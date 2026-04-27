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


def _read_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


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


def _read_sensor_thresholds() -> dict[str, float]:
    raw_thresholds = os.getenv("SPECKLE_SENSOR_THRESHOLDS", "")
    thresholds: dict[str, float] = {}
    for item in raw_thresholds.split(","):
        entry = item.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValueError(
                "SPECKLE_SENSOR_THRESHOLDS entries must look like "
                "'temperature=0.5,humidity=2'"
            )
        sensor_type, raw_value = entry.split("=", 1)
        thresholds[sensor_type.strip()] = float(raw_value.strip())
    return thresholds


def _extract_numeric_value(payload: Any) -> float | None:
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        return float(payload)
    if isinstance(payload, dict):
        for key in ("value", "state", "reading"):
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
    if isinstance(payload, str):
        try:
            return float(payload)
        except ValueError:
            return None
    return None


def _payload_signature(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return str(payload)


def _read_json_file(path: str) -> Any:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


@dataclass(slots=True)
class SensorMapEntry:
    sensor_id: str
    room_id: str
    level_id: str
    building_id: str
    speckle_element_id: str
    anchor_type: str | None = None
    anchor_category: str | None = None
    application_id: str | None = None
    speckle_model_id: str | None = None
    topic: str | None = None
    device_id: str | None = None
    sensor_type: str | None = None
    room_name: str | None = None
    zone_id: str | None = None
    zone_name: str | None = None
    tags: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SensorMapEntry":
        required = [
            "sensor_id",
            "room_id",
            "level_id",
            "building_id",
            "speckle_element_id",
        ]
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(
                "Sensor map entry is missing required keys: "
                + ", ".join(sorted(missing))
            )
        return cls(
            sensor_id=str(data["sensor_id"]),
            room_id=str(data["room_id"]),
            level_id=str(data["level_id"]),
            building_id=str(data["building_id"]),
            speckle_element_id=str(data["speckle_element_id"]),
            anchor_type=data.get("anchor_type"),
            anchor_category=data.get("anchor_category"),
            application_id=data.get("application_id"),
            speckle_model_id=data.get("speckle_model_id"),
            topic=data.get("topic"),
            device_id=data.get("device_id"),
            sensor_type=data.get("sensor_type"),
            room_name=data.get("room_name"),
            zone_id=data.get("zone_id"),
            zone_name=data.get("zone_name"),
            tags=list(data["tags"]) if isinstance(data.get("tags"), list) else None,
        )


def _read_sensor_map_entries() -> list[SensorMapEntry]:
    map_file = os.getenv("SPECKLE_SENSOR_MAP_FILE")
    if not map_file:
        return []
    raw_entries = _read_json_file(map_file)
    if not isinstance(raw_entries, list):
        raise ValueError("SPECKLE_SENSOR_MAP_FILE must contain a JSON array.")
    return [SensorMapEntry.from_dict(entry) for entry in raw_entries]


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
    min_send_interval_seconds: float = 0.0
    skip_duplicate_payloads: bool = True
    sensor_thresholds: dict[str, float] | None = None
    sensor_map_entries: list[SensorMapEntry] | None = None

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
            min_send_interval_seconds=_read_float_env(
                "SPECKLE_MIN_SEND_INTERVAL_SECONDS", 0.0
            ),
            skip_duplicate_payloads=_read_bool_env(
                "SPECKLE_SKIP_DUPLICATE_PAYLOADS", default=True
            ),
            sensor_thresholds=_read_sensor_thresholds(),
            sensor_map_entries=_read_sensor_map_entries(),
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
        self.last_sent_at_by_topic: dict[str, float] = {}
        self.last_payload_signature_by_topic: dict[str, str] = {}
        self.last_numeric_value_by_topic: dict[str, float] = {}
        self.sensor_map_by_topic: dict[str, SensorMapEntry] = {}
        self.sensor_map_by_device_and_type: dict[tuple[str, str], SensorMapEntry] = {}
        self._index_sensor_map_entries()

    def _index_sensor_map_entries(self) -> None:
        for entry in self.settings.sensor_map_entries or []:
            if entry.topic:
                self.sensor_map_by_topic[entry.topic] = entry
            if entry.device_id and entry.sensor_type:
                self.sensor_map_by_device_and_type[
                    (entry.device_id, entry.sensor_type)
                ] = entry

    def get_sensor_map_entry(self, topic: str) -> SensorMapEntry | None:
        if topic in self.sensor_map_by_topic:
            return self.sensor_map_by_topic[topic]
        metadata = parse_topic_metadata(topic)
        return self.sensor_map_by_device_and_type.get(
            (metadata["device_id"], metadata["sensor_type"])
        )

    def should_send(self, topic: str, payload: Any) -> tuple[bool, str]:
        now = time.time()
        elapsed = now - self.last_sent_at_by_topic.get(topic, 0.0)
        payload_signature = _payload_signature(payload)
        previous_signature = self.last_payload_signature_by_topic.get(topic)
        metadata = parse_topic_metadata(topic)
        sensor_type = metadata["sensor_type"]
        numeric_value = _extract_numeric_value(payload)
        previous_numeric = self.last_numeric_value_by_topic.get(topic)
        threshold = (self.settings.sensor_thresholds or {}).get(sensor_type)

        if topic not in self.last_sent_at_by_topic:
            return True, "first message for topic"

        if (
            threshold is not None
            and numeric_value is not None
            and previous_numeric is not None
            and abs(numeric_value - previous_numeric) >= threshold
        ):
            return True, f"value changed by threshold >= {threshold}"

        if (
            self.settings.skip_duplicate_payloads
            and previous_signature == payload_signature
        ):
            if self.settings.min_send_interval_seconds <= 0:
                return False, "duplicate payload"
            if elapsed < self.settings.min_send_interval_seconds:
                return False, "duplicate payload inside minimum interval"

        if (
            self.settings.min_send_interval_seconds > 0
            and elapsed < self.settings.min_send_interval_seconds
        ):
            return False, "inside minimum interval"

        return True, "minimum interval elapsed"

    def remember_sent_payload(self, topic: str, payload: Any) -> None:
        self.last_sent_at_by_topic[topic] = time.time()
        self.last_payload_signature_by_topic[topic] = _payload_signature(payload)
        numeric_value = _extract_numeric_value(payload)
        if numeric_value is not None:
            self.last_numeric_value_by_topic[topic] = numeric_value

    def send_to_speckle(self, topic: str, payload: Any) -> None:
        obj = Base()
        metadata = parse_topic_metadata(topic)
        map_entry = self.get_sensor_map_entry(topic)
        timestamp = time.time()
        obj["topic"] = topic
        obj["raw_topic"] = metadata["raw_topic"]
        obj["device_id"] = metadata["device_id"]
        obj["sensor_type"] = metadata["sensor_type"]
        obj["unit"] = metadata["unit"]
        obj["payload"] = payload if isinstance(payload, dict) else {"value": payload}
        obj["timestamp"] = timestamp
        obj["timestamp_local"] = format_timestamp_local(timestamp)
        obj["value"] = _extract_numeric_value(payload)
        obj["type"] = "telemetry"

        if map_entry:
            obj["sensor_id"] = map_entry.sensor_id
            obj["room_id"] = map_entry.room_id
            obj["level_id"] = map_entry.level_id
            obj["building_id"] = map_entry.building_id
            obj["speckle_element_id"] = map_entry.speckle_element_id
            if map_entry.anchor_type:
                obj["anchor_type"] = map_entry.anchor_type
            if map_entry.anchor_category:
                obj["anchor_category"] = map_entry.anchor_category
            if map_entry.application_id:
                obj["application_id"] = map_entry.application_id
            obj["speckle_model_id"] = (
                map_entry.speckle_model_id or self.settings.speckle_model_id
            )
            if map_entry.room_name:
                obj["room_name"] = map_entry.room_name
            if map_entry.zone_id:
                obj["zone_id"] = map_entry.zone_id
            if map_entry.zone_name:
                obj["zone_name"] = map_entry.zone_name
            if map_entry.tags:
                obj["tags"] = map_entry.tags

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
        self.remember_sent_payload(topic, payload)
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
            should_send, reason = self.should_send(topic, payload)
            if not should_send:
                LOGGER.info("Skipped topic '%s': %s", topic, reason)
                return
            self.send_to_speckle(topic, payload)
            LOGGER.info("Forwarded topic '%s': %s", topic, reason)
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
