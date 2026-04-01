import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from gql import gql
from specklepy.api.client import SpeckleClient
from specklepy.api.operations import receive
from specklepy.transports.server import ServerTransport

from speckle_arc.mqtt_to_speckle import (
    _read_bool_env,
    format_timestamp_local,
    load_environment,
)


@dataclass(slots=True)
class SpeckleSettings:
    host: str
    token: str
    project_id: str
    model_id: str
    use_ssl: bool

    @classmethod
    def from_env(cls) -> "SpeckleSettings":
        required_keys = {
            "SPECKLE_HOST": os.getenv("SPECKLE_HOST"),
            "SPECKLE_TOKEN": os.getenv("SPECKLE_TOKEN"),
            "SPECKLE_PROJECT_ID": os.getenv("SPECKLE_PROJECT_ID"),
            "SPECKLE_MODEL_ID": os.getenv("SPECKLE_MODEL_ID"),
        }
        missing_keys = [key for key, value in required_keys.items() if not value]
        if missing_keys:
            raise ValueError(
                "Missing required environment variables: "
                + ", ".join(sorted(missing_keys))
            )

        return cls(
            host=required_keys["SPECKLE_HOST"] or "",
            token=required_keys["SPECKLE_TOKEN"] or "",
            project_id=required_keys["SPECKLE_PROJECT_ID"] or "",
            model_id=required_keys["SPECKLE_MODEL_ID"] or "",
            use_ssl=_read_bool_env("SPECKLE_USE_SSL", default=False),
        )


def _coerce_dict(value: Any) -> Any:
    if hasattr(value, "get_dynamic_member_names"):
        return {
            key: _coerce_dict(getattr(value, key, value[key]))
            for key in value.get_dynamic_member_names()
        }
    if isinstance(value, dict):
        return {key: _coerce_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_coerce_dict(item) for item in value]
    return value


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    if hasattr(value, key):
        return getattr(value, key)
    try:
        return value[key]
    except (KeyError, TypeError, AttributeError):
        return None


def _print_version(root: Any, latest: dict[str, Any]) -> None:
    timestamp = _get_value(root, "timestamp")
    payload = _coerce_dict(_get_value(root, "payload"))
    print(f"version_id: {latest['id']}")
    print(f"message: {latest['message']}")
    print(f"created_at: {latest['createdAt']}")
    print(f"device_id: {_get_value(root, 'device_id')}")
    print(f"sensor_type: {_get_value(root, 'sensor_type')}")
    print(f"unit: {_get_value(root, 'unit')}")
    print(f"topic: {_get_value(root, 'topic')}")
    print(f"timestamp: {timestamp}")
    print(f"timestamp_local: {format_timestamp_local(timestamp)}")
    print("payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> None:
    load_environment()
    settings = SpeckleSettings.from_env()

    client = SpeckleClient(host=settings.host, use_ssl=settings.use_ssl)
    client.authenticate_with_token(settings.token)
    transport = ServerTransport(client=client, stream_id=settings.project_id)

    query = gql(
        f"""
        query {{
          project(id: {json.dumps(settings.project_id)}) {{
            model(id: {json.dumps(settings.model_id)}) {{
              versions(limit: 1) {{
                items {{
                  id
                  message
                  createdAt
                  referencedObject
                }}
              }}
            }}
          }}
        }}
        """
    )
    result = client.execute_query(query)
    versions = result["project"]["model"]["versions"]["items"]
    if not versions:
        raise SystemExit("No versions found in the configured model.")

    latest = versions[0]
    root = receive(latest["referencedObject"], transport)
    _print_version(root, latest)


if __name__ == "__main__":
    main()


def main_recent() -> None:
    load_environment()
    settings = SpeckleSettings.from_env()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    client = SpeckleClient(host=settings.host, use_ssl=settings.use_ssl)
    client.authenticate_with_token(settings.token)
    transport = ServerTransport(client=client, stream_id=settings.project_id)

    query = gql(
        f"""
        query {{
          project(id: {json.dumps(settings.project_id)}) {{
            model(id: {json.dumps(settings.model_id)}) {{
              versions(limit: {limit}) {{
                items {{
                  id
                  message
                  createdAt
                  referencedObject
                }}
              }}
            }}
          }}
        }}
        """
    )
    result = client.execute_query(query)
    versions = result["project"]["model"]["versions"]["items"]
    if not versions:
        raise SystemExit("No versions found in the configured model.")

    for index, version in enumerate(versions, start=1):
        root = receive(version["referencedObject"], transport)
        print(f"--- latest #{index} ---")
        _print_version(root, version)
        print()
