#!/usr/bin/env python3
"""BlueZ pairing, discoverability, and independent speaker reconnect service."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from broadcast_common import (
    A2DP_SINK_UUID,
    A2DP_SOURCE_UUID,
    DEVICE_NAME,
    ConfigError,
    atomic_write_json,
    load_config,
    normalize_mac,
)


LOGGER = logging.getLogger("broadcast-bluez")
BLUEZ_SERVICE = "org.bluez"
OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"
AGENT_MANAGER_INTERFACE = "org.bluez.AgentManager1"
AGENT_INTERFACE = "org.bluez.Agent1"
AGENT_PATH = "/com/domenicleonetti8/broadcast/agent"


@dataclass(frozen=True)
class AdapterState:
    path: str
    address: str
    alias: str
    powered: bool
    pairable: bool
    discoverable: bool
    uuids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeviceState:
    path: str
    address: str
    name: str
    adapter_path: str
    uuids: tuple[str, ...]
    paired: bool
    trusted: bool
    connected: bool
    blocked: bool
    services_resolved: bool = False


class BlueZBackend(Protocol):
    def adapters(self) -> list[AdapterState]: ...

    def devices(self) -> list[DeviceState]: ...

    def configure_adapter(
        self, adapter: AdapterState, *, input_adapter: bool
    ) -> None: ...

    def connect_device(self, device: DeviceState) -> None: ...


def select_input_adapter(
    config: dict[str, Any], adapters: Iterable[AdapterState]
) -> AdapterState | None:
    ordered = sorted(adapters, key=lambda adapter: adapter.address)
    configured = config["input_controller"]
    if configured:
        return next(
            (adapter for adapter in ordered if adapter.address == configured), None
        )
    return ordered[0] if ordered else None


def eligible_speakers(
    config: dict[str, Any],
    adapters: Iterable[AdapterState],
    devices: Iterable[DeviceState],
) -> list[DeviceState]:
    adapter_addresses = {adapter.path: adapter.address for adapter in adapters}
    allowlist = set(config["speaker_allowlist"])
    controller_map = config["speaker_controllers"]
    input_device = config["input_device_mac"]
    priority = {
        address: index for index, address in enumerate(config["speaker_priority"])
    }

    selected: list[DeviceState] = []
    seen: set[str] = set()
    for device in devices:
        if device.address in seen or device.address == input_device:
            continue
        if not device.paired or not device.trusted or device.blocked:
            continue
        if A2DP_SINK_UUID not in {uuid.lower() for uuid in device.uuids}:
            continue
        if allowlist and device.address not in allowlist:
            continue
        required_controller = controller_map.get(device.address)
        actual_controller = adapter_addresses.get(device.adapter_path)
        if required_controller and actual_controller != required_controller:
            continue
        seen.add(device.address)
        selected.append(device)

    selected.sort(
        key=lambda device: (
            priority.get(device.address, len(priority)),
            device.name.casefold(),
            device.address,
        )
    )
    return selected[: config["max_outputs"]]


class BluetoothCoordinator:
    """Reconciles adapters and devices without coupling one failure to another."""

    def __init__(self, config: dict[str, Any], backend: BlueZBackend):
        self.config = config
        self.backend = backend
        self.last_connect_attempt: dict[str, float] = {}

    def tick(self, now: float | None = None) -> dict[str, Any]:
        tick_time = time.monotonic() if now is None else now
        errors: list[str] = []

        adapters = self.backend.adapters()
        input_adapter = select_input_adapter(self.config, adapters)
        for adapter in adapters:
            try:
                self.backend.configure_adapter(
                    adapter,
                    input_adapter=(
                        input_adapter is not None and adapter.path == input_adapter.path
                    ),
                )
            except Exception as exc:  # one bad USB controller must not stop the rest
                message = f"adapter {adapter.address}: {exc}"
                LOGGER.warning(message)
                errors.append(message)

        devices = self.backend.devices()
        speakers = eligible_speakers(self.config, adapters, devices)
        cooldown = self.config["reconnect_cooldown_seconds"]
        for speaker in speakers:
            if speaker.connected:
                continue
            previous = self.last_connect_attempt.get(speaker.address, float("-inf"))
            if tick_time - previous < cooldown:
                continue
            self.last_connect_attempt[speaker.address] = tick_time
            try:
                self.backend.connect_device(speaker)
            except Exception as exc:  # reconnect every speaker independently
                message = f"speaker {speaker.address}: {exc}"
                LOGGER.warning(message)
                errors.append(message)

        # Never infer success from a setter returning. Read BlueZ back after all
        # configuration and connection attempts and publish only observed state.
        verified_adapters = self.backend.adapters()
        verified_devices = self.backend.devices()
        verified_input = None
        if input_adapter is not None:
            verified_input = next(
                (
                    adapter
                    for adapter in verified_adapters
                    if adapter.path == input_adapter.path
                    and adapter.address == input_adapter.address
                ),
                None,
            )

        controller_powered = bool(verified_input and verified_input.powered)
        alias_exact = bool(verified_input and verified_input.alias == DEVICE_NAME)
        controller_pairable = bool(verified_input and verified_input.pairable)
        controller_discoverable = bool(
            verified_input and verified_input.discoverable
        )
        sink_profile_registered = bool(
            verified_input
            and A2DP_SINK_UUID in {uuid.lower() for uuid in verified_input.uuids}
        )
        probe_registered = controller_powered and alias_exact and sink_profile_registered
        probe_findable = probe_registered and controller_discoverable
        probe_connectable = probe_findable and controller_pairable

        configured_input_device = self.config["input_device_mac"]
        inbound_sources = []
        for device in verified_devices:
            if verified_input is None or device.adapter_path != verified_input.path:
                continue
            if configured_input_device and device.address != configured_input_device:
                continue
            source_profile = A2DP_SOURCE_UUID in {
                uuid.lower() for uuid in device.uuids
            }
            profile_connected = bool(
                device.paired
                and device.connected
                and device.services_resolved
                and source_profile
                and not device.blocked
            )
            if source_profile or profile_connected:
                inbound_sources.append(
                    {
                        "address": device.address,
                        "name": device.name,
                        "paired": device.paired,
                        "services_resolved": device.services_resolved,
                        "profile_connected": profile_connected,
                    }
                )

        verified_speakers = eligible_speakers(
            self.config, verified_adapters, verified_devices
        )
        status = {
            "service": "broadcast-bluez",
            "endpoint_name": DEVICE_NAME,
            "input_controller": input_adapter.address if input_adapter else None,
            "controller_powered": controller_powered,
            "controller_alias_exact": alias_exact,
            "controller_pairable": controller_pairable,
            "controller_discoverable": controller_discoverable,
            "a2dp_sink_registered": sink_profile_registered,
            "probe_registered": probe_registered,
            "probe_findable": probe_findable,
            "probe_connectable": probe_connectable,
            "probe_connected": any(
                source["profile_connected"] for source in inbound_sources
            ),
            "inbound_sources": inbound_sources,
            "speaker_limit": self.config["max_outputs"],
            "speakers": [
                {
                    "address": speaker.address,
                    "name": speaker.name,
                    "adapter_path": speaker.adapter_path,
                    "paired": speaker.paired,
                    "trusted": speaker.trusted,
                    "connected": speaker.connected,
                    "services_resolved": speaker.services_resolved,
                    "profile_connected": bool(
                        speaker.paired
                        and speaker.trusted
                        and speaker.connected
                        and speaker.services_resolved
                        and A2DP_SINK_UUID
                        in {uuid.lower() for uuid in speaker.uuids}
                        and not speaker.blocked
                    ),
                }
                for speaker in verified_speakers
            ],
            "errors": errors,
            "updated_unix": time.time(),
        }
        atomic_write_json(self.config["bluez_status_path"], status)
        return status


class DbusBlueZBackend:
    def __init__(self, bus: Any, dbus_module: Any):
        self.bus = bus
        self.dbus = dbus_module

    def _managed_objects(self) -> dict[Any, Any]:
        manager = self.dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, "/"), OBJECT_MANAGER_INTERFACE
        )
        return manager.GetManagedObjects()

    def adapters(self) -> list[AdapterState]:
        result: list[AdapterState] = []
        for path, interfaces in self._managed_objects().items():
            properties = interfaces.get(ADAPTER_INTERFACE)
            if properties is None:
                continue
            try:
                address = normalize_mac(str(properties.get("Address", "")))
            except ConfigError:
                continue
            result.append(
                AdapterState(
                    path=str(path),
                    address=address,
                    alias=str(properties.get("Alias", "")),
                    powered=bool(properties.get("Powered", False)),
                    pairable=bool(properties.get("Pairable", False)),
                    discoverable=bool(properties.get("Discoverable", False)),
                    uuids=tuple(
                        str(value).lower() for value in properties.get("UUIDs", [])
                    ),
                )
            )
        return result

    def devices(self) -> list[DeviceState]:
        result: list[DeviceState] = []
        for path, interfaces in self._managed_objects().items():
            properties = interfaces.get(DEVICE_INTERFACE)
            if properties is None:
                continue
            try:
                address = normalize_mac(str(properties.get("Address", "")))
            except ConfigError:
                continue
            result.append(
                DeviceState(
                    path=str(path),
                    address=address,
                    name=str(
                        properties.get("Alias", properties.get("Name", address))
                    ),
                    adapter_path=str(properties.get("Adapter", "")),
                    uuids=tuple(str(value).lower() for value in properties.get("UUIDs", [])),
                    paired=bool(properties.get("Paired", False)),
                    trusted=bool(properties.get("Trusted", False)),
                    connected=bool(properties.get("Connected", False)),
                    blocked=bool(properties.get("Blocked", False)),
                    services_resolved=bool(
                        properties.get("ServicesResolved", False)
                    ),
                )
            )
        return result

    def configure_adapter(
        self, adapter: AdapterState, *, input_adapter: bool
    ) -> None:
        properties = self.dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, adapter.path), PROPERTIES_INTERFACE
        )
        properties.Set(ADAPTER_INTERFACE, "Powered", self.dbus.Boolean(True))
        if input_adapter:
            properties.Set(ADAPTER_INTERFACE, "Alias", DEVICE_NAME)
            properties.Set(
                ADAPTER_INTERFACE, "PairableTimeout", self.dbus.UInt32(0)
            )
            properties.Set(
                ADAPTER_INTERFACE, "DiscoverableTimeout", self.dbus.UInt32(0)
            )
            properties.Set(ADAPTER_INTERFACE, "Pairable", self.dbus.Boolean(True))
            properties.Set(
                ADAPTER_INTERFACE, "Discoverable", self.dbus.Boolean(True)
            )
        else:
            properties.Set(ADAPTER_INTERFACE, "Discoverable", self.dbus.Boolean(False))
            properties.Set(ADAPTER_INTERFACE, "Pairable", self.dbus.Boolean(False))

    def connect_device(self, device: DeviceState) -> None:
        interface = self.dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, device.path), DEVICE_INTERFACE
        )
        interface.Connect()


def _register_pairing_agent(bus: Any, dbus_module: Any, service_module: Any) -> Any:
    class PairingAgent(service_module.Object):
        @service_module.method(AGENT_INTERFACE, in_signature="", out_signature="")
        def Release(self) -> None:
            LOGGER.info("BlueZ released the Broadcast pairing agent")

        @service_module.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
        def RequestPinCode(self, _device: Any) -> str:
            return "0000"

        @service_module.method(AGENT_INTERFACE, in_signature="os", out_signature="")
        def DisplayPinCode(self, device: Any, pin_code: str) -> None:
            LOGGER.info("pairing code %s displayed for %s", pin_code, device)

        @service_module.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
        def DisplayPasskey(self, _device: Any, _passkey: Any, _entered: Any) -> None:
            return None

        @service_module.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
        def RequestPasskey(self, _device: Any) -> Any:
            return dbus_module.UInt32(0)

        @service_module.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
        def RequestConfirmation(self, device: Any, _passkey: Any) -> None:
            LOGGER.info("confirming physical pairing request for %s", device)

        @service_module.method(AGENT_INTERFACE, in_signature="o", out_signature="")
        def RequestAuthorization(self, device: Any) -> None:
            LOGGER.info("authorizing physical pairing request for %s", device)

        @service_module.method(AGENT_INTERFACE, in_signature="os", out_signature="")
        def AuthorizeService(self, device: Any, uuid: str) -> None:
            LOGGER.info("authorizing %s for %s", uuid, device)

        @service_module.method(AGENT_INTERFACE, in_signature="", out_signature="")
        def Cancel(self) -> None:
            LOGGER.info("pairing request cancelled")

    agent = PairingAgent(bus, AGENT_PATH)
    manager = dbus_module.Interface(
        bus.get_object(BLUEZ_SERVICE, "/org/bluez"), AGENT_MANAGER_INTERFACE
    )
    manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
    manager.RequestDefaultAgent(AGENT_PATH)
    return agent, manager


def run_service(config: dict[str, Any], *, once: bool = False) -> int:
    try:
        import dbus
        import dbus.service
        import dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError as exc:
        LOGGER.error("missing python3-dbus/python3-gi dependency: %s", exc)
        return 2

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    backend = DbusBlueZBackend(bus, dbus)
    coordinator = BluetoothCoordinator(config, backend)
    agent, agent_manager = _register_pairing_agent(bus, dbus, dbus.service)

    if once:
        coordinator.tick()
        agent_manager.UnregisterAgent(AGENT_PATH)
        agent.remove_from_connection()
        return 0

    loop = GLib.MainLoop()

    def tick() -> bool:
        try:
            coordinator.tick()
        except Exception:
            LOGGER.exception("BlueZ reconciliation failed; retrying")
        return True

    def stop(_signum: int, _frame: Any) -> None:
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    tick()
    GLib.timeout_add(int(config["poll_interval_seconds"] * 1000), tick)
    try:
        loop.run()
    finally:
        try:
            agent_manager.UnregisterAgent(AGENT_PATH)
        except Exception:
            LOGGER.exception("failed to unregister pairing agent")
        agent.remove_from_connection()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="/etc/broadcast-probe/config.json", help="probe JSON config"
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
