import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='dashboard')
CORS(app)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'mariadb')
DB_NAME = os.getenv('DB_NAME', 'etherspy')
DB_USER = os.getenv('DB_USER', 'dbuser')
DB_PASS = os.getenv('DB_PASS', 'dbpassword')

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
        print(f"Error connecting to MariaDB: {e}")
        return None

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
    app.run(host='0.0.0.0', port=5000)
