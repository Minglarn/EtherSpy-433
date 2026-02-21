import os
import json
import threading
import time
import sqlite3
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='dashboard')
CORS(app)

# SQLite configuration
DB_PATH = os.getenv('DB_PATH', 'data/etherspy.db')

# MQTT configuration (External Broker)
MQTT_BROKER = os.getenv('MQTT_BROKER', '192.168.1.125')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USER = os.getenv('MQTT_USER', '')
MQTT_PASS = os.getenv('MQTT_PASS', '')
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'rtl_433/+/events')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

# MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker ({MQTT_BROKER}) with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        save_to_db(payload)
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

def mqtt_worker():
    client = mqtt.Client()
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            print(f"MQTT Connection failed: {e}. Retrying in 5s...")
            time.sleep(5)

# Flask API
@app.route('/api/data')
def get_sensor_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Query logic adapted for SQLite: Get latest entry for each sensor_id
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

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    init_db()
    mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
    mqtt_thread.start()
    app.run(host='0.0.0.0', port=5000)
