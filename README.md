# 📡 EtherSpy-433

[![version](https://img.shields.io/badge/version-2026.02.21-blue.svg)](https://github.com/Minglarn/EtherSpy-433)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![status](https://img.shields.io/badge/status-active-brightgreen.svg)](https://github.com/Minglarn/EtherSpy-433)
[![docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

**Premium SDR Monitoring stack for 433 MHz devices.** Optimized for high information density, real-time updates via WebSockets, and maximum signal sensitivity.

## Key Features
- **Real-Time Dashboard**: Live updates using Socket.IO (no polling).
- **Dense Layout**: 2-column metric display and collapsible cards for managing many sensors.
- **Enhanced Sensitivity**: Supports `-Y autolevel` and `-Y squelch` to catch weak signals.
- **Starred Protocols**: Option to enable experimental `rtl_433` decoders.
- **Standalone Architecture**: Single Docker container with Flask backend and SQLite storage.

## Hardware
- **Receiver**: RTL-SDR v4
- **Antenna**: Moonraker Discone

## Quick Start (Docker)

### 1. Blacklist DVB-T Drivers (Host Machine)
On Linux systems, prevent the kernel from claiming the RTL-SDR:
```bash
sudo nano /etc/modprobe.d/blacklist-rtl.conf
```
Add:
```text
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
```
Reboot the host.

### 2. Startup with Docker Compose
Create a `docker-compose.yml` file with the following content:

```yaml
services:
  etherspy:
    image: ghcr.io/minglarn/etherspy-433/backend:latest
    container_name: etherspy-app
    restart: always
    privileged: true
    ports:
      - "5000:5000"
    devices:
      - "/dev/bus/usb:/dev/bus/usb"
    environment:
      - TZ=Europe/Stockholm
      - DB_PATH=/app/data/etherspy.db
      - PYTHONUNBUFFERED=1
    volumes:
      - ./data:/app/data
```

Run the stack:
```bash
docker compose up -d
```

### 3. Access the UI
Open [http://localhost:5000](http://localhost:5000) in your browser. Configure your MQTT broker and SDR frequency in the **Settings** modal.

## Project Structure
- `app.py`: Core backend, SDR process management, and API.
- `dashboard/`: Premium HTML5/JS frontend (Dense & Collapsible).
- `data/`: Persistent SQLite storage (`etherspy.db`).
- `Dockerfile`: Multi-stage build for the full stack.
