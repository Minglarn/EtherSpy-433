import eventlet
eventlet.monkey_patch()
import os
import json
import threading
import time
import sqlite3
import subprocess
import signal
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='dashboard')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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
    # Sensor Aliases Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_aliases (
            sensor_id TEXT PRIMARY KEY,
            alias TEXT
        )
    """)
    # Add indexes for performance and reliability
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensors_data (sensor_id, timestamp)")
    # Default Settings
    defaults = [
        ('sdr_freq', '433.92M'),
        ('sdr_gain', 'auto'),
        ('sdr_protocols', ''), # Empty means default protocols
        ('sdr_device', ':0'),  # Default to first device if serial fails
        ('mqtt_broker', os.getenv('MQTT_BROKER', '192.168.1.125')),
        ('mqtt_port', os.getenv('MQTT_PORT', '1883')),
        ('mqtt_user', os.getenv('MQTT_USER', '')),
        ('mqtt_pass', os.getenv('MQTT_PASS', '')),
        ('mqtt_topic', 'rtl_433[/model][/id]'),
        ('sdr_autolevel', '1'),
        ('sdr_noise', '1'),
        ('sdr_starred', '0'),
        ('sdr_samplerate', '1024k'),
        ('sdr_celsius', '1'),
        ('sdr_stale_threshold', '60')
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
        sensor_id = data.get('id')
        if sensor_id is None: sensor_id = data.get('sensor_id')
        if sensor_id is None: # Accept 0, but not None
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        
        brand = data.get('brand', 'Generic')
        model = data.get('model', 'Unknown')
        channel = str(data.get('channel', '0'))
        battery_ok = 1 if data.get('battery_ok') in ["OK", 1, True] else 0
        
        # Safe extraction of numeric fields
        def safe_float(v):
            try: return float(v) if v is not None else None
            except: return None

        # Global Celsius Conversion
        if get_setting('sdr_celsius', '1') == '1':
            # Create a copy to avoid modifying original if needed elsewhere, 
            # but here it's fine to modify the local 'data'
            keys_to_convert = [k for k in data.keys() if k.endswith('_F')]
            for k_f in keys_to_convert:
                val_f = safe_float(data[k_f])
                if val_f is not None:
                    k_c = k_f[:-2] + '_C'
                    # Only convert if _C doesn't already exist or is None
                    if data.get(k_c) is None:
                        val_c = round((val_f - 32) * 5 / 9, 2)
                        data[k_c] = val_c
                        # print(f"Converted {k_f} ({val_f}) to {k_c} ({val_c})")

        temp = safe_float(data.get('temperature_C'))
        humidity = safe_float(data.get('humidity'))
        raw_json = json.dumps(data)

        cursor.execute("""
            INSERT INTO sensors_data 
            (sensor_id, brand, model, channel, battery_ok, temperature_c, humidity, raw_json) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(sensor_id), brand, model, channel, battery_ok, temp, humidity, raw_json))
        conn.commit()
        
        conn.commit()
        
        # Consistent emission using the utility
        all_sensors = get_latest_sensors(conn)
        print(f"Backend: Emitting {len(all_sensors)} sensors via Socket.IO")
        socketio.emit('new_data', all_sensors)
        
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

        # Try to connect/reconnect if needed
        if broker and broker != last_broker:
            try:
                print(f"MQTT Subscriber: Connecting to {broker}:{port}...")
                if user and pw:
                    client.username_pw_set(user, pw)
                client.disconnect()
                client.connect(broker, port, 60)
                last_broker = broker
            except Exception as e:
                print(f"MQTT Subscriber Error: {e}")
        
        # In eventlet, we should use a shorter timeout or loop_start
        # but since we are in a background task, loop(0.1) + sleep is okay
        if last_broker:
            client.loop(timeout=0.1)
        eventlet.sleep(1) # Use eventlet.sleep for better yielding

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
            topic = get_setting('mqtt_topic', 'rtl_433[/model][/id]')

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
                "-M", "time:iso8601",
                "-s", get_setting('sdr_samplerate', '1024k')
            ]

            # Sensitivity and Noise settings
            if get_setting('sdr_autolevel', '1') == '1':
                cmd.extend(["-Y", "autolevel", "-Y", "squelch"])
            
            if get_setting('sdr_noise', '1') == '1':
                cmd.extend(["-M", "noise"])
            
            # Optional MQTT Output
            if broker:
                mqtt_dest = f"mqtt://{broker}:{port}"
                if user: mqtt_dest += f",user={user}"
                if pw: mqtt_dest += f",pass={pw}"
                # Use 'events=' as specified in the implementation plan
                mqtt_dest += f",retain=0,events={topic}"
                cmd.extend(["-F", mqtt_dest])

            # Handle protocols safely
            p_clean = protocols.strip().lower()
            if p_clean and p_clean not in ["all", "none"]:
                for p_item in protocols.split(','):
                    if p_item.strip():
                        cmd.extend(["-R", p_item.strip()])
            elif p_clean == "all":
                cmd.extend(["-R", "all"])
            else:
                if str(get_setting('sdr_starred', '0')) == '1':
                    cmd.extend(["-R", "all"])
            
            print(f"Starting SDR: {' '.join(cmd)}")
            p = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True,
                env=os.environ.copy()
            )
            sdr_process = p # Set global for restart_sdr
            
            for line in p.stdout:
                line = line.strip()
                if not line: continue
                
                if line.startswith('{') and line.endswith('}'):
                    try:
                        data = json.loads(line)
                        save_to_db(data)
                        continue
                    except json.JSONDecodeError:
                        pass
                print(f"SDR Engine: {line}")
            
            p.wait()
            rc = p.returncode
            if rc is not None and rc != 0:
                print(f"SDR Engine FATAL: Engine exited with code {rc}.")
        except Exception as e:
            print(f"SDR Worker Error: {e}")
        
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

@app.route('/api/data')
def get_sensor_data():
    try:
        rows = get_latest_sensors()
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

@app.route('/api/aliases', methods=['GET', 'POST'])
def manage_aliases():
    if request.method == 'GET':
        conn = get_db_connection()
        rows = conn.execute("SELECT * FROM sensor_aliases").fetchall()
        conn.close()
        return jsonify({row['sensor_id']: row['alias'] for row in rows})
    
    data = request.json
    sensor_id = data.get('sensor_id')
    alias = data.get('alias')
    
    conn = get_db_connection()
    if alias:
        conn.execute("INSERT OR REPLACE INTO sensor_aliases (sensor_id, alias) VALUES (?, ?)", (str(sensor_id), alias))
    else:
        conn.execute("DELETE FROM sensor_aliases WHERE sensor_id = ?", (str(sensor_id),))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    init_db()
    # Use socketio.start_background_task for better compatibility with eventlet
    socketio.start_background_task(sdr_worker)
    socketio.start_background_task(mqtt_subscriber)
    socketio.run(app, host='0.0.0.0', port=5000)
