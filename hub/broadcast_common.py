#!/usr/bin/env python3
"""Shared configuration and state helpers for the Broadcast hub."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


DEVICE_NAME = "broadcast"
MAX_OUTPUTS = 10
A2DP_SOURCE_UUID = "0000110a-0000-1000-8000-00805f9b34fb"
A2DP_SINK_UUID = "0000110b-0000-1000-8000-00805f9b34fb"
MAC_RE = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")

DEFAULT_CONFIG: dict[str, Any] = {
    "device_name": DEVICE_NAME,
    "input_controller": "",
    "input_device_mac": "",
    "input_node": "",
    "max_outputs": MAX_OUTPUTS,
    "minimum_proof_outputs": 2,
    "speaker_allowlist": [],
    "speaker_priority": [],
    "speaker_controllers": {},
    "speaker_delays_ms": {},
    "poll_interval_seconds": 1.0,
    "reconnect_cooldown_seconds": 5.0,
    "loopback_restart_seconds": 3.0,
    "loopback_latency_ms": 80,
    "bluez_status_path": "/run/broadcast-hub/bluez-status.json",
    "status_path": "",
}


class ConfigError(ValueError):
    """Raised when a hub configuration would violate a hard requirement."""


def normalize_mac(value: str, *, allow_empty: bool = False) -> str:
    normalized = value.strip().replace("-", ":").upper()
    if not normalized and allow_empty:
        return ""
    if not MAC_RE.fullmatch(normalized):
        raise ConfigError(f"invalid Bluetooth address: {value!r}")
    return normalized


def _number(
    config: Mapping[str, Any], key: str, minimum: float, maximum: float
) -> float:
    value = config[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{key} must be between {minimum} and {maximum}")
    return result


def _mac_list(config: Mapping[str, Any], key: str) -> list[str]:
    values = config[key]
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ConfigError(f"{key} must be a list of Bluetooth addresses")
    normalized = [normalize_mac(item) for item in values]
    if len(normalized) != len(set(normalized)):
        raise ConfigError(f"{key} contains duplicate addresses")
    return normalized


def validate_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ConfigError("configuration root must be an object")

    unknown = sorted(set(raw) - set(DEFAULT_CONFIG))
    if unknown:
        raise ConfigError(f"unknown configuration keys: {', '.join(unknown)}")

    config = dict(DEFAULT_CONFIG)
    config.update(raw)

    if config["device_name"] != DEVICE_NAME:
        raise ConfigError("device_name must be exactly lowercase 'broadcast'")

    for key in ("input_node", "bluez_status_path", "status_path"):
        if not isinstance(config[key], str):
            raise ConfigError(f"{key} must be a string")

    config["input_controller"] = normalize_mac(
        str(config["input_controller"]), allow_empty=True
    )
    config["input_device_mac"] = normalize_mac(
        str(config["input_device_mac"]), allow_empty=True
    )

    max_outputs = config["max_outputs"]
    if isinstance(max_outputs, bool) or not isinstance(max_outputs, int):
        raise ConfigError("max_outputs must be an integer")
    if not 2 <= max_outputs <= MAX_OUTPUTS:
        raise ConfigError(f"max_outputs must be between 2 and {MAX_OUTPUTS}")

    minimum = config["minimum_proof_outputs"]
    if isinstance(minimum, bool) or not isinstance(minimum, int):
        raise ConfigError("minimum_proof_outputs must be an integer")
    if not 2 <= minimum <= max_outputs:
        raise ConfigError(
            "minimum_proof_outputs must be at least 2 and no greater than max_outputs"
        )

    config["speaker_allowlist"] = _mac_list(config, "speaker_allowlist")
    config["speaker_priority"] = _mac_list(config, "speaker_priority")

    controller_map = config["speaker_controllers"]
    if not isinstance(controller_map, Mapping):
        raise ConfigError("speaker_controllers must be an address-to-address object")
    config["speaker_controllers"] = {
        normalize_mac(str(device)): normalize_mac(str(controller))
        for device, controller in controller_map.items()
    }

    delay_map = config["speaker_delays_ms"]
    if not isinstance(delay_map, Mapping):
        raise ConfigError("speaker_delays_ms must be an address-to-milliseconds object")
    normalized_delays: dict[str, int] = {}
    for device, delay in delay_map.items():
        if isinstance(delay, bool) or not isinstance(delay, int):
            raise ConfigError("every speaker delay must be an integer")
        if not 0 <= delay <= 5000:
            raise ConfigError("every speaker delay must be between 0 and 5000 ms")
        normalized_delays[normalize_mac(str(device))] = delay
    config["speaker_delays_ms"] = normalized_delays

    config["poll_interval_seconds"] = _number(
        config, "poll_interval_seconds", 0.2, 60.0
    )
    config["reconnect_cooldown_seconds"] = _number(
        config, "reconnect_cooldown_seconds", 1.0, 300.0
    )
    config["loopback_restart_seconds"] = _number(
        config, "loopback_restart_seconds", 0.2, 300.0
    )

    latency = config["loopback_latency_ms"]
    if isinstance(latency, bool) or not isinstance(latency, int):
        raise ConfigError("loopback_latency_ms must be an integer")
    if not 10 <= latency <= 2000:
        raise ConfigError("loopback_latency_ms must be between 10 and 2000")

    return config


def load_config(path: str | os.PathLike[str]) -> dict[str, Any]:
    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read configuration {config_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {config_path}: {exc}") from exc
    return validate_config(raw)


def atomic_write_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary.write_text(payload, encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, destination)


def read_json(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
