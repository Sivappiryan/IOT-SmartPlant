import time
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import paho.mqtt.client as mqtt
from pymongo import MongoClient
from datetime import datetime

# --- MQTT CONFIGURATION ---
MQTT_BROKER     = "broker.hivemq.com"
MQTT_PORT       = 1883
MQTT_TOPIC_DATA = "smartplant/sensors"    # NodeMCU publishes here
MQTT_TOPIC_CMD  = "smartplant/commands"   # Server publishes commands here
MQTT_CLIENT_ID  = "SmartPlant_Server_Worker"

# --- DATABASE ---
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME   = 'smart_plant_db'


ENABLE_EMAIL        = True
SMTP_SERVER         = "smtp.gmail.com"
SMTP_PORT           = 587
SENDER_EMAIL        = "sivappiryanmanivannan@gmail.com"
SENDER_PASSWORD     = "tldj lvmi usbl lafn"

TANK_EMPTY_THRESHOLD = 20.0   # cm — distance above which tank is considered empty
TEMP_HIGH_THRESHOLD  = 35.0   # °C — extreme heat alert
TEMP_LOW_THRESHOLD   =  5.0   # °C — extreme cold alert

# --- DATABASE CONNECTION ---
mongo_client        = MongoClient(MONGO_URI)
db                  = mongo_client[DB_NAME]
data_collection     = db['sensor_data']
commands_collection = db['commands']
users_collection    = db['users']

# --- ALERT STATES (Anti-spam: one notification per event, reset on recovery) ---
tank_empty_alert_sent  = False
temp_high_alert_sent   = False
temp_low_alert_sent    = False

# ─────────────────────────────────────────────
#  ALERT FUNCTION
# ─────────────────────────────────────────────
def send_alert(subject: str, body: str):
    """Send alert via Discord webhook and email to all registered users."""
    print(f"\n[ALERT] Sending: {subject}")


    # Email to all registered users
    if ENABLE_EMAIL:
        try:
            users = list(users_collection.find({"email": {"$exists": True, "$ne": ""}}))
            if not users:
                print("   [Email] No users with email address found.")
            else:
                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                for user in users:
                    msg            = MIMEMultipart()
                    msg['From']    = SENDER_EMAIL
                    msg['To']      = user['email']
                    msg['Subject'] = f"SMART PLANT: {subject}"
                    msg.attach(MIMEText(body, 'plain'))
                    server.sendmail(SENDER_EMAIL, user['email'], msg.as_string())
                    print(f"   [Email] Sent to {user['email']}")
                server.quit()
        except Exception as e:
            print(f"   [Email ERROR] {e}")

# ─────────────────────────────────────────────
#  ALERT CHECKS (called after each DB insert)
# ─────────────────────────────────────────────

def check_tank_alert(dist):
    """Water tank empty/refill alerts (FR3 / FR4 - Safety Lockout)."""
    global tank_empty_alert_sent
    if isinstance(dist, (int, float)) and dist > TANK_EMPTY_THRESHOLD:
        if not tank_empty_alert_sent:
            send_alert(
                subject="Water Tank Empty",
                body=(
                    f"The water tank is empty (distance: {dist:.1f} cm > {TANK_EMPTY_THRESHOLD} cm).\n"
                    "The pump has been locked to prevent dry-run damage.\n"
                    "Please refill the tank as soon as possible."
                )
            )
            tank_empty_alert_sent = True
    else:
        if tank_empty_alert_sent:
            send_alert(
                subject="Water Tank Refilled",
                body=(
                    f"The water tank has been refilled (distance: {dist:.1f} cm).\n"
                    "The pump is now unlocked. System back to normal."
                )
            )
            tank_empty_alert_sent = False


def check_temperature_alert(temp):
    """Extreme temperature anomaly alerts (mentioned in architecture, page 13 of project PDF)."""
    global temp_high_alert_sent, temp_low_alert_sent
    if not isinstance(temp, (int, float)) or temp < 0:
        return  # Ignore invalid readings

    # High temperature
    if temp > TEMP_HIGH_THRESHOLD:
        if not temp_high_alert_sent:
            send_alert(
                subject="High Temperature Alert",
                body=(
                    f"Extreme heat detected: {temp:.1f} °C (threshold: {TEMP_HIGH_THRESHOLD} °C).\n"
                    "Your plant may be suffering from heat stress.\n"
                    "Consider moving the plant to a cooler location or increasing ventilation."
                )
            )
            temp_high_alert_sent = True
    else:
        temp_high_alert_sent = False

    # Low temperature
    if temp < TEMP_LOW_THRESHOLD:
        if not temp_low_alert_sent:
            send_alert(
                subject="Low Temperature Alert",
                body=(
                    f"Extreme cold detected: {temp:.1f} °C (threshold: {TEMP_LOW_THRESHOLD} °C).\n"
                    "Your plant may be at risk of frost damage.\n"
                    "Consider moving the plant to a warmer location."
                )
            )
            temp_low_alert_sent = True
    else:
        temp_low_alert_sent = False


def run_irrigation_decision(data, mqtt_client):
    """
    Irrigation Decision Service — Eco-Smart automatic watering logic (FR2 / Service Composition Layer).
    Evaluates conditions server-side and triggers automatic watering when:
      - Humidity is low  (< 30 %) → plant environment is too dry
      - Tank has water   (TankOK == 1)
      - Light is safe    (EcoOK  == 1) → no high sunlight (prevents evaporation)
    This mirrors and supplements the Arduino-side Eco-Smart guard.
    """
    hum    = data.get('Hum',    None)
    tank_ok = data.get('TankOK', 1)
    eco_ok  = data.get('EcoOK',  1)

    if hum is None or not isinstance(hum, (int, float)):
        return

    if hum < 30.0 and tank_ok == 1 and eco_ok == 1:
        print(f"[ECO-SMART] Auto-watering triggered: Hum={hum:.1f}% < 30%, Tank OK, Light OK.")
        # Queue automatic watering command (same pipeline as manual button)
        commands_collection.insert_one({
            "command":    "WATER_ON",
            "status":     "pending",
            "timestamp":  datetime.now(),
            "user":       "eco_smart_auto"
        })
        send_alert(
            subject="Eco-Smart: Automatic Watering Triggered",
            body=(
                f"The system has automatically triggered watering.\n"
                f"Reason: Air humidity is low ({hum:.1f}% < 30%) and conditions are safe.\n"
                f"  - Water Tank: {'OK' if tank_ok else 'Empty (should not happen)'}\n"
                f"  - Sunlight  : {'Safe' if eco_ok else 'Too bright (should not happen)'}\n"
                "The pump will run for 5 seconds."
            )
        )

# ─────────────────────────────────────────────
#  MQTT CALLBACKS
# ─────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected to broker.")
        client.subscribe(MQTT_TOPIC_DATA)
        print(f"[MQTT] Subscribed to: {MQTT_TOPIC_DATA}")
    else:
        print(f"[MQTT] Connection failed (rc={rc})")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        print(f"[MQTT] Received: {payload}")

        data = json.loads(payload)
        data['timestamp'] = datetime.now()

        # Semantic Enrichment: add human-readable interpretations
        dist = data.get('Dist', 0)
        temp = data.get('Temp', None)
        data['tank_status'] = "Empty"   if (isinstance(dist, (int,float)) and dist > TANK_EMPTY_THRESHOLD) else "OK"
        data['eco_status']  = "Blocked" if data.get('EcoOK', 1) == 0 else "OK"

        data_collection.insert_one(data)
        print(f"[DB] Saved. Tank={data['tank_status']}  Eco={data['eco_status']}")

        # Run all alert checks (anti-spam state-machine)
        check_tank_alert(dist)
        check_temperature_alert(temp)

        # Run Irrigation Decision Service (Eco-Smart auto-watering)
        run_irrigation_decision(data, client)

    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON: {msg.payload}")
    except Exception as e:
        print(f"[ERROR] Message processing: {e}")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    print("[SYSTEM] MQTT Worker starting...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    print("[SYSTEM] Worker ready. Listening for sensor data and web commands...")

    while True:
        try:
            # Check for pending watering commands from the web dashboard
            pending = commands_collection.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "executed", "executed_at": datetime.now()}}
            )
            if pending:
                cmd = pending['command']
                print(f"[TX] Publishing command to MQTT: {cmd}")
                mqtt_client.publish(MQTT_TOPIC_CMD, cmd)

        except Exception as e:
            print(f"[ERROR] Command loop: {e}")

        time.sleep(0.5)

if __name__ == "__main__":
    main()