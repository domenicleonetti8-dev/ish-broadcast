#!/usr/bin/env python3
"""Validate the iOS wiring that the portable C tests cannot compile."""

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
    ):
        require(token in router, f"missing audio router wiring: {token}")

    controller = read("app/BroadcastViewController.m")
    for token in ("AVRoutePickerView", "Test Sound", "Audio fingers"):
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

    fastfile = read("fastlane/Fastfile")
    lane_start = fastfile.index("lane :broadcast_beta do")
    lane_end = fastfile.index("lane :build do", lane_start)
    release_lane = fastfile[lane_start:lane_end]
    require("build_app(" in release_lane, "release lane does not build")
    require("upload_to_testflight(" in release_lane,
            "release lane does not upload to TestFlight")


def main() -> None:
    validate_plist_and_storyboard()
    validate_bridge()
    validate_xcode_project()
    validate_release_wiring()
    print("validate_broadcast_project: PASS")


if __name__ == "__main__":
    main()
