/**
 * Node-RED Function Node Logic for EtherSpy-433
 * 
 * Input: MQTT message from rtl_433/+/events
 * Output: SQL Query object for MySQL/MariaDB node
 */

const data = msg.payload;

// Ensure we have valid data
if (!data || typeof data !== 'object') {
    return null;
}

// Map fields to SQL parameters
// Note: We use the sensor ID as the unique identifier
const sensorId = data.id || 'unknown';
const brand = data.brand || 'Generic';
const model = data.model || 'Unknown';
const channel = data.channel || '0';
const batteryOk = data.battery_ok === "OK" || data.battery_ok === 1 ? 1 : 0;
const temp = data.temperature_C !== undefined ? data.temperature_C : null;
const humidity = data.humidity !== undefined ? data.humidity : null;
const rawJson = JSON.stringify(data);

// Construct the SQL INSERT statement
// Using prepared statement placeholders (?) is safer
msg.topic = "INSERT INTO sensors_data (sensor_id, brand, model, channel, battery_ok, temperature_c, humidity, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)";
msg.payload = [sensorId, brand, model, channel, batteryOk, temp, humidity, rawJson];

return msg;
