from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- DB CONNECTION ---
client = MongoClient('localhost', 27017)
db = client['smart_plant_db']
users_collection = db['users']
data_collection = db['sensor_data']
commands_collection = db['commands']

# --- AUTH ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    user_data = users_collection.find_one({"username": username})
    if user_data: return User(username)
    return None

# --- ROUTES ---
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error_msg = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_collection.find_one({"username": username})
        if user_data and check_password_hash(user_data['password'], password):
            user = User(username)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            error_msg = "Invalid credentials."
    return render_template('login.html', error=error_msg)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', username=current_user.id)

# --- API ---
@app.route('/api/sensor_data')
@login_required
def get_sensor_data():
    latest = data_collection.find_one(sort=[('timestamp', -1)])
    if latest:
        latest['_id'] = str(latest['_id'])
        if 'timestamp' in latest:
            latest['timestamp'] = latest['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(latest)
    return jsonify({})

@app.route('/api/history')
@login_required
def get_history():
    time_range = request.args.get('range', 'hour')
    now = datetime.now()
    if time_range == 'day': start = now - timedelta(days=1)
    elif time_range == 'week': start = now - timedelta(weeks=1)
    else: start = now - timedelta(hours=1)

    cursor = data_collection.find({"timestamp": {"$gte": start}}).sort("timestamp", 1)
    data = {"labels": [], "temp": [], "hum": [], "light": []}
    for doc in cursor:
        data["labels"].append(doc['timestamp'].strftime("%H:%M"))
        data["temp"].append(doc.get('Temp', 0))
        data["hum"].append(doc.get('Hum', 0))
        data["light"].append(doc.get('Light', 0))
    return jsonify(data)

@app.route('/api/water_plant', methods=['POST'])
@login_required
def water_plant():
    commands_collection.insert_one({
        "command": "WATER_ON",
        "status": "pending",
        "timestamp": datetime.now(),
        "user": current_user.id
    })
    return jsonify({"status": "success", "message": "Command sent successfully!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)