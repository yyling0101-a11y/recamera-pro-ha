"""Read the optional broker bootstrap created by the host-side installer."""

from __future__ import annotations

import json
from pathlib import Path


def load_managed_broker_config(path: str) -> dict:
    """Return validated HA-side credentials without exposing device credentials."""
    credentials_path = Path(path)
    marker_path = credentials_path.parent / ".recamera-pro-managed"
    if not credentials_path.is_file() or not marker_path.is_file():
        return {}
    try:
        payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        port = int(payload.get("port", 1883))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    if (
        payload.get("managed") is not True
        or not str(payload.get("host", "")).strip()
        or not str(payload.get("ha_username", "")).strip()
        or not str(payload.get("ha_password", ""))
        or not 1 <= port <= 65535
    ):
        return {}
    return {
        "broker": str(payload["host"]).strip(),
        "port": port,
        "username": str(payload["ha_username"]).strip(),
        "password": str(payload["ha_password"]),
    }
