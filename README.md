# EtherSpy-433

SDR Project for monitoring 433 MHz devices (Weather stations, sensors, etc.) using RTL-SDR v4, Docker, and Node-RED.

## Hardware
- **Receiver:** RTL-SDR v4
- **Antenna:** Moonraker Discone

## Components
1. **Docker:** `rtl_433` service publishing to MQTT.
2. **Database:** MariaDB/MySQL for storage.
3. **Node-RED:** Integration logic.
4. **Grafana:** Visualization.

## Setup Instructions

### 1. Blacklist DVB-T Drivers (Host Machine)
To use the RTL-SDR v4 with Docker, you must prevent the host operating system from loading the default DVB-T drivers.

On Linux/Debian/Ubuntu:
1. Create a blacklist file:
   ```bash
   sudo nano /etc/modprobe.d/blacklist-rtl.conf
   ```
2. Add the following lines:
   ```text
   blacklist dvb_usb_rtl28xxu
   blacklist rtl2832
   blacklist rtl2830
   ```
3. Save and reboot the host.

### 2. Database Schema
Run the provided `init.sql` on your MariaDB/MySQL server to create the `sensors_data` table.

### 3. Docker Compose
Modify `docker-compose.yml` if your MQTT broker IP or port differs from `192.168.1.125`.
Start the service:
```bash
docker-compose up -d
```

### 4. Node-RED Integration
1. Add an `mqtt in` node subscribing to `rtl_433/+/events`.
2. Connect it to a `function` node and paste the code from `nodered_function.js`.
3. Connect the function node to a `mysql` or `mariadb` node (configured with your DB credentials).

### 5. Web UI & Visualization
- **Grafana:** Access at `http://localhost:3000` (User: `admin` / Pass: `admin`). Use the query in `grafana_query.sql`.
- **Premium Dashboard:** Open `dashboard/index.html` in your browser.
  - Note: Configure `api/data.php` with your database credentials to enable live data.

## Project Structure
- `docker-compose.yml`: Services for SDR and Grafana.
- `init.sql`: Database schema.
- `nodered_function.js`: Integration logic.
- `dashboard/`: Custom Web UI assets.
- `api/`: Backend data interface.
