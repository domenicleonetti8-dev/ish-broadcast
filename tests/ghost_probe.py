#!/usr/bin/env python3
"""Inspect a GitHub-built Broadcast iPhone app and emit a proof report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
from typing import Any


REQUIRED_FRAMEWORKS = (
    "CoreBluetooth",
)
REQUIRED_BINARY_STRINGS = (
    "broadcast",
    "/dev/broadcast_audio",
    "classic_bluetooth_a2dp_sink",
    "native_a2dp_provider_unavailable",
    "a2dp_sink_provider_unavailable_on_stock_ios",
    "BroadcastNativeA2DPProbeTransport",
    "findable_and_connectable",
    "Attached Bluetooth speaker strings",
    "hardware_audio_confirmation",
    "Run Check",
    "B0ADC0DE-0000-4F1A-9000-000000000001",
    "B0ADC0DE-0000-4F1A-9000-000000000002",
)


def command(*arguments: str) -> str:
    completed = subprocess.run(
        arguments,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json", dest="json_report", type=Path, required=True)
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    app = args.app.resolve()
    info_path = app / "Info.plist"
    check("App bundle exists", app.is_dir(), str(app))
    check("Compiled Info.plist exists", info_path.is_file(), str(info_path))

    info: dict[str, Any] = {}
    if info_path.is_file():
        with info_path.open("rb") as plist_file:
            info = plistlib.load(plist_file)

    display_name = info.get("CFBundleDisplayName")
    bundle_id = info.get("CFBundleIdentifier")
    version = info.get("CFBundleShortVersionString")
    build = info.get("CFBundleVersion")
    background_modes = set(info.get("UIBackgroundModes", []))
    check(
        "Visible app name",
        display_name == "broadcast",
        f"CFBundleDisplayName={display_name!r}",
    )
    check(
        "Broadcast bundle identifier",
        bundle_id == "com.domenicleonetti8.broadcast",
        f"CFBundleIdentifier={bundle_id!r}",
    )
    check("Broadcast version", version == "1.7.0", f"version={version!r}")
    check("Broadcast build", build == "817", f"build={build!r}")
    check(
        "Background audio mode",
        "audio" in background_modes,
        f"UIBackgroundModes={sorted(background_modes)!r}",
    )
    check(
        "BLE peripheral mode",
        "bluetooth-peripheral" in background_modes,
        f"UIBackgroundModes={sorted(background_modes)!r}",
    )
    check(
        "Bluetooth permission copy",
        bool(info.get("NSBluetoothAlwaysUsageDescription")),
        "NSBluetoothAlwaysUsageDescription is present",
    )

    executable_name = info.get("CFBundleExecutable", "iSH")
    executable = app / executable_name
    check("App executable exists", executable.is_file(), str(executable))

    architecture = "not inspected"
    linked_frameworks = "not inspected"
    binary_strings = ""
    if executable.is_file():
        try:
            architecture = command("/usr/bin/file", str(executable))
            check("arm64 device binary", "arm64" in architecture, architecture)
        except (OSError, subprocess.CalledProcessError) as error:
            check("arm64 device binary", False, str(error))

        try:
            linked_frameworks = command("/usr/bin/otool", "-L", str(executable))
            for framework in REQUIRED_FRAMEWORKS:
                check(
                    f"Linked {framework}",
                    framework in linked_frameworks,
                    f"{framework}.framework",
                )
        except (OSError, subprocess.CalledProcessError) as error:
            for framework in REQUIRED_FRAMEWORKS:
                check(f"Linked {framework}", False, str(error))

        try:
            binary_strings = command("/usr/bin/strings", "-a", str(executable))
            for required_string in REQUIRED_BINARY_STRINGS:
                check(
                    f"Compiled marker: {required_string}",
                    required_string in binary_strings,
                    "present in the compiled executable",
                )
        except (OSError, subprocess.CalledProcessError) as error:
            for required_string in REQUIRED_BINARY_STRINGS:
                check(f"Compiled marker: {required_string}", False, str(error))

    failed = [item for item in checks if not item["passed"]]
    signed = (app / "_CodeSignature").is_dir() or (
        app / "embedded.mobileprovision"
    ).is_file()
    result = {
        "result": "PASS" if not failed else "FAIL",
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "ref": os.environ.get("GITHUB_REF_NAME", "local"),
        "app": str(app),
        "signed": signed,
        "installable_on_stock_iphone": False,
        "classic_a2dp_provider_included": False,
        "physical_bluetooth_tested": False,
        "checks": checks,
    }

    args.json_report.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    report_lines = [
        "# Ghost Probe report",
        "",
        f"**Result: {result['result']}**",
        "",
        f"- Commit: `{result['commit']}`",
        f"- Ref: `{result['ref']}`",
        f"- Signing payload detected: {'yes' if signed else 'no'}",
        "- Stock-iPhone installability: no; this probe verifies the unsigned build",
        "- Classic A2DP provider: interface compiled; stock-iOS provider intentionally reports unavailable",
        "- Physical Bluetooth radio test: not available on a hosted runner",
        "",
        "| Check | Result | Detail |",
        "|---|---:|---|",
    ]
    for item in checks:
        status = "PASS" if item["passed"] else "FAIL"
        detail = str(item["detail"]).replace("|", "\\|").replace("\n", " ")
        report_lines.append(f"| {item['name']} | {status} | {detail} |")
    report_lines.append("")
    args.report.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
