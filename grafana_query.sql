-- Grafana SQL Query: Average Temperature per Sensor ID (Last 24 Hours)
-- Set the "Time series" format in Grafana and use "sensor_id" as the metric/label.

SELECT
    timestamp AS "time",
    temperature_c AS "Temperature (°C)",
    sensor_id AS "metric"
FROM sensors_data
WHERE
    timestamp >= NOW() - INTERVAL 24 HOUR
ORDER BY timestamp ASC;

-- For a table with averages grouped by hour:
/*
SELECT
    DATE_FORMAT(timestamp, '%Y-%m-%d %H:00:00') AS "time",
    sensor_id,
    AVG(temperature_c) AS avg_temp
FROM sensors_data
WHERE
    timestamp >= NOW() - INTERVAL 24 HOUR
GROUP BY 1, 2
ORDER BY 1 ASC;
*/
