# speckle_arc

Starter project for `speckle_arc`.

## Architecture overview

Current system flow:

```text
IoT Devices
  -> MQTT Broker (Mosquitto add-on on Home Assistant)
  -> Home Assistant integrations
  -> Speckle
```

Authoritative reference:

- [IoT Architecture Diagram.html](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/docs/IoT%20Architecture%20Diagram.html)

According to that diagram:

- IoT devices publish data to MQTT
- The MQTT broker is part of the Home Assistant side of the system
- Home Assistant subscribes to MQTT and can also send commands back
- Zigbee devices may flow into Home Assistant directly through Zigbee2MQTT or ZHA
- Home Assistant pushes data to Speckle through a Speckle integration
- Users interact through Home Assistant dashboards and Speckle viewers

In this repository:

- [docker-compose.yml](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/docker-compose.yml) provides the Speckle deployment
- [src/speckle_arc/mqtt_to_speckle.py](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/src/speckle_arc/mqtt_to_speckle.py) is an optional Python bridge that subscribes directly to the MQTT broker endpoint exposed from the Home Assistant side

## Project structure

```text
speckle_arc/
|- src/
|  \- speckle_arc/
|     |- __init__.py
|     \- mqtt_to_speckle.py
|- docker-compose.yml
|- .env.example
|- .gitignore
|- pyproject.toml
|\- README.md
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Environment configuration

1. Copy `.env.example` to `.env`
2. Fill in the real values for your environment
3. Keep `.env` local only and never commit it

```powershell
Copy-Item .env.example .env
```

## Run

MQTT to Speckle bridge:

```powershell
speckle-arc-mqtt
```

You can also run modules directly:

```powershell
python -m speckle_arc.mqtt_to_speckle
```

## Docker deployment

The repository now includes [docker-compose.yml](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/docker-compose.yml) for running Speckle services on an Ubuntu server with Docker Compose.

Typical flow:

```powershell
Copy-Item .env.example .env
docker compose up -d
```

Before starting, update the Docker-related values in `.env`, especially:

- `SPECKLE_PUBLIC_HOST`
- `SPECKLE_CANONICAL_URL`
- `SPECKLE_FRONTEND_ORIGIN`
- `SPECKLE_API_ORIGIN`
- `SPECKLE_SESSION_SECRET`
- `SPECKLE_POSTGRES_PASSWORD`
- `SPECKLE_S3_SECRET_KEY`

For a fuller Ubuntu walkthrough, see [docs/ubuntu-deploy.md](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/docs/ubuntu-deploy.md).

If you want the optional MQTT bridge to start automatically on Ubuntu boot, use the systemd unit at [speckle-arc-mqtt.service](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/deploy/systemd/speckle-arc-mqtt.service).

## Deployment roles

- `Home Assistant host`: MQTT broker access and integrations
- `Speckle host`: Speckle services

## Notes

- `.env` is ignored by git and should contain real secrets only on your machine.
- `.env.example` is safe to commit and documents the required configuration.
