import os
import json
import threading
import time
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='dashboard')
CORS(app)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'mariadb')
DB_NAME = os.getenv('DB_NAME', 'etherspy')
DB_USER = os.getenv('DB_USER', 'dbuser')
DB_PASS = os.getenv('DB_PASS', 'dbpassword')

# MQTT configuration
MQTT_BROKER = os.getenv('MQTT_BROKER', 'mqtt-broker')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_TOPIC = "rtl_433/+/events"

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return connection
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def save_to_db(data):
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Map fields from rtl_433 JSON
        sensor_id = data.get('id', 'unknown')
        brand = data.get('brand', 'Generic')
        model = data.get('model', 'Unknown')
        channel = str(data.get('channel', '0'))
        battery_ok = 1 if data.get('battery_ok') in ["OK", 1, True] else 0
        temp = data.get('temperature_C')
        humidity = data.get('humidity')
        raw_json = json.dumps(data)

        query = """
            INSERT INTO sensors_data 
            (sensor_id, brand, model, channel, battery_ok, temperature_c, humidity, raw_json) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (sensor_id, brand, model, channel, battery_ok, temp, humidity, raw_json))
        conn.commit()
    except Error as e:
        print(f"Error inserting into DB: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"Received data for sensor: {payload.get('id')}")
        save_to_db(payload)
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

def mqtt_worker():
    client = mqtt.Client()
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
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
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
        results = cursor.fetchall()
        return jsonify(results)
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    # Start MQTT subscriber in background thread
    mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
    mqtt_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000)
