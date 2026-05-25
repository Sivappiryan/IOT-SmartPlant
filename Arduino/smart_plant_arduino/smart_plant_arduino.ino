/*
 * Smart Plant System - Arduino Uno R3 (Central Control Unit)
 * University of Cagliari - IoT Project 2025-2026
 * Authors: Sivappiryan MANIVANNAN & Patson PINTO
 *
 *
 * Wiring:
 *   DHT11    -> Pin 7
 *   LDR      -> Pin A0 (analog, higher = brighter)
 *   HC-SR04  -> TRIG: Pin 9 | ECHO: Pin 10
 *   Relay    -> Pin 6   (active LOW: LOW = pump ON)
 *   Buzzer   -> Pin 5
 *   LED      -> Pin 4
 *   Button   -> Pin 8   (INPUT_PULLUP: press to silence alarm)
 *   NodeMCU  -> SoftSerial RX=Pin 2 (from NodeMCU TX/D6)
 *                          TX=Pin 3  (to  NodeMCU RX/D5)
 *
 * Required Libraries (Arduino Library Manager):
 *   - "DHT sensor library" by Adafruit
 *   - "Adafruit Unified Sensor"
 */

#include <DHT.h>
#include <SoftwareSerial.h>

// ─────────────────────────────────────────────
//  PIN DEFINITIONS
// ─────────────────────────────────────────────
#define DHT_PIN       7
#define DHT_TYPE      DHT11
#define LDR_PIN       A0
#define TRIG_PIN      9
#define ECHO_PIN      10
#define RELAY_PIN     6    // Active LOW relay: LOW=pump ON, HIGH=pump OFF
#define BUZZER_PIN    5
#define LED_PIN       4
#define BUTTON_PIN    8    // Physical silence/override button (INPUT_PULLUP)
#define SW_RX         2    // Receives from NodeMCU TX (D6)
#define SW_TX         3    // Transmits to NodeMCU RX (D5)

// ─────────────────────────────────────────────
//  THRESHOLDS
// ─────────────────────────────────────────────
#define TANK_EMPTY_CM       20.0  // Distance > 20cm → tank empty → pump locked
#define HIGH_LIGHT_THRESHOLD 750  // LDR raw > 750 → high sunlight → watering blocked
                                  // (prevents evaporation — "Eco-Smart" logic, FR2)
#define PUMP_DURATION_MS    5000  // Pump runs 5 seconds per watering cycle
#define SEND_INTERVAL_MS    5000  // Send sensor data every 5 seconds
#define DEBOUNCE_DELAY_MS     50  // Button debounce

// ─────────────────────────────────────────────
//  INSTANCES
// ─────────────────────────────────────────────
DHT dht(DHT_PIN, DHT_TYPE);
SoftwareSerial nodeSerial(SW_RX, SW_TX);

// ─────────────────────────────────────────────
//  STATE
// ─────────────────────────────────────────────
bool tankEmpty          = false;
bool highSunlight       = false;   // Eco-Smart flag: block watering during bright daylight
bool alarmSilenced      = false;   // Set by button press to silence local buzzer
unsigned long lastSendMs       = 0;
unsigned long lastDebounceMs   = 0;
int  lastButtonState           = HIGH; // INPUT_PULLUP → idle = HIGH

// ─────────────────────────────────────────────
//  SENSOR HELPERS
// ─────────────────────────────────────────────
float readUltrasonic() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if (duration == 0) return 999.0; // Sensor error → treat as empty (safe default)
  return duration * 0.0343 / 2.0;
}

int readLight() {
  return analogRead(LDR_PIN); // 0 = dark, 1023 = very bright
}

// ─────────────────────────────────────────────
//  BUTTON (debounced, INPUT_PULLUP)
// ─────────────────────────────────────────────
void checkButton() {
  int reading = digitalRead(BUTTON_PIN);
  if (reading != lastButtonState) {
    lastDebounceMs = millis();
  }
  if ((millis() - lastDebounceMs) > DEBOUNCE_DELAY_MS) {
    // Button pressed (LOW because INPUT_PULLUP)
    if (reading == LOW && lastButtonState == HIGH) {
      alarmSilenced = !alarmSilenced;
      Serial.println(alarmSilenced
        ? F("[BUTTON] Alarm silenced by user.")
        : F("[BUTTON] Alarm re-enabled."));
    }
  }
  lastButtonState = reading;
}

// ─────────────────────────────────────────────
//  ACTUATORS
// ─────────────────────────────────────────────
void pumpOn()  { digitalWrite(RELAY_PIN, LOW);  } // Active LOW
void pumpOff() { digitalWrite(RELAY_PIN, HIGH); }

/*
 * Eco-Smart Pump Guard
 * Blocks watering if:
 *   (a) Tank is empty             → dry-run protection (FR4)
 *   (b) High sunlight detected    → prevents evaporation (FR2 Eco-Smart)
 * Returns true if pump was activated, false if blocked.
 */
bool activatePump() {
  if (tankEmpty) {
    Serial.println(F("[SAFETY] Pump BLOCKED: tank is empty (dist > 20 cm)."));
    return false;
  }
  if (highSunlight) {
    Serial.println(F("[ECO-SMART] Pump BLOCKED: high sunlight detected. Water would evaporate."));
    return false;
  }
  Serial.println(F("[ACTION] Eco-Smart OK. Pump ON for 5 seconds..."));
  pumpOn();
  delay(PUMP_DURATION_MS);
  pumpOff();
  Serial.println(F("[ACTION] Pump OFF."));
  return true;
}

// ─────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  nodeSerial.begin(9600);
  dht.begin();

  pinMode(TRIG_PIN,   OUTPUT);
  pinMode(ECHO_PIN,   INPUT);
  pinMode(RELAY_PIN,  OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN,    OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  pumpOff();
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN,    LOW);

  Serial.println(F("============================================="));
  Serial.println(F("  Smart Plant System - Arduino Uno R3       "));
  Serial.println(F("  Safety Lockout  : dist > 20 cm            "));
  Serial.println(F("  Eco-Smart Block : light > 750 (raw)       "));
  Serial.println(F("  Button (pin 8)  : silence alarm           "));
  Serial.println(F("============================================="));
}

// ─────────────────────────────────────────────
//  MAIN LOOP
// ─────────────────────────────────────────────
void loop() {

  // ── 1. BUTTON CHECK (every iteration, non-blocking) ──────────────────────
  checkButton();

  // ── 2. INCOMING COMMANDS FROM NODEMCU ────────────────────────────────────
  if (nodeSerial.available()) {
    String cmd = nodeSerial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      Serial.println("[RX] Command: " + cmd);
      if (cmd == "WATER_ON") {
        activatePump(); // Eco-Smart guard inside
      }
    }
  }

  // ── 3. PERIODIC SENSOR READ + TRANSMISSION ───────────────────────────────
  unsigned long now = millis();
  if (now - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = now;

    float temp  = dht.readTemperature();
    float hum   = dht.readHumidity();
    float dist  = readUltrasonic();
    int   light = readLight();

    if (isnan(temp)) { temp = -1.0; Serial.println(F("[WARN] DHT Temp read failed.")); }
    if (isnan(hum))  { hum  = -1.0; Serial.println(F("[WARN] DHT Hum read failed."));  }

    // ── 4. SAFETY + ECO-SMART FLAGS ──
    tankEmpty   = (dist  > TANK_EMPTY_CM);
    highSunlight = (light > HIGH_LIGHT_THRESHOLD);

    // ── 5. LOCAL ALARM (buzzer + LED) if tank empty and not silenced by button ──
    if (tankEmpty && !alarmSilenced) {
      digitalWrite(BUZZER_PIN, HIGH);
      digitalWrite(LED_PIN,    HIGH);
    } else {
      digitalWrite(BUZZER_PIN, LOW);
      // Keep LED on as visual indicator even when silenced
      digitalWrite(LED_PIN, tankEmpty ? HIGH : LOW);
    }

    // ── 6. BUILD STATUS STRING AND SEND TO NODEMCU ──
    // Format: "Temp:22.5;Hum:55.0;Light:400;Dist:15.0;TankOK:1;EcoOK:1"
    // TankOK=1 means tank has water | EcoOK=1 means light level is safe to water
    String data = "Temp:"   + String(temp,  1) +
                  ";Hum:"   + String(hum,   1) +
                  ";Light:" + String(light)     +
                  ";Dist:"  + String(dist,  1)  +
                  ";TankOK:"  + String(tankEmpty    ? 0 : 1) +
                  ";EcoOK:"   + String(highSunlight ? 0 : 1);

    nodeSerial.println(data);

    Serial.println(F("──────────────────────────────────────────"));
    Serial.println("[TX→NodeMCU] " + data);
    Serial.print  (F("  Tank:    ")); Serial.println(tankEmpty    ? "EMPTY (pump locked)"  : "OK");
    Serial.print  (F("  Eco:     ")); Serial.println(highSunlight ? "HIGH LIGHT (blocked)" : "OK");
    Serial.print  (F("  Alarm:   ")); Serial.println(alarmSilenced ? "Silenced by button" : "Active");
    Serial.println(F("──────────────────────────────────────────"));
  }
}
