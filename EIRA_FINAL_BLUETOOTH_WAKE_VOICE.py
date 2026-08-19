#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.request

BASE_INSTALLER_COMMIT = "697bb1df2c835731b09e3f61c6a31b3f6e4569c0"
OLD_RUNTIME_COMMIT = "0aa3a347a693cf4b84c3243f2c3b27bd732c8d60"
FINAL_RUNTIME_COMMIT = "3c43864b0f64af449278d7cc5d45a1f073bdebe7"
BASE_INSTALLER_URL = (
    "https://raw.githubusercontent.com/"
    "domenicleonetti8-dev/ish-broadcast/"
    + BASE_INSTALLER_COMMIT
    + "/EIRA_FINAL_BLUETOOTH_WAKE_VOICE_INSTALL.py"
)


def die(message: str) -> None:
    raise SystemExit("EIRA FINAL BUILD: " + message)


req = urllib.request.Request(
    BASE_INSTALLER_URL,
    headers={"User-Agent": "Eira-final-bluetooth-wake-voice"},
)
with urllib.request.urlopen(req, timeout=45) as response:
    raw = response.read(100000)

if not raw or len(raw) >= 100000:
    die("sealed installer download invalid")

try:
    source = raw.decode("utf-8")
except UnicodeDecodeError:
    die("sealed installer was not UTF-8")

required = (
    'EXT = LIVE / "extensions" / "eira_bluetooth_voice_ai"',
    'LIVE / "extensions" / "omnivenom_mesh_ai" / "eira_bridge.py"',
    'LIVE / "extensions" / "unified_brain_ai" / "plugin.py"',
    'LIVE / "extensions" / "local_brain" / "router.py"',
    "PiperVoice.load",
    'source.find("def _speak(response):")',
    "EIRA_FINAL_BLUETOOTH_WAKE_VOICE_INSTALL=PASS",
    "LIVE_AUDIO_TEST=",
)
missing = [marker for marker in required if marker not in source]
if missing:
    die("sealed installer identity mismatch: " + repr(missing))

if source.count(OLD_RUNTIME_COMMIT) != 1:
    die("runtime pin replacement was not exactly one occurrence")

source = source.replace(OLD_RUNTIME_COMMIT, FINAL_RUNTIME_COMMIT, 1)
if f'RUNTIME_COMMIT = "{FINAL_RUNTIME_COMMIT}"' not in source:
    die("final runtime pin was not installed")

code = compile(source, "EIRA_FINAL_BLUETOOTH_WAKE_VOICE_INSTALL.py", "exec")
namespace = {
    "__name__": "__main__",
    "__file__": "EIRA_FINAL_BLUETOOTH_WAKE_VOICE_INSTALL.py",
}
exec(code, namespace, namespace)
