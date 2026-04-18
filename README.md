# Viessmann Solar Monitor

This repository is split into two optional parts:

- `backend/`: SEMS polling, local HTTP API, MQTT/Home Assistant bridge
- `ui/`: React dashboard

## Backend only

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
python3 backend/solar_api_server.py
```

The backend serves:

- `http://127.0.0.1:8765/api/snapshot`
- `http://127.0.0.1:8765/api/status`

## UI + backend in development

```bash
cd ui
npm install
npm run dev
```

This starts:

- backend on `127.0.0.1:8765`
- UI on `127.0.0.1:1420`

## Docker

```bash
docker compose up --build
```

Then open:

```bash
http://localhost:8080
```

For local MQTT tests, Docker Compose also starts a Mosquitto broker on:

```bash
mqtt://localhost:1883
```

## MQTT for Home Assistant

Set these values in `.env`:

- `MQTT_ENABLED=true`
- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`

Optional:

- `MQTT_BASE_TOPIC`
- `MQTT_DISCOVERY_PREFIX`
- `MQTT_DEVICE_NAME`
- `MQTT_DEVICE_ID`

Home Assistant MQTT discovery is used automatically.

### Quick local MQTT test with Docker

If you use the bundled Docker broker, these values are enough:

```env
MQTT_ENABLED=true
MQTT_HOST=mqtt
MQTT_PORT=1883
```

From the host machine, the same broker is reachable at:

```bash
localhost:1883
```
