import serial
import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pymongo import MongoClient
from datetime import datetime

# --- CONFIGURATION ---
SERIAL_PORT = 'COM3' 
BAUD_RATE = 9600
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'smart_plant_db'


ENABLE_EMAIL = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "sivappiryanmanivannan@gmail.com"
SENDER_PASSWORD = "tldj lvmi usbl lafn"

# --- DATABASE CONNECTION ---
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
data_collection = db['sensor_data']
commands_collection = db['commands']
users_collection = db['users']

# --- ALERT FUNCTION ---
def send_alert_to_users(subject, message_body):
    """Sends alert via Email"""
 

    # Email
    if ENABLE_EMAIL:
        try:
            users = list(users_collection.find({"email": {"$exists": True, "$ne": ""}}))
            if not users: return

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            
            for user in users:
                msg = MIMEMultipart()
                msg['From'] = SENDER_EMAIL
                msg['To'] = user['email']
                msg['Subject'] = f"SMART PLANT: {subject}"
                msg.attach(MIMEText(message_body, 'plain'))
                server.sendmail(SENDER_EMAIL, user['email'], msg.as_string())
                print(f"[INFO] Email sent to {user['email']}")
            
            server.quit()
        except Exception as e:
            print(f"[ERROR] Email failed: {e}")

# --- MAIN LOOP ---
def connect_serial():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"[SYSTEM] Connected to Arduino on {SERIAL_PORT}")
        return ser
    except Exception as e:
        print(f"[ERROR] Serial connection failed: {e}")
        return None

def main():
    ser = connect_serial()
    time.sleep(2)
    tank_empty_alert_sent = False 
    print("[SYSTEM] Worker started.")

    while True:
        if ser is None:
            time.sleep(5)
            ser = connect_serial()
            continue

        # 1. READ SENSORS
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    print(f"[RX] {line}")
                    parts = line.split(';')
                    data = {"timestamp": datetime.now()}
                    for part in parts:
                        if ':' in part:
                            key, val = part.split(':')
                            try: data[key.strip()] = float(val)
                            except ValueError: data[key.strip()] = val
                    
                    data_collection.insert_one(data)

                    # Alert Logic
                    dist = data.get('Dist', 0)
                    if dist > 20 and not tank_empty_alert_sent:
                        send_alert_to_users("TANK EMPTY", f"Water level critical: {dist}cm.")
                        tank_empty_alert_sent = True
                    elif dist <= 20 and tank_empty_alert_sent:
                        send_alert_to_users("INFO", "Tank refilled.")
                        tank_empty_alert_sent = False

        except Exception as e:
            print(f"[ERROR] Read loop: {e}")

        # 2. SEND COMMANDS
        try:
            pending_cmd = commands_collection.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "executed", "executed_at": datetime.now()}}
            )
            if pending_cmd:
                ser.write(f"{pending_cmd['command']}\n".encode('utf-8'))
                print(f"[TX] Command sent: {pending_cmd['command']}")
        except Exception: pass
            
        time.sleep(0.1)

if __name__ == "__main__":
    main()
