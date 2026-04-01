import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from gql import gql
from specklepy.api.client import SpeckleClient
from specklepy.api.operations import receive
from specklepy.transports.server import ServerTransport

from speckle_arc.mqtt_to_speckle import _read_bool_env, load_environment


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


def _format_timestamp(timestamp: Any) -> str:
    if not isinstance(timestamp, (int, float)):
        return str(timestamp)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


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
    payload = _coerce_dict(root["payload"])

    print(f"version_id: {latest['id']}")
    print(f"message: {latest['message']}")
    print(f"created_at: {latest['createdAt']}")
    print(f"topic: {root['topic']}")
    print(f"timestamp: {root['timestamp']}")
    print(f"timestamp_iso: {_format_timestamp(root['timestamp'])}")
    print("payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
