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
        ('sdr_protocols', ''), # Empty means default protocols
        ('sdr_device', ':0'),  # Default to first device if serial fails
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
    if not isinstance(data, dict):
        return # Ignore non-JSON data (individual values from MQTT)
        
    try:
        # We need at least an ID or model to consider this valid sensor data
        sensor_id = data.get('id') or data.get('sensor_id')
        if not sensor_id:
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        """, (str(sensor_id), brand, model, channel, battery_ok, temp, humidity, raw_json))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inserting into SQLite: {e}")
        # print(f"Offending data: {data}") # Debug

# MQTT Subscriber (for receiving from broker)
def mqtt_subscriber():
    client = mqtt.Client()
    
    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            print("MQTT Subscriber: Connected to broker")
            c.subscribe("rtl_433/#")
        else:
            print(f"MQTT Subscriber: Connection failed (code {rc})")

    def on_message(c, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            save_to_db(payload)
        except Exception as e:
            pass

    client.on_connect = on_connect
    client.on_message = on_message

    last_broker = None
    while True:
        broker = get_setting('mqtt_broker', '')
        port = int(get_setting('mqtt_port', '1883'))
        user = get_setting('mqtt_user', '')
        pw = get_setting('mqtt_pass', '')

        if broker and broker != last_broker:
            try:
                print(f"MQTT Subscriber: Connecting to {broker}...")
                if user and pw:
                    client.username_pw_set(user, pw)
                client.disconnect()
                client.connect(broker, port, 60)
                last_broker = broker
            except Exception as e:
                print(f"MQTT Subscriber Error: {e}")
        
        client.loop(timeout=1.0)
        time.sleep(1)

# SDR Management
def sdr_worker():
    global sdr_process
    while True:
        try:
            freq = get_setting('sdr_freq', '433.92M')
            gain = get_setting('sdr_gain', 'auto')
            protocols = get_setting('sdr_protocols', '')
            device = get_setting('sdr_device', ':0')
            broker = get_setting('mqtt_broker', '')
            port = get_setting('mqtt_port', '1883')
            user = get_setting('mqtt_user', '')
            pw = get_setting('mqtt_pass', '')

            # Heuristic: Fix serial ID if user forgot the colon
            if len(device) > 2 and not device.startswith(':') and not device.isdigit():
                device = f":{device}"

            # Basic command structure
            cmd = [
                "rtl_433",
                "-d", device,
                "-f", freq,
                "-g", gain,
                "-F", "log", # Always show logs during startup
                "-F", "json",
                "-M", "level",
                "-M", "metadata",
                "-M", "time:iso8601"
            ]
            
            # Optional MQTT Output
            if broker:
                mqtt_dest = f"mqtt://{broker}:{port}"
                if user: mqtt_dest += f",user={user}"
                if pw: mqtt_dest += f",pass={pw}"
                mqtt_dest += ",retain=0,devices=rtl_433[/model][/id]"
                cmd.extend(["-F", mqtt_dest])

            # Handle protocols safely
            # Note: -G is deprecated and causes exits in newer versions. 
            # If empty, 'all', or '-G' is requested, we use the 90+ default decoders by omitting the flag.
            p_clean = protocols.strip().lower()
            if p_clean and p_clean not in ["all", "-g"]:
                for p in protocols.split(','):
                    cmd.extend(["-R", p.strip()])
            
            print(f"Starting SDR: {' '.join(cmd)}")
            process_env = os.environ.copy()
            sdr_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True,
                env=process_env
            )
            
            for line in sdr_process.stdout:
                line = line.strip()
                if not line: continue
                
                # If it's data JSON
                if line.startswith('{') and line.endswith('}'):
                    try:
                        data = json.loads(line)
                        save_to_db(data)
                        continue
                    except json.JSONDecodeError:
                        pass
                
                # Suppress only extremely noisy repeated logs
                if any(x in line for x in ["Exact sample rate", "Tuned to"]):
                    continue
                    
                print(f"SDR Engine: {line}")
            
            sdr_process.wait()
            rc = sdr_process.returncode
            if rc != 0:
                print(f"SDR Engine FATAL: Engine exited with code {rc}. Check hardware or MQTT credentials.")
        except Exception as e:
            print(f"SDR Worker Error: {e}")
        
        print("SDR Worker: Restarting engine in 5s...")
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
    mqtt_thread = threading.Thread(target=mqtt_subscriber, daemon=True)
    mqtt_thread.start()
    app.run(host='0.0.0.0', port=5000)
