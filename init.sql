CREATE TABLE IF NOT EXISTS `sensors_data` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `sensor_id` VARCHAR(50),
    `brand` VARCHAR(100),
    `model` VARCHAR(100),
    `channel` VARCHAR(10),
    `battery_ok` TINYINT(1),
    `temperature_c` DECIMAL(5, 2),
    `humidity` DECIMAL(5, 2),
    `raw_json` JSON,
    INDEX (`sensor_id`),
    INDEX (`timestamp`)
);
