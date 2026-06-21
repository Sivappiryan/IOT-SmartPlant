import getpass
from pymongo import MongoClient
from werkzeug.security import generate_password_hash

# Configuration
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'smart_plant_db'
COLLECTION_NAME = 'users'

def create_admin_user():
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        users_collection = db[COLLECTION_NAME]
        print("[SYSTEM] Connected to MongoDB.")
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
        return

    print("\n--- CREATE ADMIN USER ---")
    
    # 1. Ask for Username
    username = input("Username: ").strip()
    if not username:
        print("[ERROR] Username cannot be empty.")
        return

    # 2. Ask for Email
    email = input("Email for alerts: ").strip()
    if not email or "@" not in email:
        print("[WARNING] Invalid or empty email (you will not receive email alerts).")

    # 3. Ask for Password
    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm Password: ")

    if password != password_confirm:
        print("[ERROR] Passwords do not match.")
        return
    
    # Check if user exists
    existing_user = users_collection.find_one({"username": username})
    if existing_user:
        print(f"[INFO] User '{username}' already exists. Updating email...")
        users_collection.update_one({"username": username}, {"$set": {"email": email}})
        print("[SUCCESS] Email updated.")
        return

    # Hash password
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

    # 4. Save User
    user_data = {
        "username": username,
        "email": email,
        "password": hashed_password,
        "role": "admin"
    }

    users_collection.insert_one(user_data)
    print(f"\n[SUCCESS] User '{username}' created with email '{email}'.")

if __name__ == "__main__":
    create_admin_user()