#!/usr/bin/env python3
"""Route one incoming Bluetooth stream to independent Bluetooth speakers."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from broadcast_common import (
    DEVICE_NAME,
    ConfigError,
    atomic_write_json,
    load_config,
    normalize_mac,
    read_json,
)


LOGGER = logging.getLogger("broadcast-hub")
NODE_INTERFACE = "PipeWire:Interface:Node"
NODE_ADDRESS_RE = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[_:-]){5}[0-9A-Fa-f]{2}")


@dataclass(frozen=True)
class AudioNode:
    name: str
    media_class: str
    description: str
    address: str


def _address_from_properties(properties: dict[str, Any]) -> str:
    for key in (
        "api.bluez5.address",
        "bluez5.address",
        "device.address",
        "device.string",
        "device.name",
        "node.name",
    ):
        value = properties.get(key)
        if not isinstance(value, str):
            continue
        match = NODE_ADDRESS_RE.search(value)
        if match:
            return normalize_mac(match.group(0).replace("_", ":"))
    return ""


def parse_pw_dump(value: Any) -> tuple[list[AudioNode], list[AudioNode]]:
    if not isinstance(value, list):
        raise ValueError("pw-dump root must be an array")

    sources: list[AudioNode] = []
    sinks: list[AudioNode] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != NODE_INTERFACE:
            continue
        info = item.get("info", {})
        properties = info.get("props", {}) if isinstance(info, dict) else {}
        if not isinstance(properties, dict):
            continue
        name = properties.get("node.name")
        media_class = properties.get("media.class")
        if not isinstance(name, str) or not isinstance(media_class, str):
            continue
        if not name.startswith(("bluez_input.", "bluez_output.")):
            continue
        node = AudioNode(
            name=name,
            media_class=media_class,
            description=str(
                properties.get(
                    "node.description", properties.get("device.description", name)
                )
            ),
            address=_address_from_properties(properties),
        )
        if media_class == "Audio/Source" and name.startswith("bluez_input."):
            sources.append(node)
        elif media_class == "Audio/Sink" and name.startswith("bluez_output."):
            sinks.append(node)

    sources.sort(key=lambda node: node.name)
    sinks.sort(key=lambda node: node.name)
    return sources, sinks


class GraphBackend(Protocol):
    def snapshot(self) -> tuple[list[AudioNode], list[AudioNode]]: ...


class PipeWireGraph:
    def snapshot(self) -> tuple[list[AudioNode], list[AudioNode]]:
        completed = subprocess.run(
            ["pw-dump"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit {completed.returncode}"
            raise RuntimeError(f"pw-dump failed: {detail}")
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"pw-dump returned invalid JSON: {exc}") from exc
        return parse_pw_dump(value)


class ProcessLike(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


@dataclass
class LoopbackRecord:
    address: str
    source: str
    sink: str
    process: ProcessLike
    command: list[str]


def _start_process(command: list[str]) -> ProcessLike:
    return subprocess.Popen(command, stdout=subprocess.DEVNULL)


class LoopbackSupervisor:
    """Owns one pw-loopback process per speaker and isolates every failure."""

    def __init__(
        self,
        config: dict[str, Any],
        process_factory: Callable[[list[str]], ProcessLike] = _start_process,
    ):
        self.config = config
        self.process_factory = process_factory
        self.records: dict[str, LoopbackRecord] = {}
        self.retry_after: dict[str, float] = {}
        self.failures: dict[str, str] = {}

    def command_for(self, source: AudioNode, sink: AudioNode) -> list[str]:
        safe_address = sink.address.replace(":", "_") or "unknown"
        delay_seconds = self.config["speaker_delays_ms"].get(sink.address, 0) / 1000.0
        stream_properties = json.dumps(
            {"node.dont-reconnect": True, "node.passive": True},
            separators=(",", ":"),
        )
        return [
            "pw-loopback",
            "--name",
            f"broadcast-{safe_address}",
            "--latency",
            str(self.config["loopback_latency_ms"]),
            "--delay",
            f"{delay_seconds:.3f}",
            "--capture",
            source.name,
            "--playback",
            sink.name,
            "--capture-props",
            stream_properties,
            "--playback-props",
            stream_properties,
        ]

    def _stop(self, address: str) -> None:
        record = self.records.pop(address, None)
        if record is None:
            return
        if record.process.poll() is not None:
            return
        record.process.terminate()
        try:
            record.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            record.process.kill()
            record.process.wait(timeout=2.0)

    def reconcile(
        self,
        source: AudioNode | None,
        sinks: Iterable[AudioNode],
        *,
        now: float | None = None,
    ) -> None:
        tick_time = time.monotonic() if now is None else now
        desired = {sink.address: sink for sink in sinks if sink.address}

        for address, record in list(self.records.items()):
            return_code = record.process.poll()
            sink = desired.get(address)
            changed = (
                source is None
                or sink is None
                or record.source != source.name
                or record.sink != sink.name
            )
            if return_code is not None:
                self.records.pop(address, None)
                self.failures[address] = f"pw-loopback exited {return_code}"
                self.retry_after[address] = (
                    tick_time + self.config["loopback_restart_seconds"]
                )
            elif changed:
                self._stop(address)

        if source is None:
            return

        for address, sink in desired.items():
            if address in self.records:
                continue
            if tick_time < self.retry_after.get(address, float("-inf")):
                continue
            command = self.command_for(source, sink)
            try:
                process = self.process_factory(command)
            except Exception as exc:
                self.failures[address] = str(exc)
                self.retry_after[address] = (
                    tick_time + self.config["loopback_restart_seconds"]
                )
                LOGGER.warning("speaker %s loopback failed to start: %s", address, exc)
                continue
            self.records[address] = LoopbackRecord(
                address=address,
                source=source.name,
                sink=sink.name,
                process=process,
                command=command,
            )
            self.failures.pop(address, None)

    def stop_all(self) -> None:
        for address in list(self.records):
            self._stop(address)

    def active_addresses(self) -> list[str]:
        return sorted(
            address
            for address, record in self.records.items()
            if record.process.poll() is None
        )


def choose_input(config: dict[str, Any], sources: Iterable[AudioNode]) -> AudioNode | None:
    candidates = list(sources)
    configured_node = config["input_node"]
    if configured_node:
        return next((node for node in candidates if node.name == configured_node), None)
    configured_device = config["input_device_mac"]
    if configured_device:
        return next(
            (node for node in candidates if node.address == configured_device), None
        )
    return candidates[0] if candidates else None


def choose_sinks(
    config: dict[str, Any],
    sinks: Iterable[AudioNode],
    bluez_status: dict[str, Any] | None,
) -> list[AudioNode]:
    if not bluez_status or bluez_status.get("endpoint_name") != DEVICE_NAME:
        return []
    speaker_values = bluez_status.get("speakers", [])
    if not isinstance(speaker_values, list):
        return []
    order: list[str] = []
    for speaker in speaker_values:
        if not isinstance(speaker, dict) or not speaker.get("connected"):
            continue
        address = speaker.get("address")
        if not isinstance(address, str):
            continue
        try:
            order.append(normalize_mac(address))
        except ConfigError:
            continue

    by_address: dict[str, AudioNode] = {}
    for sink in sinks:
        if sink.address and sink.address not in by_address:
            by_address[sink.address] = sink
    return [
        by_address[address]
        for address in order[: config["max_outputs"]]
        if address in by_address
    ]


class BroadcastHub:
    def __init__(
        self,
        config: dict[str, Any],
        graph: GraphBackend,
        supervisor: LoopbackSupervisor,
        status_path: str,
    ):
        self.config = config
        self.graph = graph
        self.supervisor = supervisor
        self.status_path = status_path

    def reconcile_once(self, now: float | None = None) -> dict[str, Any]:
        sources, sinks = self.graph.snapshot()
        bluez_status = read_json(self.config["bluez_status_path"])
        source = choose_input(self.config, sources)
        selected_sinks = choose_sinks(self.config, sinks, bluez_status)
        self.supervisor.reconcile(source, selected_sinks, now=now)
        active = self.supervisor.active_addresses()
        minimum_met = len(active) >= self.config["minimum_proof_outputs"]
        controller_ready = bool(
            bluez_status and bluez_status.get("controller_discoverable")
        )
        status = {
            "service": "broadcast-hub",
            "endpoint_name": DEVICE_NAME,
            "controller_discoverable": controller_ready,
            "input_node": source.name if source else None,
            "input_device": source.address if source else None,
            "selected_outputs": [
                {
                    "address": sink.address,
                    "name": sink.description,
                    "node": sink.name,
                }
                for sink in selected_sinks
            ],
            "active_routes": active,
            "route_failures": dict(sorted(self.supervisor.failures.items())),
            "minimum_output_gate": self.config["minimum_proof_outputs"],
            "minimum_output_gate_met": minimum_met,
            "runtime_ready": controller_ready and source is not None and minimum_met,
            "physical_audio_proof": "not-recorded",
            "updated_unix": time.time(),
        }
        atomic_write_json(self.status_path, status)
        return status


def default_status_path(config: dict[str, Any]) -> str:
    if config["status_path"]:
        return config["status_path"]
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return str(Path(runtime) / "broadcast-hub" / "status.json")


def run_service(config: dict[str, Any], *, once: bool = False) -> int:
    status_path = default_status_path(config)
    supervisor = LoopbackSupervisor(config)
    hub = BroadcastHub(config, PipeWireGraph(), supervisor, status_path)
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            try:
                hub.reconcile_once()
            except Exception as exc:
                LOGGER.exception("audio graph reconciliation failed; keeping live routes")
                atomic_write_json(
                    status_path,
                    {
                        "service": "broadcast-hub",
                        "endpoint_name": DEVICE_NAME,
                        "runtime_ready": False,
                        "error": str(exc),
                        "active_routes": supervisor.active_addresses(),
                        "physical_audio_proof": "not-recorded",
                        "updated_unix": time.time(),
                    },
                )
            if once or stopping:
                break
            time.sleep(config["poll_interval_seconds"])
    finally:
        supervisor.stop_all()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="/etc/broadcast-hub/config.json", help="hub JSON config"
    )
    parser.add_argument("--once", action="store_true", help="reconcile once and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        LOGGER.error("%s", exc)
        return 2
    return run_service(config, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
