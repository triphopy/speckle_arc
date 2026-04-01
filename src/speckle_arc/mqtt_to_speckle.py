import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt
from gql import gql
from paho.mqtt.client import CallbackAPIVersion
from dotenv import load_dotenv
from specklepy.api.client import SpeckleClient
from specklepy.api.operations import send
from specklepy.objects.base import Base
from specklepy.transports.server import ServerTransport

os.environ["DISABLE_SPECKLE_ANALYTICS"] = "true"

LOGGER = logging.getLogger(__name__)


def load_environment() -> None:
    env_candidates = [
        os.getenv("SPECKLE_ARC_ENV_FILE"),
        ".env",
        "/home/system/.config/speckle-stack.env",
    ]
    for env_path in env_candidates:
        if env_path and os.path.exists(env_path):
            load_dotenv(env_path, override=False)
            return


def _read_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_local_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("SPECKLE_ARC_TIMEZONE", "Asia/Bangkok"))


def format_timestamp_local(timestamp: Any) -> str:
    if not isinstance(timestamp, (int, float)):
        return str(timestamp)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
        get_local_timezone()
    ).isoformat()


def parse_topic_metadata(topic: str) -> dict[str, Any]:
    parts = topic.split("/")
    device_id = parts[0] if parts else ""
    sensor_type = parts[2] if len(parts) >= 3 else ""
    unit_map = {
        "temperature": "C",
        "humidity": "%",
        "pm1_0": "ug/m3",
        "pm25": "ug/m3",
        "pm10": "ug/m3",
    }
    return {
        "raw_topic": topic,
        "device_id": device_id,
        "sensor_type": sensor_type,
        "unit": unit_map.get(sensor_type),
    }


def _read_topics() -> list[str]:
    raw_topics = os.getenv("MQTT_TOPICS")
    if not raw_topics:
        raise ValueError("Missing required environment variable: MQTT_TOPICS")

    topics = [topic.strip() for topic in raw_topics.split(",") if topic.strip()]
    if not topics:
        raise ValueError("MQTT_TOPICS is set but does not contain any valid topics.")
    return topics


@dataclass(slots=True)
class Settings:
    speckle_host: str
    speckle_token: str
    speckle_project_id: str
    speckle_model_id: str
    speckle_use_ssl: bool
    mqtt_broker: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_topics: list[str]
    mqtt_keepalive: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        required_keys = {
            "SPECKLE_HOST": os.getenv("SPECKLE_HOST"),
            "SPECKLE_TOKEN": os.getenv("SPECKLE_TOKEN"),
            "SPECKLE_PROJECT_ID": os.getenv("SPECKLE_PROJECT_ID"),
            "SPECKLE_MODEL_ID": os.getenv("SPECKLE_MODEL_ID"),
            "MQTT_BROKER": os.getenv("MQTT_BROKER"),
        }
        missing_keys = [key for key, value in required_keys.items() if not value]
        if missing_keys:
            missing_list = ", ".join(sorted(missing_keys))
            raise ValueError(
                f"Missing required environment variables: {missing_list}"
            )

        return cls(
            speckle_host=required_keys["SPECKLE_HOST"] or "",
            speckle_token=required_keys["SPECKLE_TOKEN"] or "",
            speckle_project_id=required_keys["SPECKLE_PROJECT_ID"] or "",
            speckle_model_id=required_keys["SPECKLE_MODEL_ID"] or "",
            speckle_use_ssl=_read_bool_env("SPECKLE_USE_SSL", default=False),
            mqtt_broker=required_keys["MQTT_BROKER"] or "",
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_username=os.getenv("MQTT_USERNAME"),
            mqtt_password=os.getenv("MQTT_PASSWORD"),
            mqtt_topics=_read_topics(),
            mqtt_keepalive=int(os.getenv("MQTT_KEEPALIVE", "60")),
        )


class MqttToSpeckleBridge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.speckle_client = SpeckleClient(
            host=settings.speckle_host,
            use_ssl=settings.speckle_use_ssl,
        )
        self.speckle_client.authenticate_with_token(settings.speckle_token)
        self.transport = ServerTransport(
            client=self.speckle_client,
            stream_id=settings.speckle_project_id,
        )

    def send_to_speckle(self, topic: str, payload: Any) -> None:
        obj = Base()
        metadata = parse_topic_metadata(topic)
        obj["topic"] = topic
        obj["raw_topic"] = metadata["raw_topic"]
        obj["device_id"] = metadata["device_id"]
        obj["sensor_type"] = metadata["sensor_type"]
        obj["unit"] = metadata["unit"]
        obj["payload"] = payload if isinstance(payload, dict) else {"value": payload}
        obj["timestamp"] = time.time()
        obj["timestamp_local"] = format_timestamp_local(obj["timestamp"])

        obj_id = send(obj, [self.transport])
        message = f"IoT: {topic}"
        query = gql(
            f"""
            mutation {{
              versionMutations {{
                create(
                  input: {{
                    objectId: {json.dumps(obj_id)},
                    modelId: {json.dumps(self.settings.speckle_model_id)},
                    projectId: {json.dumps(self.settings.speckle_project_id)},
                    message: {json.dumps(message)}
                  }}
                ) {{
                  id
                  message
                }}
              }}
            }}
            """
        )
        result = self.speckle_client.execute_query(query)
        version = result["versionMutations"]["create"]
        LOGGER.info("Sent topic '%s' to Speckle version %s", topic, version["id"])

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        LOGGER.info("Connected to MQTT broker with reason code %s", reason_code)
        for topic in self.settings.mqtt_topics:
            client.subscribe(topic)
            LOGGER.info("Subscribed to topic '%s'", topic)

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        payload_text = msg.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(payload_text)
        except JSONDecodeError:
            payload = payload_text

        LOGGER.info("Received message on '%s': %s", topic, payload)
        try:
            self.send_to_speckle(topic, payload)
        except Exception:
            LOGGER.exception("Failed to forward topic '%s' to Speckle", topic)


def build_mqtt_client(bridge: MqttToSpeckleBridge) -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    if bridge.settings.mqtt_username:
        client.username_pw_set(
            bridge.settings.mqtt_username,
            bridge.settings.mqtt_password,
        )
    client.on_connect = bridge.on_connect
    client.on_message = bridge.on_message
    return client


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    load_environment()
    configure_logging()

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        LOGGER.error("%s", exc)
        raise SystemExit(1) from exc

    bridge = MqttToSpeckleBridge(settings)
    mqtt_client = build_mqtt_client(bridge)

    LOGGER.info("Starting MQTT to Speckle bridge")
    mqtt_client.connect(
        settings.mqtt_broker,
        settings.mqtt_port,
        settings.mqtt_keepalive,
    )
    mqtt_client.loop_forever()


if __name__ == "__main__":
    main()
