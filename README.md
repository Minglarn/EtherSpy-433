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

### 4. Standalone Backend (Python/Flask)
The backend is now a standalone Python/Flask application containerized within the Docker stack. It serves the Premium Dashboard and the data API.

### 5. Web UI & Visualization
- **Premium Dashboard:** Access at `http://localhost:5000`. This is the primary standalone interface for viewing live sensor data.

## Project Structure
- `docker-compose.yml`: Full stack orchestration (SDR, Backend, DB, MQTT).
- `app.py`: Flask backend and static file server.
- `Dockerfile`: Multi-stage build for the standalone backend.
- `dashboard/`: Custom Web UI assets.
- `init.sql`: MariaDB schema.
- `mosquitto.conf`: MQTT broker configuration.
