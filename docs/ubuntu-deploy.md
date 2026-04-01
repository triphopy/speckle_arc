# Ubuntu Deployment Guide

This guide explains how to deploy the Speckle stack from this repository on an Ubuntu server with Docker Compose.

## Architecture overview

The current project flow is:

```text
IoT Devices
  -> MQTT Broker (Mosquitto add-on on Home Assistant)
  -> Home Assistant integrations
  -> Speckle
```

Authoritative reference:

- [IoT Architecture Diagram.html](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/docs/IoT%20Architecture%20Diagram.html)

Deployment roles:

- `Home Assistant host` is the Home Assistant side of the system, including the MQTT broker endpoint and related device flows
- `Speckle host` runs the Speckle Docker stack

This guide focuses on the Ubuntu server that runs Speckle.

## 1. Server prerequisites

Recommended baseline:

- Ubuntu 22.04 LTS or newer
- A user with `sudo` access
- Docker Engine installed
- Docker Compose plugin installed
- Ports `3000`, `8080`, `9000`, and `9002` reachable as needed

Update the server first:

```bash
sudo apt update
sudo apt upgrade -y
```

## 2. Install Docker

If Docker is not installed yet:

```bash
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
```

Optional: allow the current user to run Docker without `sudo`:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

## 3. Get the project onto the server

Clone the repository:

```bash
git clone https://github.com/triphopy/speckle_arc.git
cd speckle_arc
```

If you are copying files manually, make sure at minimum these files exist on the server:

- `docker-compose.yml`
- `.env`

## 4. Prepare environment variables

Copy the example file if needed:

```bash
cp .env.example .env
```

Review and update the Docker-related settings inside `.env`:

- `SPECKLE_PUBLIC_HOST`
- `SPECKLE_CANONICAL_URL`
- `SPECKLE_FRONTEND_ORIGIN`
- `SPECKLE_API_ORIGIN`
- `SPECKLE_SESSION_SECRET`
- `SPECKLE_POSTGRES_PASSWORD`
- `SPECKLE_S3_ACCESS_KEY`
- `SPECKLE_S3_SECRET_KEY`
- `SPECKLE_S3_BUCKET`

Important:

- Replace the default example secrets before production use.
- If the server will be exposed publicly, use strong random values for `SPECKLE_SESSION_SECRET`, `SPECKLE_POSTGRES_PASSWORD`, and `SPECKLE_S3_SECRET_KEY`.
- If you change the host or port mapping, update the URL values to match.

## 5. Start the Speckle stack

Start all services in the background:

```bash
docker compose up -d
```

See running containers:

```bash
docker compose ps
```

Watch logs:

```bash
docker compose logs -f
```

To inspect one service only:

```bash
docker compose logs -f speckle-server
docker compose logs -f speckle-frontend
```

## 6. Optional Python bridge

The architecture diagram shows Home Assistant as the main component that connects MQTT data into Speckle.

This repository also contains an optional Python bridge at [mqtt_to_speckle.py](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/src/speckle_arc/mqtt_to_speckle.py). Use it only if you want a direct MQTT-to-Speckle path outside the Home Assistant integration flow. In that setup, the bridge subscribes to the MQTT broker endpoint exposed from the Home Assistant side.

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Run the bridge:

```bash
source .venv/bin/activate
speckle-arc-mqtt
```

Alternative direct module run:

```bash
source .venv/bin/activate
python -m speckle_arc.mqtt_to_speckle
```

Before starting the bridge, confirm `.env` contains the MQTT settings for the Home Assistant broker:

- `MQTT_BROKER=your-home-assistant-mqtt-host`
- `MQTT_PORT=1883`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TOPICS`

### Run the bridge as a systemd service

This repository includes a ready-made unit file at [speckle-arc-mqtt.service](C:/Users/jonew/Downloads/P_Kwan/speckle_arc/deploy/systemd/speckle-arc-mqtt.service).

Default assumptions in that file:

- project path: `/home/system/speckle-stack`
- virtual environment path: `/home/system/speckle-stack/.venv`
- service user: `system`

These values are already set in the included unit file. Edit them only if your server layout changes.

Copy the unit file into systemd:

```bash
sudo cp deploy/systemd/speckle-arc-mqtt.service /etc/systemd/system/speckle-arc-mqtt.service
```

Reload systemd and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable speckle-arc-mqtt.service
sudo systemctl start speckle-arc-mqtt.service
```

Check service status:

```bash
sudo systemctl status speckle-arc-mqtt.service
```

Follow logs:

```bash
sudo journalctl -u speckle-arc-mqtt.service -f
```

## 7. Verify the deployment

Check these endpoints from the server or another machine on the network:

- Speckle frontend: `http://YOUR_HOST:8080`
- Speckle server API: `http://YOUR_HOST:3000`
- MinIO API: `http://YOUR_HOST:9000`
- MinIO console: `http://YOUR_HOST:9002`

If you use your own host values in `.env`, verify the corresponding endpoints:

- `http://your-speckle-host:8080`
- `http://your-speckle-host:3000`
- `http://your-speckle-host:9000`
- `http://your-speckle-host:9002`

Also verify the bridge process:

- If you are using the optional Python bridge, it can connect to your MQTT broker host
- If you are using the optional Python bridge, it can create versions in Speckle on your Speckle host
- If you are not using the Python bridge, verify the Home Assistant to Speckle integration path instead

## 8. Common operations

Stop the stack:

```bash
docker compose down
```

Restart the stack:

```bash
docker compose restart
```

Pull newer images and recreate containers:

```bash
docker compose pull
docker compose up -d
```

If the bridge stops, restart it from the virtual environment:

```bash
source .venv/bin/activate
speckle-arc-mqtt
```

If you installed the systemd service, restart it with:

```bash
sudo systemctl restart speckle-arc-mqtt.service
```

## 9. Data persistence

This Compose file stores state in Docker volumes:

- `postgres_data`
- `redis_data`
- `minio_data`

These volumes persist across container restarts and `docker compose down` runs, as long as you do not remove volumes explicitly.

## 10. Firewall and networking notes

If Ubuntu firewall is enabled with `ufw`, allow the ports you need:

```bash
sudo ufw allow 8080/tcp
sudo ufw allow 3000/tcp
sudo ufw allow 9000/tcp
sudo ufw allow 9002/tcp
```

Only expose MinIO ports if you actually need direct access to them.

If you use the optional Python bridge, also confirm the Ubuntu server can reach your MQTT broker host on port `1883`.

## 11. Production recommendations

- Put Nginx or another reverse proxy in front of Speckle if the server will be accessed outside the local network.
- Use HTTPS instead of plain HTTP for public deployments.
- Rotate any credentials that were ever committed or shared in plain text.
- Back up Docker volumes regularly, especially PostgreSQL and MinIO data.
- If you rely on the optional Python bridge, run it with `systemd` or another process manager so it starts automatically on boot.
