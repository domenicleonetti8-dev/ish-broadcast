#!/usr/bin/env python3
"""Validate the iOS wiring that the portable C tests cannot compile."""

from pathlib import Path
import json
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
    require(plist.get("CFBundleDisplayName") == "broadcast",
            "display name must be exactly lowercase broadcast")
    modes = set(plist.get("UIBackgroundModes", []))
    require({"audio", "bluetooth-peripheral"} <= modes,
            "background audio and BLE peripheral modes are required")
    require(bool(plist.get("NSBluetoothAlwaysUsageDescription")),
            "Bluetooth permission copy is required")
    require(bool(plist.get("NSBluetoothPeripheralUsageDescription")),
            "Bluetooth permission copy for older iOS versions is required")
    ET.parse(ROOT / "app/Base.lproj/Terminal.storyboard")


def validate_bridge() -> None:
    bridge = read("app/BroadcastBridge.m")
    required = (
        'BroadcastLogicalName = @"broadcast"',
        "B0ADC0DE-0000-4F1A-9000-000000000001",
        "B0ADC0DE-0000-4F1A-9000-000000000002",
        "CBAdvertisementDataLocalNameKey: BroadcastLogicalName",
        "CBAdvertisementDataServiceUUIDsKey",
        "configureControlService",
        "didReceiveReadRequest",
        "playConnectionTest",
        "maximum_fingers",
        "active_fingers",
        "bluetooth_state",
        "mapped_channels",
    )
    for token in required:
        require(token in bridge, f"missing bridge wiring: {token}")

    router = read("app/BroadcastAudioRouter.m")
    for token in (
        "AVAudioSessionCategoryMultiRoute",
        "dualRouteModeForSession",
        "kAudioOutputUnitProperty_ChannelMap",
        "maximumOutputNumberOfChannels",
        "BroadcastAudioMaximumQueuedFrames",
        "BroadcastAudioMaximumQueuedFrames -",
        "initStandardFormatWithSampleRate",
        "floatChannelData",
        "useChannelMap",
        "broadcast_pcm_s16le_stereo_to_float",
        "_enabledOutputUIDs = [identifiers copy]",
        "withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation",
    ):
        require(token in router, f"missing audio router wiring: {token}")

    controller = read("app/BroadcastViewController.m")
    for token in (
        "AVRoutePickerView",
        "Test Sound",
        "Remembered audio fingers",
    ):
        require(token in controller, f"missing visible connection UI: {token}")

    device = read("app/BroadcastDevice.m")
    require("broadcast_audio_dev" in device,
            "raw PCM device is not registered")
    require("size % 4" in device,
            "raw PCM frame alignment is not enforced")


def validate_xcode_project() -> None:
    project = read("iSH.xcodeproj/project.pbxproj")
    for filename in (
        "BroadcastBridge.m",
        "BroadcastDevice.m",
        "BroadcastFingerTable.c",
        "BroadcastFanout.c",
        "BroadcastRouteMap.c",
        "BroadcastPCM.c",
        "BroadcastAudioRouter.m",
        "BroadcastViewController.m",
    ):
        require(f"{filename} in Sources" in project,
                f"{filename} is not in the app source phase")
    for framework in (
        "CoreBluetooth.framework in Frameworks",
        "AVFoundation.framework in Frameworks",
        "AudioToolbox.framework in Frameworks",
        "AVKit.framework in Frameworks",
    ):
        require(framework in project, f"missing linked {framework}")

    object_ids = re.findall(
        r"^\s*([A-F0-9]{24}) /\*.*?\*/ = ", project, re.MULTILINE
    )
    duplicate_ids = sorted({value for value in object_ids
                            if object_ids.count(value) > 1})
    require(not duplicate_ids,
            f"duplicate Xcode object IDs: {duplicate_ids}")


def validate_release_wiring() -> None:
    config = read("app/iSH.xcconfig")
    require("ROOT_BUNDLE_IDENTIFIER = com.domenicleonetti8.broadcast" in config,
            "broadcast bundle identifier is missing")
    project_config = read("app/Project.xcconfig")
    require("MARKETING_VERSION = 1.4.1" in project_config,
            "broadcast marketing version is not 1.4.1")

    project = read("iSH.xcodeproj/project.pbxproj")
    require(project.count("CURRENT_PROJECT_VERSION = 814;") == 4,
            "broadcast build number is not consistently 814")

    workflow = read(".github/workflows/ghost-probe.yml")
    require("-scheme iSH" in workflow,
            "Ghost Probe does not compile the iSH scheme")
    require("-configuration Debug" not in workflow,
            "Ghost Probe forces a nonexistent Xcode configuration")
    require("Payload/iSH.app" in workflow,
            "Ghost Probe does not create a standard IPA payload")
    require("broadcast-unsigned-iphone.ipa" in workflow,
            "Ghost Probe does not publish an unsigned IPA")

    fastfile = read("fastlane/Fastfile")
    lane_start = fastfile.index("lane :broadcast_beta do")
    lane_end = fastfile.index("lane :build do", lane_start)
    release_lane = fastfile[lane_start:lane_end]
    require("build_app(" in release_lane, "release lane does not build")
    require("upload_to_testflight(" in release_lane,
            "release lane does not upload to TestFlight")


def validate_hub_wiring() -> None:
    config = json.loads(read("hub/config/broadcast-hub.json"))
    require(config.get("device_name") == "broadcast",
            "hub endpoint name must be exactly lowercase broadcast")
    require(config.get("max_outputs") == 10,
            "hub must retain the 10-output limit")
    require(config.get("minimum_proof_outputs", 0) >= 2,
            "hub physical proof gate must require two outputs")

    common = read("hub/broadcast_common.py")
    require('DEVICE_NAME = "broadcast"' in common,
            "hub does not enforce the exact endpoint name")
    require("MAX_OUTPUTS = 10" in common,
            "hub does not enforce the hard output limit")

    bluez = read("hub/broadcast_bluez.py")
    for token in (
        '"Alias", DEVICE_NAME',
        '"Discoverable", self.dbus.Boolean(True)',
        "A2DP_SINK_UUID",
        "reconnect_cooldown_seconds",
        "for speaker in speakers",
    ):
        require(token in bluez, f"missing BlueZ hub wiring: {token}")

    fanout = read("hub/broadcast_hub.py")
    for token in (
        '"pw-loopback"',
        '"--capture"',
        '"--playback"',
        "for address, sink in desired.items()",
        '"physical_audio_proof": "not-recorded"',
    ):
        require(token in fanout, f"missing PipeWire hub wiring: {token}")

    modern = read("hub/config/wireplumber-0.5.conf")
    legacy = read("hub/config/wireplumber-0.4.lua")
    for token in ("a2dp_sink", "a2dp_source"):
        require(token in modern, f"WirePlumber 0.5 is missing {token}")
        require(token in legacy, f"WirePlumber 0.4 is missing {token}")
    require('bluez5.media-source-role = "input"' in modern,
            "incoming phone audio is not exposed as a PipeWire input")
    require('["bluez5.media-source-role"] = "input"' in legacy,
            "legacy incoming phone audio is not exposed as a PipeWire input")

    system_service = read("hub/systemd/broadcast-bluetooth.service")
    user_service = read("hub/systemd/broadcast-hub.service")
    require("broadcast_bluez.py" in system_service,
            "BlueZ coordinator is not installed as a system service")
    require("broadcast_hub.py" in user_service,
            "PipeWire fanout is not installed as a user service")


def main() -> None:
    validate_plist_and_storyboard()
    validate_bridge()
    validate_xcode_project()
    validate_release_wiring()
    validate_hub_wiring()
    print("validate_broadcast_project: PASS")


if __name__ == "__main__":
    main()
