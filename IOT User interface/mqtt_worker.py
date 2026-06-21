import time
import json
import paho.mqtt.client as mqtt
from pymongo import MongoClient
from datetime import datetime

# --- CONFIGURATION ---
# MQTT Broker (Use a public one for testing, or your own)
MQTT_BROKER = "broker.hivemq.com" 
MQTT_PORT = 1883
MQTT_TOPIC_DATA = "smartplant/sensors"   # NodeMCU publishes here
MQTT_TOPIC_CMD  = "smartplant/commands"  # We publish commands here

# Database
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'smart_plant_db'

# --- DATABASE CONNECTION ---
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
data_collection = db['sensor_data']
commands_collection = db['commands']

# --- MQTT CALLBACKS ---

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected to Broker (Code: {rc})")
    # Subscribe to sensor data from NodeMCU
    client.subscribe(MQTT_TOPIC_DATA)

def on_message(client, userdata, msg):
    try:
        # 1. Receive message from NodeMCU
        payload = msg.payload.decode('utf-8')
        print(f"[MQTT] Received: {payload}")

        # 2. Parse JSON (Expected: {"Temp": 25, "Dist": 10 ...})
        data = json.loads(payload)
        data['timestamp'] = datetime.now()

        # 3. Save to MongoDB
        data_collection.insert_one(data)
        print("[DB] Data saved.")

        # 4. Check for Alerts (Logic from previous steps)
        # (You can paste your alert function here)

    except Exception as e:
        print(f"[ERROR] Message processing: {e}")

# --- MAIN LOOP ---

def main():
    # 1. Setup MQTT Client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    print("[SYSTEM] Connecting to MQTT Broker...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start() # Runs MQTT in background

    print("[SYSTEM] Worker started. Listening for commands...")

    while True:
        # 2. Check for Web Commands (from MongoDB)
        try:
            pending_cmd = commands_collection.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "executed", "executed_at": datetime.now()}}
            )
            
            if pending_cmd:
                command_str = pending_cmd['command'] # e.g., "WATER_ON"
                print(f"[TX] Sending command to MQTT: {command_str}")
                
                # Publish to MQTT (NodeMCU will receive this)
                mqtt_client.publish(MQTT_TOPIC_CMD, command_str)

        except Exception as e:
            print(f"[ERROR] Command loop: {e}")

        time.sleep(0.5)

if __name__ == "__main__":
    main()