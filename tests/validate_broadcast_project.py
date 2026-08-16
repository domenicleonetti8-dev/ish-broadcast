#!/usr/bin/env python3
"""Validate the real portable probe contract and iOS project wiring."""

from pathlib import Path
import plistlib
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def validate_plist_and_storyboard() -> None:
    plist = plistlib.loads((ROOT / "app/Info.plist").read_bytes())
    require(
        plist.get("CFBundleDisplayName") == "broadcast",
        "display name must be exactly lowercase broadcast",
    )
    modes = set(plist.get("UIBackgroundModes", []))
    require(
        {"audio", "bluetooth-peripheral"} <= modes,
        "background audio and BLE control modes are required",
    )
    require(
        bool(plist.get("NSBluetoothAlwaysUsageDescription")),
        "Bluetooth permission copy is required",
    )
    require(
        bool(plist.get("NSBluetoothPeripheralUsageDescription")),
        "Bluetooth permission copy for older iOS versions is required",
    )
    ET.parse(ROOT / "app/Base.lproj/Terminal.storyboard")


def validate_probe_contract() -> None:
    contract = read("app/BroadcastProbeContract.h")
    for token in (
        '#define BROADCAST_PROBE_NAME "broadcast"',
        "#define BROADCAST_MAX_STRINGS 10",
        "BROADCAST_PROBE_PROVIDER_UNAVAILABLE",
        "BROADCAST_PROBE_FINDABLE",
        "BROADCAST_PROBE_CONNECTED",
        "native_a2dp_provider_available",
        "a2dp_sink_registered",
        "ble_gatt_advertising",
    ):
        require(token in contract, f"missing probe contract: {token}")

    implementation = read("app/BroadcastProbeContract.c")
    require(
        "!evidence->native_a2dp_provider_available" in implementation,
        "probe registration is not gated by native A2DP evidence",
    )
    require(
        "evidence->ble_gatt_advertising" not in implementation,
        "BLE advertising must not promote classic-speaker state",
    )

    transport = read("app/BroadcastA2DPProbeTransport.h")
    for token in (
        "BroadcastA2DPProbeTransport",
        "inboundSourceConnections",
        "speakerStrings",
        "startSpeakerDiscovery",
        "attachSpeakerString",
        "detachSpeakerString",
        "writePCM16Stereo",
    ):
        require(token in transport, f"missing native transport seam: {token}")


def validate_bridge() -> None:
    bridge = read("app/BroadcastBridge.m")
    required = (
        'BroadcastLogicalName = @"broadcast"',
        "B0ADC0DE-0000-4F1A-9000-000000000001",
        "B0ADC0DE-0000-4F1A-9000-000000000002",
        "BroadcastCreateProbeTransport",
        'NSClassFromString(\n        @"BroadcastNativeA2DPProbeTransport"',
        'return @"stock_ios_public_api"',
        'a2dp_sink_provider_unavailable_on_stock_ios',
        'counts_as_classic_speaker_registration\": @NO',
        'classic_bluetooth_a2dp_sink',
        'probe_registered',
        'probe_findable',
        'probe_connectable',
        'probe_connected',
        'maximum_strings',
        'active_strings',
        'string_nodes',
        'isEqualToString:@"native_a2dp_stream"',
        'native_a2dp_source_provider',
        'hardware_audio_confirmation',
    )
    for token in required:
        require(token in bridge, f"missing bridge wiring: {token}")
    require(
        "AVAudioSessionCategoryMultiRoute" not in bridge,
        "system multiroute must not substitute for the probe topology",
    )
    require(
        "CBAdvertisementDataLocalNameKey" not in bridge,
        "the BLE control plane must not claim the broadcast probe name",
    )

    controller = read("app/BroadcastViewController.m")
    for token in (
        "BroadcastTopologyView",
        '@"broadcast"',
        '@"A2DP sink"',
        'maximumStrings = 10',
        'Attached Bluetooth speaker strings',
        'physical route evidenced',
        'Register Probe',
        'Run Check',
        'Test Sound',
    ):
        require(token in controller, f"missing topology UI: {token}")
    require(
        "AVRoutePickerView" not in controller,
        "the UI must not replace the probe with Apple's route picker",
    )

    device = read("app/BroadcastDevice.m")
    for token in (
        'isEqualToString:@"start"',
        'hasPrefix:@"attach "',
        'hasPrefix:@"detach "',
        "broadcast_audio_dev",
        "size % 4",
    ):
        require(token in device, f"missing /dev/broadcast wiring: {token}")


def validate_xcode_project() -> None:
    project = read("iSH.xcodeproj/project.pbxproj")
    for filename in (
        "BroadcastBridge.m",
        "BroadcastDevice.m",
        "BroadcastFingerTable.c",
        "BroadcastFanout.c",
        "BroadcastPCM.c",
        "BroadcastHealth.c",
        "BroadcastProbeContract.c",
        "BroadcastViewController.m",
    ):
        require(
            f"{filename} in Sources" in project,
            f"{filename} is not in the app source phase",
        )
    require(
        "CoreBluetooth.framework in Frameworks" in project,
        "CoreBluetooth is not linked for the separate BLE control plane",
    )
    require(
        "BroadcastAudioRouter.m in Sources" not in project,
        "legacy system-route implementation is still active",
    )

    object_ids = re.findall(
        r"^\s*([A-F0-9]{24}) /\*.*?\*/ = ", project, re.MULTILINE
    )
    duplicate_ids = sorted(
        {value for value in object_ids if object_ids.count(value) > 1}
    )
    require(not duplicate_ids, f"duplicate Xcode object IDs: {duplicate_ids}")


def validate_release_wiring() -> None:
    config = read("app/iSH.xcconfig")
    require(
        "ROOT_BUNDLE_IDENTIFIER = com.domenicleonetti8.broadcast" in config,
        "broadcast bundle identifier is missing",
    )
    project_config = read("app/Project.xcconfig")
    require(
        "MARKETING_VERSION = 1.7.0" in project_config,
        "broadcast marketing version is not 1.7.0",
    )

    project = read("iSH.xcodeproj/project.pbxproj")
    require(
        project.count("CURRENT_PROJECT_VERSION = 817;") == 4,
        "broadcast build number is not consistently 817",
    )

    workflow = read(".github/workflows/ghost-probe.yml")
    require("-scheme iSH" in workflow, "Ghost Probe does not compile iSH")
    require(
        "Payload/iSH.app" in workflow,
        "Ghost Probe does not create a standard IPA payload",
    )
    require(
        "broadcast-unsigned-iphone.ipa" in workflow,
        "Ghost Probe does not publish the unsigned build",
    )
    require(
        "broadcast-portable-probe.tar.gz" in workflow,
        "Ghost Probe does not package the real portable probe",
    )
    require("hub/" not in workflow, "obsolete hardware hub remains in CI")

    fastfile = read("fastlane/Fastfile")
    lane_start = fastfile.index("lane :broadcast_beta do")
    lane_end = fastfile.index("lane :build do", lane_start)
    release_lane = fastfile[lane_start:lane_end]
    require("build_app(" in release_lane, "release lane does not build")
    require(
        "upload_to_testflight(" in release_lane,
        "release lane does not upload to TestFlight",
    )


def validate_real_probe_target() -> None:
    hub = ROOT / "hub"
    remaining = [] if not hub.exists() else [
        path for path in hub.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    require(not remaining, f"obsolete portable hub files remain: {remaining}")
    required_files = (
        "probe/broadcast_bluez.py",
        "probe/broadcast_probe.py",
        "probe/config/wireplumber-0.5.conf",
        "probe/install.sh",
        "probe/systemd/broadcast-bluetooth.service",
        "probe/systemd/broadcast-probe.service",
    )
    for relative in required_files:
        require((ROOT / relative).is_file(), f"missing real probe file: {relative}")

    bluez = read("probe/broadcast_bluez.py")
    for token in (
        "A2DP_SINK_UUID",
        "A2DP_SOURCE_UUID",
        'verified_input.alias == DEVICE_NAME',
        'speaker.services_resolved',
        '"profile_connected"',
        'self.backend.adapters()',
    ):
        require(token in bluez, f"missing real BlueZ evidence gate: {token}")

    probe = read("probe/broadcast_probe.py")
    for token in (
        '"pw-loopback"',
        '"bluez_device_connected"',
        '"pipewire_bluez_output"',
        '"route_process_alive"',
        '"physical_audio_proof": "not-recorded"',
        '"end_to_end_streaming"',
    ):
        require(token in probe, f"missing real route evidence gate: {token}")
    require(
        'DEVICE_NAME = "broadcast"' in read("probe/broadcast_common.py"),
        "portable probe name must be exactly broadcast",
    )
    require(
        'MAX_OUTPUTS = 10' in read("probe/broadcast_common.py"),
        "portable probe must expose ten independent strings",
    )


def main() -> None:
    validate_plist_and_storyboard()
    validate_probe_contract()
    validate_bridge()
    validate_xcode_project()
    validate_release_wiring()
    validate_real_probe_target()
    print("validate_broadcast_project: PASS")


if __name__ == "__main__":
    main()
