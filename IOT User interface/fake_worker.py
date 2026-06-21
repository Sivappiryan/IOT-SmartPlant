import time
import random
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pymongo import MongoClient
from datetime import datetime

# --- CONFIGURATION ---
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'smart_plant_db'

# --- PASTE YOUR CREDENTIALS HERE ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1469125092574232820/_8R53GWyRhR6rdW2f3cHFAC1yhOudAKcUl8z0oAYoYFdE2is7elfFe6hPZijEp1pEm8x"
ENABLE_EMAIL = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "sivappiryanmanivannan@gmail.com"
SENDER_PASSWORD = "tldj lvmi usbl lafn"

# --- DATABASE ---
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    data_collection = db['sensor_data']
    commands_collection = db['commands']
    users_collection = db['users']
    print("[SYSTEM] MongoDB connection successful.")
except Exception as e:
    print(f"[CRITICAL ERROR] MongoDB: {e}")

# --- ALERT FUNCTION ---
def send_alert_to_users(subject, message_body):
    print(f"\n[ALERT SYSTEM] Sending: {subject}")

    # Discord
    if DISCORD_WEBHOOK_URL and "http" in DISCORD_WEBHOOK_URL:
        try:
            payload = {"content": f"**SIMULATION**: {subject}\n{message_body}", "username": "Plant Simulator"}
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
            print("   -> [OK] Discord notified.")
        except Exception as e:
            print(f"   -> [ERROR] Discord: {e}")

    # Email
    if ENABLE_EMAIL:
        try:
            users = list(users_collection.find({"email": {"$exists": True, "$ne": ""}}))
            if not users:
                print("   -> [WARNING] No users with email found.")
                return

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            
            for user in users:
                msg = MIMEMultipart()
                msg['From'] = SENDER_EMAIL
                msg['To'] = user['email']
                msg['Subject'] = f"SIMULATION TEST: {subject}"
                msg.attach(MIMEText(message_body, 'plain'))
                server.sendmail(SENDER_EMAIL, user['email'], msg.as_string())
                print(f"   -> [OK] Email sent to {user['email']}")
            
            server.quit()
        except Exception as e:
            print(f"   -> [ERROR] Email: {e}")

# --- MAIN LOOP ---
def main():
    print("--- FAKE WORKER STARTED ---")
    print("Cycling between FULL and EMPTY to test alerts.")
    
    tank_empty_alert_sent = False 
    cycle_counter = 0

    while True:
        # Generate Data
        temp = round(random.uniform(20.0, 30.0), 1)
        hum = round(random.uniform(40.0, 60.0), 1)
        light = random.randint(200, 800)
        
        # Simulation Logic
        cycle_counter += 1
        if cycle_counter > 3: 
            dist = 25.0  # EMPTY -> Alert
            state_desc = "EMPTY (Alert Expected)"
            if cycle_counter > 6: cycle_counter = 0 
        else:
            dist = 10.0  # FULL -> Normal
            state_desc = "FULL"

        fake_data = {"timestamp": datetime.now(), "Temp": temp, "Hum": hum, "Light": light, "Dist": dist}
        data_collection.insert_one(fake_data)
        print(f"[DATA] Simu [{state_desc}] : Dist={dist}cm")

        # Alert Logic
        if dist > 20 and not tank_empty_alert_sent:
            print("\n[DETECTION] TANK EMPTY (>20cm)")
            send_alert_to_users("WATER ALERT", "Simulation: Tank is empty (25cm).")
            tank_empty_alert_sent = True 
        elif dist <= 20 and tank_empty_alert_sent:
            print("\n[DETECTION] TANK REFILLED")
            send_alert_to_users("INFO", "Simulation: Tank is full again.")
            tank_empty_alert_sent = False 

        # Check for Web Commands
        try:
            pending_cmd = commands_collection.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "executed", "executed_at": datetime.now()}}
            )
            if pending_cmd:
                print(f"\n[COMMAND] RECEIVED: {pending_cmd['command']}")
        except Exception: pass

        time.sleep(3)

if __name__ == "__main__":
    main()