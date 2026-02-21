<?php
/**
 * EtherSpy-433 Data API
 * Fetches the latest sensor readings from MariaDB
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

// Database configuration - Update with your credentials
$host = '127.0.0.1'; // Or service name if in Docker
$db   = 'etherspy';
$user = 'dbuser';
$pass = 'dbpassword';
$charset = 'utf8mb4';

$dsn = "mysql:host=$host;dbname=$db;charset=$charset";
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $user, $pass, $options);
} catch (\PDOException $e) {
    echo json_encode(['error' => 'Connection failed: ' . $e->getMessage()]);
    exit;
}

// Fetch the latest reading for each sensor
$query = "SELECT s1.* 
          FROM sensors_data s1
          INNER JOIN (
              SELECT sensor_id, MAX(timestamp) as max_ts
              FROM sensors_data
              GROUP BY sensor_id
          ) s2 ON s1.sensor_id = s2.sensor_id AND s1.timestamp = s2.max_ts
          ORDER BY s1.timestamp DESC";

$stmt = $pdo->query($query);
$results = $stmt->fetchAll();

echo json_encode($results);
?>
