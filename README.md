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

For long-lived server deployments, you can also keep the real env file outside the repo.
The CLI tools will try these locations in order:

- `SPECKLE_ARC_ENV_FILE`
- `.env` in the project root
- `/home/system/.config/speckle-stack.env`

### Cloud and self-hosted profiles

This project supports both Speckle Cloud and self-hosted Speckle without code changes.
The Python tools read the same core variables in both cases:

- `SPECKLE_HOST`
- `SPECKLE_TOKEN`
- `SPECKLE_PROJECT_ID`
- `SPECKLE_MODEL_ID`
- `SPECKLE_USE_SSL`

Use these example files as starting points:

- [\.env.cloud.example](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/.env.cloud.example)
- [\.env.selfhosted.example](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/.env.selfhosted.example)

Recommended setup:

```powershell
Copy-Item .env.cloud.example .env.cloud
Copy-Item .env.selfhosted.example .env.selfhosted
```

Run against Speckle Cloud:

```powershell
$env:SPECKLE_ARC_ENV_FILE=".env.cloud"
speckle-arc-mqtt
```

Run against self-hosted Speckle:

```powershell
$env:SPECKLE_ARC_ENV_FILE=".env.selfhosted"
speckle-arc-mqtt
```

Notes:

- Speckle Cloud should usually use `SPECKLE_USE_SSL=true`
- Self-hosted deployments may use `false` or `true` depending on whether TLS is enabled
- The self-hosted Docker values such as `SPECKLE_PUBLIC_HOST` and `SPECKLE_S3_BUCKET` are not needed for Speckle Cloud

## Run

MQTT to Speckle bridge:

```powershell
speckle-arc-mqtt
```

Read the latest value from Speckle:

```powershell
speckle-arc-latest
```

Read multiple recent values from Speckle:

```powershell
speckle-arc-recent 5
```

You can also run modules directly:

```powershell
python -m speckle_arc.mqtt_to_speckle
python -m speckle_arc.speckle_latest
```

The CLI tools print timestamps in the local timezone from `SPECKLE_ARC_TIMEZONE`.
If not set, they default to `Asia/Bangkok`.

### Rate limiting sensor updates

To avoid creating a new Speckle version for every MQTT message, the bridge supports
three environment variables:

- `SPECKLE_MIN_SEND_INTERVAL_SECONDS`: minimum seconds between sends for the same topic
- `SPECKLE_SKIP_DUPLICATE_PAYLOADS`: skip unchanged payloads
- `SPECKLE_SENSOR_THRESHOLDS`: send immediately when a numeric value changes by at least the configured amount for that sensor type

Example:

```powershell
SPECKLE_MIN_SEND_INTERVAL_SECONDS=60
SPECKLE_SKIP_DUPLICATE_PAYLOADS=true
SPECKLE_SENSOR_THRESHOLDS=temperature=0.5,humidity=2,pm25=5
```

With that example, the bridge will:

- skip duplicate payloads
- send at most once every 60 seconds per MQTT topic
- still send immediately if temperature changes by `0.5`, humidity by `2`, or PM2.5 by `5`

### Sensor-to-room mapping

To attach telemetry to a room or model element, point the bridge at a JSON mapping file:

```powershell
SPECKLE_SENSOR_MAP_FILE=config/sensor_room_map.json
```

Use [config/sensor_room_map.example.json](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/config/sensor_room_map.example.json) as the starting point, then copy it to `config/sensor_room_map.json`.

Each entry should include:

- `sensor_id`
- `building_id`
- `level_id`
- `room_id`
- `speckle_element_id`

Recommended extra field:

- `application_id`: the source application element id shown in Speckle, which is usually more stable across model reimports than the Speckle object `id`
- `anchor_type`: what the sensor is attached to in the model, for example `floor`, `door`, `wall`, or `room`
- `anchor_category`: the model category, for example `Floors`, `Doors`, or `Walls`

You can match on either:

- `topic`: exact MQTT topic match
- or `device_id` + `sensor_type`

When a mapping entry is found, the bridge adds these fields to the Speckle object:

- `sensor_id`
- `building_id`
- `level_id`
- `room_id`
- `room_name`
- `zone_id`
- `zone_name`
- `anchor_type`
- `anchor_category`
- `speckle_element_id`
- `application_id`
- `speckle_model_id`
- `tags`

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
