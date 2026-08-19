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
MARK = "# EIRA_OMNIVENOM_TWO_BRAIN_BIND_V2"

BRIDGE_URL = (
    "https://raw.githubusercontent.com/"
    "domenicleonetti8-dev/ish-broadcast/"
    "0d3f82d0f0ad12ca73b55617125587562b2481ee/"
    "EIRA_OMNIVENOM_TWO_BRAIN_BRIDGE_V2.py"
)
BRIDGE_SHA256 = "8f2aaf88dd8a9adf46da813af09bb11a9f2a21e94e41ec6ea96e5b6c7b341993"


def die(message):
    raise SystemExit("EIRA TWO-BRAIN BIND V2: " + message)


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    return digest_bytes(path.read_bytes())


for path, label in (
    (MAIN, "main.py"),
    (
        LIVE / "extensions" / "omnivenom_mesh_ai" / "runtime.py",
        "OmniVenom runtime",
    ),
    (
        LIVE / "extensions" / "unified_brain_ai" / "plugin.py",
        "Unified Brain",
    ),
    (
        LIVE / "extensions" / "local_brain" / "router.py",
        "local brain",
    ),
):
    if not path.is_file():
        die(label + " missing: " + str(path))

before_main = MAIN.read_bytes()
before_bridge = BRIDGE.read_bytes() if BRIDGE.exists() else None
stamp = time.strftime("%Y%m%d_%H%M%S")
backup = LIVE / f"main.py.bak_omnivenom_two_brain_v2_{stamp}"
shutil.copy2(MAIN, backup)


def rollback():
    MAIN.write_bytes(before_main)
    if before_bridge is None:
        try:
            BRIDGE.unlink()
        except FileNotFoundError:
            pass
    else:
        BRIDGE.write_bytes(before_bridge)


try:
    request = urllib.request.Request(
        BRIDGE_URL,
        headers={"User-Agent": "Eira-two-brain-bind-v2"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        bridge_bytes = response.read(100000)

    if digest_bytes(bridge_bytes) != BRIDGE_SHA256:
        die("bridge SHA256 mismatch; nothing bound")

    compile(
        bridge_bytes.decode("utf-8"),
        "eira_bridge.py",
        "exec",
    )

    BRIDGE.write_bytes(bridge_bytes)

    lines = MAIN.read_text(encoding="utf-8").splitlines()
    output = []
    replaced = False

    for line in lines:
        if "ROUTER_DEBUG:" in line:
            continue

        stripped = line.strip()
        if (
            stripped.startswith(
                "from extensions.local_brain.router import"
            )
            and "chat" in stripped
            and "should_route" in stripped
        ):
            indent = line[: len(line) - len(line.lstrip())]
            output.extend([
                indent + MARK,
                indent
                + "from extensions.local_brain.router import should_route",
                indent
                + "from extensions.omnivenom_mesh_ai.eira_bridge import chat",
            ])
            replaced = True
            continue

        output.append(line)

    if not replaced:
        current = "\n".join(output)
        if MARK not in current:
            die(
                "expected local_brain chat import not found; "
                "main.py rolled back"
            )

    new_main = "\n".join(output) + "\n"
    ast.parse(new_main, filename=str(MAIN))

    if "_speak(eira_response)" not in new_main:
        die(
            "voice handoff _speak(eira_response) not found; "
            "main.py rolled back"
        )

    MAIN.write_text(new_main, encoding="utf-8")

    sys.path.insert(0, str(LIVE))
    from extensions.omnivenom_mesh_ai.eira_bridge import status
    from extensions.unified_brain_ai import plugin as unified

    bridge_status = status()
    unified_status = unified.status()

except BaseException:
    rollback()
    raise

print("EIRA_TWO_BRAIN_BIND_V2=PASS")
print("MAIN_BEFORE_SHA256=" + digest_bytes(before_main))
print("MAIN_AFTER_SHA256=" + digest_file(MAIN))
print("BACKUP=" + str(backup))
print("OMNIVENOM_ROLE=" + str(bridge_status.get("omnivenom_role")))
print("DOMINANT=" + str(bridge_status.get("dominant")))
print("TANDEM=" + str(bridge_status.get("tandem")))
print("BRAINS=" + str(bridge_status.get("brain_count")))
print("VOICE_HANDOFF=main.py:_speak")
print("UNIFIED_VERSION=" + str(unified_status.get("version")))
