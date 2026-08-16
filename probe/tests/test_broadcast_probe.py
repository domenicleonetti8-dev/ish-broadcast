#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


PROBE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROBE_DIR))

from broadcast_bluez import (  # noqa: E402
    AdapterState,
    BluetoothCoordinator,
    DbusBlueZBackend,
    DeviceState,
    eligible_speakers,
)
from broadcast_common import (  # noqa: E402
    A2DP_SINK_UUID,
    A2DP_SOURCE_UUID,
    ConfigError,
    atomic_write_json,
    validate_config,
)
from broadcast_probe import (  # noqa: E402
    AudioNode,
    BroadcastProbe,
    LoopbackSupervisor,
    choose_input,
    parse_pw_dump,
)


def config_for(directory: Path, **updates: Any) -> dict[str, Any]:
    value = {
        "bluez_status_path": str(directory / "bluez.json"),
        "status_path": str(directory / "probe.json"),
    }
    value.update(updates)
    return validate_config(value)


def adapter(
    address: str,
    path: str,
    *,
    ready: bool = False,
) -> AdapterState:
    return AdapterState(
        path,
        address,
        "broadcast" if ready else "old-name",
        ready,
        ready,
        ready,
        (A2DP_SINK_UUID,) if ready else (),
    )


def speaker(
    address: str,
    path: str,
    adapter_path: str,
    *,
    connected: bool = True,
    trusted: bool = True,
    services_resolved: bool | None = None,
) -> DeviceState:
    if services_resolved is None:
        services_resolved = connected
    return DeviceState(
        path=path,
        address=address,
        name=f"speaker-{address[-2:]}",
        adapter_path=adapter_path,
        uuids=(A2DP_SINK_UUID,),
        paired=True,
        trusted=trusted,
        connected=connected,
        blocked=False,
        services_resolved=services_resolved,
    )


def inbound_source(address: str, adapter_path: str) -> DeviceState:
    return DeviceState(
        path=f"{adapter_path}/dev_{address.replace(':', '_')}",
        address=address,
        name="Dom iPhone",
        adapter_path=adapter_path,
        uuids=(A2DP_SOURCE_UUID,),
        paired=True,
        trusted=True,
        connected=True,
        blocked=False,
        services_resolved=True,
    )


class FakeBlueZBackend:
    def __init__(
        self,
        adapters: list[AdapterState],
        devices: list[DeviceState],
        *,
        failed_device: str = "",
    ):
        self.adapter_values = adapters
        self.device_values = devices
        self.failed_device = failed_device
        self.configured: list[tuple[str, bool]] = []
        self.connects: list[str] = []

    def adapters(self) -> list[AdapterState]:
        return self.adapter_values

    def devices(self) -> list[DeviceState]:
        return self.device_values

    def configure_adapter(
        self, value: AdapterState, *, input_adapter: bool
    ) -> None:
        self.configured.append((value.address, input_adapter))

    def connect_device(self, value: DeviceState) -> None:
        self.connects.append(value.address)
        if value.address == self.failed_device:
            raise RuntimeError("radio unavailable")


class FakeProperties:
    def __init__(self) -> None:
        self.sets: list[tuple[str, str, Any]] = []

    def Set(self, interface: str, name: str, value: Any) -> None:
        self.sets.append((interface, name, value))


class FakeDbusModule:
    def __init__(self, properties: FakeProperties) -> None:
        self.properties = properties

    def Interface(self, _object: Any, _name: str) -> FakeProperties:
        return self.properties

    @staticmethod
    def Boolean(value: bool) -> bool:
        return value

    @staticmethod
    def UInt32(value: int) -> int:
        return value


class FakeBus:
    @staticmethod
    def get_object(_service: str, path: str) -> str:
        return path


class FakeProcess:
    def __init__(self) -> None:
        self.return_code: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = 0

    def wait(self, timeout: float | None = None) -> int:
        if self.return_code is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.return_code

    def kill(self) -> None:
        self.killed = True
        self.return_code = -9


class FakeProcessFactory:
    def __init__(self, failed_address: str = "") -> None:
        self.failed_address = failed_address.replace(":", "_")
        self.commands: list[list[str]] = []
        self.processes: list[FakeProcess] = []

    def __call__(self, command: list[str]) -> FakeProcess:
        self.commands.append(command)
        if self.failed_address and self.failed_address in command[2]:
            raise OSError("cannot launch this route")
        process = FakeProcess()
        self.processes.append(process)
        return process


class FakeGraph:
    def __init__(
        self, snapshots: list[tuple[list[AudioNode], list[AudioNode]]]
    ) -> None:
        self.snapshots = snapshots

    def snapshot(self) -> tuple[list[AudioNode], list[AudioNode]]:
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


def source(address: str = "AA:BB:CC:DD:EE:01") -> AudioNode:
    return AudioNode(
        f"bluez_input.{address.replace(':', '_')}.1",
        "Audio/Source",
        "iPhone",
        address,
        "running",
    )


def sink(address: str) -> AudioNode:
    return AudioNode(
        f"bluez_output.{address.replace(':', '_')}.1",
        "Audio/Sink",
        f"speaker-{address[-2:]}",
        address,
        "running",
    )


class ConfigurationTests(unittest.TestCase):
    def test_name_and_limits_are_hard_requirements(self) -> None:
        with self.assertRaises(ConfigError):
            validate_config({"device_name": "Broadcast"})
        with self.assertRaises(ConfigError):
            validate_config({"max_outputs": 11})
        self.assertEqual(validate_config({})["device_name"], "broadcast")
        self.assertEqual(validate_config({})["max_outputs"], 10)

    def test_pw_dump_discovers_only_bluetooth_audio_nodes(self) -> None:
        value = [
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "bluez_input.AA_BB_CC_DD_EE_01.1",
                        "node.description": "Dom iPhone",
                        "media.class": "Audio/Source",
                    }
                },
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "bluez_output.10_20_30_40_50_60.1",
                        "device.description": "Kitchen",
                        "media.class": "Audio/Sink",
                    }
                },
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "alsa_output.fake",
                        "media.class": "Audio/Sink",
                    }
                },
            },
        ]
        sources, sinks = parse_pw_dump(value)
        self.assertEqual([node.address for node in sources], ["AA:BB:CC:DD:EE:01"])
        self.assertEqual([node.address for node in sinks], ["10:20:30:40:50:60"])

    def test_configured_input_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = config_for(
                Path(temporary), input_device_mac="AA:BB:CC:DD:EE:02"
            )
            self.assertEqual(
                choose_input(
                    config,
                    [source(), source("AA:BB:CC:DD:EE:02")],
                    {
                        "probe_connected": True,
                        "inbound_sources": [
                            {
                                "address": "AA:BB:CC:DD:EE:02",
                                "profile_connected": True,
                            }
                        ],
                    },
                ).address,
                "AA:BB:CC:DD:EE:02",
            )

    def test_input_requires_real_bluez_profile_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = config_for(Path(temporary))
            self.assertIsNone(choose_input(config, [source()], None))
            self.assertIsNone(
                choose_input(
                    config,
                    [source()],
                    {"probe_connected": True, "inbound_sources": []},
                )
            )


class BlueZCoordinatorTests(unittest.TestCase):
    def test_connected_flag_without_resolved_audio_service_is_not_a_string(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            controller = adapter(
                "00:00:00:00:00:01", "/org/bluez/hci0", ready=True
            )
            unresolved = speaker(
                "10:20:30:40:50:60",
                "/org/bluez/hci0/dev_speaker",
                controller.path,
                connected=True,
                services_resolved=False,
            )
            status = BluetoothCoordinator(
                config_for(Path(temporary)),
                FakeBlueZBackend([controller], [unresolved]),
            ).tick(now=0.0)
            self.assertTrue(status["speakers"][0]["connected"])
            self.assertFalse(status["speakers"][0]["profile_connected"])

    def test_setter_success_never_fakes_probe_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            value = adapter("00:00:00:00:00:01", "/org/bluez/hci0")
            backend = FakeBlueZBackend([value], [])
            status = BluetoothCoordinator(
                config_for(Path(temporary)), backend
            ).tick(now=0.0)
            self.assertFalse(status["probe_registered"])
            self.assertFalse(status["probe_findable"])
            self.assertFalse(status["probe_connectable"])

    def test_verified_adapter_and_inbound_handshake_are_real_probe_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            value = adapter(
                "00:00:00:00:00:01", "/org/bluez/hci0", ready=True
            )
            phone = inbound_source("AA:BB:CC:DD:EE:01", value.path)
            status = BluetoothCoordinator(
                config_for(Path(temporary)), FakeBlueZBackend([value], [phone])
            ).tick(now=0.0)
            self.assertTrue(status["probe_registered"])
            self.assertTrue(status["probe_findable"])
            self.assertTrue(status["probe_connectable"])
            self.assertTrue(status["probe_connected"])
    def test_dbus_backend_sets_exact_alias_and_discoverability(self) -> None:
        properties = FakeProperties()
        backend = DbusBlueZBackend(FakeBus(), FakeDbusModule(properties))
        value = adapter("00:00:00:00:00:01", "/org/bluez/hci0")
        backend.configure_adapter(value, input_adapter=True)
        changed = {(name, setting) for _interface, name, setting in properties.sets}
        self.assertIn(("Alias", "broadcast"), changed)
        self.assertIn(("Powered", True), changed)
        self.assertIn(("Pairable", True), changed)
        self.assertIn(("Discoverable", True), changed)

    def test_exact_input_controller_and_independent_reconnect_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = adapter("00:00:00:00:00:01", "/org/bluez/hci0")
            second = adapter("00:00:00:00:00:02", "/org/bluez/hci1")
            good = speaker(
                "10:20:30:40:50:60", "/org/bluez/hci0/dev_good", first.path
            )
            failed = speaker(
                "10:20:30:40:50:61",
                "/org/bluez/hci1/dev_failed",
                second.path,
                connected=False,
            )
            backend = FakeBlueZBackend(
                [first, second], [good, failed], failed_device=failed.address
            )
            config = config_for(directory, input_controller=second.address)
            status = BluetoothCoordinator(config, backend).tick(now=100.0)

            self.assertEqual(
                backend.configured,
                [(first.address, False), (second.address, True)],
            )
            self.assertEqual(status["endpoint_name"], "broadcast")
            self.assertEqual(status["input_controller"], second.address)
            self.assertEqual(backend.connects, [failed.address])
            self.assertEqual(len(status["speakers"]), 2)
            self.assertIn(failed.address, status["errors"][0])

    def test_reconnect_cooldown_prevents_a_hot_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            value = adapter("00:00:00:00:00:01", "/org/bluez/hci0")
            target = speaker(
                "10:20:30:40:50:60",
                "/org/bluez/hci0/dev_target",
                value.path,
                connected=False,
            )
            backend = FakeBlueZBackend([value], [target])
            coordinator = BluetoothCoordinator(config_for(Path(temporary)), backend)
            coordinator.tick(now=10.0)
            coordinator.tick(now=11.0)
            coordinator.tick(now=16.0)
            self.assertEqual(backend.connects, [target.address, target.address])

    def test_limit_trust_allowlist_and_controller_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = adapter("00:00:00:00:00:01", "/org/bluez/hci0")
            second = adapter("00:00:00:00:00:02", "/org/bluez/hci1")
            devices = [
                speaker(
                    f"10:20:30:40:50:{index:02X}",
                    f"/org/bluez/hci0/dev_{index}",
                    first.path,
                )
                for index in range(12)
            ]
            config = config_for(Path(temporary))
            self.assertEqual(len(eligible_speakers(config, [first, second], devices)), 10)

            target = devices[0]
            untrusted = speaker(
                "10:20:30:40:50:FE",
                "/org/bluez/hci1/dev_untrusted",
                second.path,
                trusted=False,
            )
            bound = config_for(
                Path(temporary),
                speaker_allowlist=[target.address, untrusted.address],
                speaker_controllers={target.address: second.address},
            )
            self.assertEqual(
                eligible_speakers(bound, [first, second], [target, untrusted]), []
            )


class FanoutTests(unittest.TestCase):
    def test_stale_bluez_status_cannot_keep_a_connection_alive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = config_for(directory, status_freshness_seconds=5.0)
            target = sink("10:20:30:40:50:60")
            atomic_write_json(
                config["bluez_status_path"],
                {
                    "endpoint_name": "broadcast",
                    "updated_unix": 1000.0,
                    "probe_registered": True,
                    "probe_connected": True,
                    "inbound_sources": [
                        {
                            "address": source().address,
                            "profile_connected": True,
                        }
                    ],
                    "speakers": [
                        {"address": target.address, "profile_connected": True}
                    ],
                },
            )
            supervisor = LoopbackSupervisor(config, FakeProcessFactory())
            probe = BroadcastProbe(
                config,
                FakeGraph([([source()], [target])]),
                supervisor,
                config["status_path"],
            )
            status = probe.reconcile_once(now=0.0, wall_time=1006.0)
            self.assertFalse(status["probe"]["connected"])
            self.assertFalse(status["runtime_ready"])
            self.assertEqual(status["connected_routes"], [])

    def test_idle_nodes_are_connected_but_never_claim_streaming(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = config_for(directory, minimum_proof_outputs=2)
            input_node = AudioNode(
                source().name,
                source().media_class,
                source().description,
                source().address,
                "idle",
            )
            targets = [
                AudioNode(
                    sink(address).name,
                    "Audio/Sink",
                    sink(address).description,
                    address,
                    "idle",
                )
                for address in ("10:20:30:40:50:60", "10:20:30:40:50:61")
            ]
            atomic_write_json(
                config["bluez_status_path"],
                {
                    "endpoint_name": "broadcast",
                    "updated_unix": 1000.0,
                    "probe_registered": True,
                    "probe_findable": True,
                    "probe_connectable": True,
                    "probe_connected": True,
                    "inbound_sources": [
                        {
                            "address": input_node.address,
                            "profile_connected": True,
                        }
                    ],
                    "speakers": [
                        {"address": node.address, "profile_connected": True}
                        for node in targets
                    ],
                },
            )
            probe = BroadcastProbe(
                config,
                FakeGraph([([input_node], targets)]),
                LoopbackSupervisor(config, FakeProcessFactory()),
                config["status_path"],
            )
            status = probe.reconcile_once(now=0.0, wall_time=1000.0)
            self.assertTrue(status["runtime_ready"])
            self.assertTrue(status["minimum_output_gate_met"])
            self.assertFalse(status["streaming_output_gate_met"])
            self.assertFalse(status["end_to_end_streaming"])
            self.assertEqual(status["active_routes"], [])

    def test_one_dead_loopback_does_not_stop_another(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = config_for(Path(temporary))
            factory = FakeProcessFactory()
            supervisor = LoopbackSupervisor(config, factory)
            first = sink("10:20:30:40:50:60")
            second = sink("10:20:30:40:50:61")

            supervisor.reconcile(source(), [first, second], now=0.0)
            first_process = supervisor.records[first.address].process
            second_process = supervisor.records[second.address].process
            first_process.return_code = 7
            supervisor.reconcile(source(), [first, second], now=1.0)

            self.assertNotIn(first.address, supervisor.records)
            self.assertIs(supervisor.records[second.address].process, second_process)
            self.assertFalse(second_process.terminated)
            supervisor.reconcile(source(), [first, second], now=3.0)
            self.assertNotIn(first.address, supervisor.records)
            supervisor.reconcile(source(), [first, second], now=4.0)
            self.assertIn(first.address, supervisor.records)

    def test_start_failure_is_isolated_and_command_targets_both_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            failed = "10:20:30:40:50:60"
            healthy = "10:20:30:40:50:61"
            config = config_for(Path(temporary))
            factory = FakeProcessFactory(failed)
            supervisor = LoopbackSupervisor(config, factory)
            supervisor.reconcile(source(), [sink(failed), sink(healthy)], now=0.0)

            self.assertNotIn(failed, supervisor.records)
            self.assertIn(healthy, supervisor.records)
            command = supervisor.records[healthy].command
            self.assertEqual(command[command.index("--capture") + 1], source().name)
            self.assertEqual(command[command.index("--playback") + 1], sink(healthy).name)
            self.assertTrue(any("node.dont-reconnect" in value for value in command))

    def test_per_speaker_delay_is_passed_to_pipewire(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            address = "10:20:30:40:50:61"
            config = config_for(
                Path(temporary), speaker_delays_ms={address: 375}
            )
            supervisor = LoopbackSupervisor(config, FakeProcessFactory())
            command = supervisor.command_for(source(), sink(address))
            self.assertEqual(command[command.index("--delay") + 1], "0.375")

    def test_dynamic_leave_stops_only_the_missing_speaker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = config_for(directory)
            first = sink("10:20:30:40:50:60")
            second = sink("10:20:30:40:50:61")
            atomic_write_json(
                config["bluez_status_path"],
                {
                    "endpoint_name": "broadcast",
                    "updated_unix": 1000.0,
                    "probe_registered": True,
                    "probe_findable": True,
                    "probe_connectable": True,
                    "probe_connected": True,
                    "inbound_sources": [
                        {
                            "address": source().address,
                            "profile_connected": True,
                        }
                    ],
                    "speakers": [
                        {"address": first.address, "profile_connected": True},
                        {"address": second.address, "profile_connected": True},
                    ],
                },
            )
            graph = FakeGraph([([source()], [first, second]), ([source()], [second])])
            factory = FakeProcessFactory()
            supervisor = LoopbackSupervisor(config, factory)
            probe = BroadcastProbe(config, graph, supervisor, config["status_path"])

            status = probe.reconcile_once(now=0.0, wall_time=1000.0)
            self.assertTrue(status["runtime_ready"])
            self.assertEqual(status["physical_audio_proof"], "not-recorded")
            first_process = supervisor.records[first.address].process
            second_process = supervisor.records[second.address].process

            status = probe.reconcile_once(now=1.0, wall_time=1001.0)
            self.assertTrue(status["runtime_ready"])
            self.assertFalse(status["minimum_output_gate_met"])
            self.assertTrue(first_process.terminated)
            self.assertFalse(second_process.terminated)
            self.assertEqual(status["active_routes"], [second.address])


if __name__ == "__main__":
    unittest.main()
