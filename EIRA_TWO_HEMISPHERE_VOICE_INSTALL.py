#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import shutil
import sys
import time
import urllib.request
from pathlib import Path

LIVE = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/media/domenicleonetti/easystore/EIRA/LIVE"
).expanduser().resolve()

MAIN = LIVE / "main.py"
BRIDGE = LIVE / "extensions" / "omnivenom_mesh_ai" / "eira_bridge.py"

BRIDGE_URL = (
    "https://raw.githubusercontent.com/"
    "domenicleonetti8-dev/ish-broadcast/"
    "ff33d3f360fd63dc9a18f8498c1ce83f2d2d407c/"
    "EIRA_OMNIVENOM_TWO_HEMISPHERE_BRIDGE_V3.py"
)
BRIDGE_SHA256 = "fcc283cbcdb11169673e6622376270bb36e1b1ba7070d74b741f2a2633941fad"


def die(message):
    raise SystemExit("EIRA TWO-HEMISPHERE VOICE: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


for path, label in (
    (MAIN, "main.py"),
    (BRIDGE.parent / "runtime.py", "OmniVenom runtime"),
    (LIVE / "extensions" / "unified_brain_ai" / "plugin.py", "Unified Brain"),
    (LIVE / "extensions" / "local_brain" / "router.py", "local brain"),
):
    if not path.is_file():
        die(label + " missing: " + str(path))

main_before = MAIN.read_bytes()
bridge_before = BRIDGE.read_bytes() if BRIDGE.exists() else None
stamp = time.strftime("%Y%m%d_%H%M%S")
main_backup = LIVE / f"main.py.bak_two_hemisphere_voice_{stamp}"
bridge_backup = LIVE / f"eira_bridge.py.bak_two_hemisphere_voice_{stamp}"
shutil.copy2(MAIN, main_backup)
if BRIDGE.exists():
    shutil.copy2(BRIDGE, bridge_backup)


def rollback():
    MAIN.write_bytes(main_before)
    if bridge_before is None:
        try:
            BRIDGE.unlink()
        except FileNotFoundError:
            pass
    else:
        BRIDGE.write_bytes(bridge_before)


try:
    req = urllib.request.Request(
        BRIDGE_URL,
        headers={"User-Agent": "Eira-two-hemisphere-voice"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        bridge_bytes = response.read(200000)

    if sha(bridge_bytes) != BRIDGE_SHA256:
        die("bridge SHA256 mismatch; rolled back")

    compile(
        bridge_bytes.decode("utf-8"),
        str(BRIDGE),
        "exec",
    )
    BRIDGE.write_bytes(bridge_bytes)

    source = MAIN.read_text(encoding="utf-8")
    start = source.find("def _speak(response):")
    if start < 0:
        die("_speak(response) not found")
    end = source.find("\ndef live_runtime_report(", start)
    if end < 0:
        die("live_runtime_report boundary not found")

    speak = r'''def _speak(response):
    import base64
    import sys
    from extensions.ecosystem_kernel_ai.awareness import run as refresh_awareness
    from extensions.ecosystem_kernel_ai.evidence import render_response

    refresh_awareness()
    evidence_checked = render_response(response)
    identity_checked = outward_text_gate(evidence_checked)
    spoken = str(identity_checked or "").strip()

    print("EIRA:", spoken)

    if spoken:
        payload = base64.b64encode(
            spoken.encode("utf-8")
        ).decode("ascii")
        sys.stdout.write(
            "\x1b]777;EIRA-SPEAK;" + payload + "\x07"
        )
        sys.stdout.flush()

'''
    new_main = source[:start] + speak + source[end + 1:]
    ast.parse(new_main, filename=str(MAIN))

    if "extensions.omnivenom_mesh_ai.eira_bridge import chat" not in new_main:
        die("OmniVenom chat import missing from main.py")
    if "EIRA-SPEAK" not in new_main:
        die("phone voice protocol missing from main.py")

    MAIN.write_text(new_main, encoding="utf-8")

    sys.path.insert(0, str(LIVE))
    from extensions.omnivenom_mesh_ai.eira_bridge import status

    st = status()
    if st.get("brain_count") != 2:
        die("bridge did not report exactly two brains")
    if st.get("architecture") != "two_hemisphere_one_voice":
        die("unexpected bridge architecture")

except BaseException:
    rollback()
    raise

print("EIRA_TWO_HEMISPHERE_VOICE_INSTALL=PASS")
print("BRAINS=2")
print("DOMINANT=unified_brain_ai")
print("TANDEM=local_brain")
print("OMNIVENOM=connective_evidence_fabric")
print("OUTWARD_RESPONSE_PLANES=1")
print("VOICE_PROTOCOL=OSC777_EIRA_SPEAK")
print("MAIN_BACKUP=" + str(main_backup))
print("MAIN_SHA256=" + sha(MAIN.read_bytes()))
print("BRIDGE_SHA256=" + sha(BRIDGE.read_bytes()))
