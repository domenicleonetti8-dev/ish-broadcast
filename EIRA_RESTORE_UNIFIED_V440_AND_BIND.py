#!/usr/bin/env python3
from __future__ import annotations

import base64
import io
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

LIVE = Path(sys.argv[1] if len(sys.argv) > 1 else "/media/domenicleonetti/easystore/EIRA/LIVE").expanduser().resolve()
PIN = "8d2158c982adcd87852c65562ee9bc71bbc7864e"
BASE = f"https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{PIN}/_eira_v440_payload"
BINDER = "https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/1ae507da346468d06373efbbee599418609a24a8/EIRA_OMNIVENOM_TWO_BRAIN_BIND_V2.py"
TARGET = LIVE / "extensions" / "unified_brain_ai"


def die(msg: str):
    raise SystemExit("EIRA UNIFIED RESTORE: " + msg)


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=45) as r:
        return r.read()


def safe_extract(tf: tarfile.TarFile, dst: Path):
    root = dst.resolve()
    for m in tf.getmembers():
        pp = PurePosixPath(m.name)
        if pp.is_absolute() or any(p in ("", "..") for p in pp.parts):
            die(f"unsafe archive path: {m.name}")
        out = (dst / Path(*pp.parts)).resolve()
        if root != out and root not in out.parents:
            die(f"archive escape: {m.name}")
        if m.issym() or m.islnk():
            die(f"archive link blocked: {m.name}")
    tf.extractall(dst)


if not (LIVE / "main.py").is_file():
    die(f"main.py missing under {LIVE}")
if not (LIVE / "extensions" / "omnivenom_mesh_ai" / "runtime.py").is_file():
    die("OmniVenom is missing; refusing to replace it")
if not (LIVE / "extensions" / "local_brain" / "router.py").is_file():
    die("existing local brain missing")

print("[1/5] Pulling pinned v4.4.0 source payload")
joined = bytearray()
for i in range(5):
    url = f"{BASE}/source.chunk{i:02d}"
    part = get(url)
    if not part:
        die(f"empty payload chunk {i:02d}")
    joined.extend(part.strip())

try:
    packed = base64.b64decode(bytes(joined), validate=False)
except Exception as exc:
    die(f"payload base64 decode failed: {exc}")
if not packed.startswith(b"\xfd7zXZ\x00"):
    die("payload is not the expected XZ archive")

print("[2/5] Locating Unified Brain inside payload")
with tempfile.TemporaryDirectory(prefix="eira_v440_restore_") as td:
    temp = Path(td)
    try:
        with tarfile.open(fileobj=io.BytesIO(packed), mode="r:xz") as tf:
            safe_extract(tf, temp)
    except Exception as exc:
        die(f"payload extraction failed: {exc}")

    matches = list(temp.rglob("extensions/unified_brain_ai/plugin.py"))
    if not matches:
        die("v4.4.0 payload does not contain extensions/unified_brain_ai/plugin.py")
    plugin = matches[0]
    source = plugin.parent

    print("[3/5] Installing only missing Unified Brain")
    backup = None
    if TARGET.exists():
        backup = TARGET.with_name("unified_brain_ai.bak_before_v440_restore")
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(TARGET), str(backup))
    try:
        shutil.copytree(source, TARGET)
        for py in TARGET.rglob("*.py"):
            py_compile.compile(str(py), doraise=True)
    except Exception as exc:
        shutil.rmtree(TARGET, ignore_errors=True)
        if backup and backup.exists():
            shutil.move(str(backup), str(TARGET))
        die(f"Unified Brain install failed/rolled back: {exc}")

print("[4/5] Verifying Unified Brain v4.4.0")
sys.path.insert(0, str(LIVE))
try:
    from extensions.unified_brain_ai import plugin as unified
    st = unified.status()
except Exception as exc:
    die(f"Unified Brain import failed: {exc}")
if str(st.get("version")) != "4.4.0":
    die(f"wrong Unified Brain version: {st.get('version')}")
print("UNIFIED_VERSION=4.4.0")

print("[5/5] Binding the existing two brains through OmniVenom")
with tempfile.NamedTemporaryFile(prefix="eira_bind_v2_", suffix=".py", delete=False) as f:
    binder_path = Path(f.name)
    f.write(get(BINDER))
try:
    py_compile.compile(str(binder_path), doraise=True)
    cp = subprocess.run([sys.executable, str(binder_path), str(LIVE)], text=True)
    if cp.returncode != 0:
        die(f"two-brain binder exited {cp.returncode}")
finally:
    binder_path.unlink(missing_ok=True)

print("EIRA_UNIFIED_RESTORE_AND_BIND=PASS")
print("BRAINS=2")
print("DOMINANT=unified_brain_ai")
print("TANDEM=local_brain")
print("OMNIVENOM=connective_web")
print("VOICE_HANDOFF=main.py:_speak")
