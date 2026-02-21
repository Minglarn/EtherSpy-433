import os
import json
import threading
import time
import sqlite3
import subprocess
import signal
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='dashboard')
CORS(app)

# SQLite configuration
DB_PATH = os.getenv('DB_PATH', 'data/etherspy.db')

# Global SDR Process handle
sdr_process = None
sdr_thread = None

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Sensors Data Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensors_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT,
            brand TEXT,
            model TEXT,
            channel TEXT,
            battery_ok INTEGER,
            temperature_c REAL,
            humidity REAL,
            raw_json TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Settings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Default Settings
    defaults = [
        ('sdr_freq', '433.92M'),
        ('sdr_gain', 'auto'),
        ('sdr_protocols', '-G'),
        ('sdr_device', ':00000102'),
        ('mqtt_broker', os.getenv('MQTT_BROKER', '192.168.1.125')),
        ('mqtt_port', os.getenv('MQTT_PORT', '1883')),
        ('mqtt_user', os.getenv('MQTT_USER', '')),
        ('mqtt_pass', os.getenv('MQTT_PASS', ''))
    ]
    for key, val in defaults:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key, default=None):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def save_to_db(data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sensor_id = data.get('id', 'unknown')
        brand = data.get('brand', 'Generic')
        model = data.get('model', 'Unknown')
        channel = str(data.get('channel', '0'))
        battery_ok = 1 if data.get('battery_ok') in ["OK", 1, True] else 0
        temp = data.get('temperature_C')
        humidity = data.get('humidity')
        raw_json = json.dumps(data)

        cursor.execute("""
            INSERT INTO sensors_data 
            (sensor_id, brand, model, channel, battery_ok, temperature_c, humidity, raw_json) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sensor_id, brand, model, channel, battery_ok, temp, humidity, raw_json))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inserting into SQLite: {e}")

# SDR Management
def sdr_worker():
    global sdr_process
    while True:
        try:
            freq = get_setting('sdr_freq', '433.92M')
            gain = get_setting('sdr_gain', 'auto')
            protocols = get_setting('sdr_protocols', '-G')
            device = get_setting('sdr_device', ':00000102')

            cmd = [
                "rtl_433",
                "-d", device,
                "-f", freq,
                "-g", gain,
                protocols,
                "-F", "json",
                "-M", "level",
                "-M", "metadata",
                "-M", "time:iso8601"
            ]
            
            print(f"Starting SDR: {' '.join(cmd)}")
            sdr_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            for line in sdr_process.stdout:
                try:
                    data = json.loads(line)
                    save_to_db(data)
                except json.JSONDecodeError:
                    if "R82XX" not in line: # Filter noisy logs
                        print(f"SDR Debug: {line.strip()}")
            
            sdr_process.wait()
        except Exception as e:
            print(f"SDR Process Error: {e}")
        
        print("SDR Process exited. Restarting in 5s...")
        time.sleep(5)

def restart_sdr():
    global sdr_process
    if sdr_process:
        print("Restarting SDR process with new settings...")
        sdr_process.terminate()
        try:
            sdr_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sdr_process.kill()
        sdr_process = None

# Flask API
@app.route('/api/data')
def get_sensor_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT s1.* 
            FROM sensors_data s1
            INNER JOIN (
                SELECT sensor_id, MAX(timestamp) as max_ts
                FROM sensors_data
                GROUP BY sensor_id
            ) s2 ON s1.sensor_id = s2.sensor_id AND s1.timestamp = s2.max_ts
            ORDER BY s1.timestamp DESC
        """
        cursor.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    if request.method == 'GET':
        conn = get_db_connection()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        return jsonify({row['key']: row['value'] for row in rows})
    
    data = request.json
    conn = get_db_connection()
    for key, value in data.items():
        conn.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()
    
    restart_sdr()
    return jsonify({'status': 'success'})

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    init_db()
    sdr_thread = threading.Thread(target=sdr_worker, daemon=True)
    sdr_thread.start()
    app.run(host='0.0.0.0', port=5000)
