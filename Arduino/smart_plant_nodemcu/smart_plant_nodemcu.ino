/*
 * Smart Plant System - NodeMCU ESP8266 
 * University of Cagliari - IoT Project 2025-2026
 * Authors: Sivappiryan MANIVANNAN & Patson PINTO
 *
 * Wiring (NodeMCU ↔ Arduino):
 *   NodeMCU D5 (GPIO14) RX  ←  Arduino TX (SoftSerial pin 3)
 *   NodeMCU D6 (GPIO12) TX  →  Arduino RX (SoftSerial pin 2)
 *   Common GND required between NodeMCU and Arduino
 *
 * MQTT Topics:
 *   Publish  : smartplant/sensors   (JSON sensor data → server)
 *   Subscribe: smartplant/commands  (commands from server → Arduino)
 *
 * Required Libraries (Arduino Library Manager):
 *   - "PubSubClient"  by Nick O'Leary
 *   - "ArduinoJson"   by Benoit Blanchon (v6.x)
 */

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <SoftwareSerial.h>
#include <ArduinoJson.h>

// ─────────────────────────────────────────────
//  CONFIGURATION 
// ─────────────────────────────────────────────
const char* WIFI_SSID     = "";
const char* WIFI_PASSWORD = "";

// Public MQTT broker 
const char* MQTT_BROKER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "SmartPlant_NodeMCU_01"; 
// ─────────────────────────────────────────────
//  MQTT TOPICS
// ─────────────────────────────────────────────
const char* TOPIC_DATA = "smartplant/sensors";    
const char* TOPIC_CMD  = "smartplant/commands";   

// ─────────────────────────────────────────────
//  SOFTWARESERIAL PINS (to Arduino)
// ─────────────────────────────────────────────
#define SW_RX D5   // GPIO14 — receives from Arduino TX (pin 3)
#define SW_TX D6   // GPIO12 — sends to Arduino RX (pin 2)

// ─────────────────────────────────────────────
//  OBJECT INSTANCES
// ─────────────────────────────────────────────
SoftwareSerial arduinoSerial(SW_RX, SW_TX);
WiFiClient     wifiClient;
PubSubClient   mqttClient(wifiClient);

// ─────────────────────────────────────────────
//  MQTT CALLBACK — incoming commands from server
// ─────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  Serial.println("[MQTT←Broker] " + String(topic) + ": " + msg);

  // Forward the command to Arduino over SoftwareSerial
  arduinoSerial.println(msg);
  Serial.println("[TX→Arduino] " + msg);
}

// ─────────────────────────────────────────────
//  WIFI CONNECTION
// ─────────────────────────────────────────────
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("[WiFi] Connecting to ");
  Serial.print(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - start > 20000) {   // 20s timeout, then retry
      Serial.println(F("\n[WiFi] Timeout, retrying..."));
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      start = millis();
    }
  }
  Serial.println();
  Serial.print(F("[WiFi] Connected. IP: "));
  Serial.println(WiFi.localIP());
}

// ─────────────────────────────────────────────
//  MQTT CONNECTION
// ─────────────────────────────────────────────
void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print(F("[MQTT] Connecting to broker..."));
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println(F(" OK"));
      mqttClient.subscribe(TOPIC_CMD);
      Serial.print(F("[MQTT] Subscribed to: "));
      Serial.println(TOPIC_CMD);
    } else {
      Serial.print(F(" Failed (rc="));
      Serial.print(mqttClient.state());
      Serial.println(F("). Retry in 5s..."));
      delay(5000);
    }
  }
}

// ─────────────────────────────────────────────
//  JSON BUILDER
//  Parses "Temp:22.5;Hum:55.0;Light:400;Dist:15.0"
//  Builds  {"Temp":22.5,"Hum":55.0,"Light":400,"Dist":15.0}
// ─────────────────────────────────────────────
String buildJson(const String& rawLine) {
  StaticJsonDocument<256> doc;

  // Work on a mutable copy
  char buf[rawLine.length() + 1];
  rawLine.toCharArray(buf, sizeof(buf));

  char* token = strtok(buf, ";");
  while (token != NULL) {
    char* colon = strchr(token, ':');
    if (colon != NULL) {
      *colon = '\0';          // Split key and value
      doc[token] = atof(colon + 1);
    }
    token = strtok(NULL, ";");
  }

  String output;
  serializeJson(doc, output);
  return output;
}

// ─────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────
void setup() {
  Serial.begin(9600);       // USB Serial Monitor 
  arduinoSerial.begin(9600); // SoftwareSerial to Arduino
  delay(100);

  Serial.println(F("========================================="));
  Serial.println(F(" Smart Plant System - NodeMCU ESP8266   "));
  Serial.println(F("  MQTT Gateway                          "));
  Serial.println(F("========================================="));

  connectWiFi();

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(60);
  mqttClient.setBufferSize(512);

  connectMQTT();

  Serial.println(F("[SYSTEM] Ready. Waiting for Arduino data..."));
}

// ─────────────────────────────────────────────
//  MAIN LOOP
// ─────────────────────────────────────────────
void loop() {
  // ── Maintain connections ──────────────────────────────────────────────────
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("[WiFi] Connection lost. Reconnecting..."));
    connectWiFi();
  }
  if (!mqttClient.connected()) {
    Serial.println(F("[MQTT] Connection lost. Reconnecting..."));
    connectMQTT();
  }
  mqttClient.loop(); // Process incoming MQTT messages (triggers mqttCallback)

  // ── Read data from Arduino via SoftwareSerial ─────────────────────────────
  if (arduinoSerial.available()) {
    String line = arduinoSerial.readStringUntil('\n');
    line.trim();

    if (line.length() == 0) return;

    Serial.println("[RX←Arduino] " + line);

    // Build JSON and publish to MQTT broker
    String jsonPayload = buildJson(line);

    if (jsonPayload != "null" && jsonPayload.length() > 2) {
      bool success = mqttClient.publish(TOPIC_DATA, jsonPayload.c_str());
      if (success) {
        Serial.println("[MQTT→Broker] Published: " + jsonPayload);
      } else {
        Serial.println(F("[MQTT] Publish failed. Buffer might be full."));
      }
    }
  }
}
