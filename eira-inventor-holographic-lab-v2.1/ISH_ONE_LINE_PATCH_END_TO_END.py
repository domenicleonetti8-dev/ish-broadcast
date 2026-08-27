#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

SOURCE_COMMIT = "861a7c3294d7b8f5ea6bdb1daec43e4d5b3e29c3"
BASE = f"https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{SOURCE_COMMIT}/eira-inventor-holographic-lab-v2.1/extensions/eira_inventor_holographic_lab/"
FILES = (
    "engineering3d_bridge.py",
    "blender_bridge.py",
    "plugin.py",
    "server.py",
    "static/index.html",
    "omnivenom_node.json",
    "manifest.json",
)
LIVE = Path("/media/domenicleonetti/easystore/EIRA/LIVE").resolve()
TARGET = LIVE / "extensions" / "eira_inventor_holographic_lab"
NODE_ID = "eira.inventor.holographic_lab"

def die(msg):
    raise SystemExit("EIRA INVENTOR LAB E2E: " + msg)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if not TARGET.is_dir():
    die("active inventor lab missing: " + str(TARGET))
if not (TARGET / "archive").exists():
    print("ARCHIVE_STATE=empty_or_not_created")
else:
    print("ARCHIVE_STATE=present")

before_main = sha(LIVE / "main.py") if (LIVE / "main.py").is_file() else None
db = TARGET / "archive" / "inventor_archive.sqlite3"
before_db = sha(db) if db.is_file() else None
before_archive_count = sum(1 for p in (TARGET / "archive").rglob("*") if p.is_file()) if (TARGET / "archive").is_dir() else 0

stage_root = Path(tempfile.mkdtemp(prefix="eira_inventor_e2e_"))
backup_root = Path(tempfile.mkdtemp(prefix="eira_inventor_e2e_backup_"))

try:
    for rel in FILES:
        dst = stage_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(BASE + rel, headers={"User-Agent": "EIRA-InventorLab-E2E"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(5_000_000)
        if not data:
            die("empty download: " + rel)
        dst.write_bytes(data)
        if dst.suffix == ".py":
            compile(dst.read_text(encoding="utf-8"), str(dst), "exec")
        print("FETCHED=" + rel + " SHA256=" + hashlib.sha256(data).hexdigest())

    for rel in FILES:
        src = TARGET / rel
        if src.is_file():
            bak = backup_root / rel
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, bak)

    try:
        for rel in FILES:
            src = stage_root / rel
            dst = TARGET / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".e2e_tmp")
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)

        if before_main and sha(LIVE / "main.py") != before_main:
            die("protected main.py changed")

        if db.is_file() and before_db and sha(db) != before_db:
            die("inventor archive database changed during code update")
        after_archive_count = sum(1 for p in (TARGET / "archive").rglob("*") if p.is_file()) if (TARGET / "archive").is_dir() else 0
        if after_archive_count != before_archive_count:
            die(f"inventor archive file count changed during code update: {before_archive_count}->{after_archive_count}")

        sys.path.insert(0, str(LIVE))
        for name in list(sys.modules):
            if name.startswith("extensions.eira_inventor_holographic_lab"):
                sys.modules.pop(name, None)
        plugin = importlib.import_module("extensions.eira_inventor_holographic_lab.plugin")
        bridge = importlib.import_module("extensions.eira_inventor_holographic_lab.engineering3d_bridge")

        st = plugin.status()
        if st.get("node_id") != NODE_ID or st.get("core_modified") is not False:
            die("extension self-test failed")

        contract = bridge.provider_contract()
        print("ENGINEERING3D_CAPABILITY=" + str(contract.get("capability")))
        print("CAPABILITY_REQUEST=" + str(contract.get("request_type")) + str(contract.get("request_signature")))
        print("MEDIA_PART=" + str(contract.get("media_type")) + str(contract.get("media_signature")))
        print("BLENDER_EXECUTABLE=" + str(contract.get("blender_executable")))

        if not contract.get("ok"):
            die("Engineering3D contract unresolved: " + json.dumps(contract, default=str))
        if not contract.get("media_type"):
            die("MediaPart unresolved; drawing pixels cannot be passed to Engineering3D")
        if not contract.get("blender_executable"):
            die("BLENDER_MISSING: no Blender executable found on the Pi; set EIRA_BLENDER or install Blender")

        from extensions.omnivenom_mesh_ai.runtime import Omnivenom
        mesh = Omnivenom(LIVE)
        descriptor = json.loads((TARGET / "omnivenom_node.json").read_text(encoding="utf-8"))
        descriptor.update({
            "path": str(TARGET),
            "entrypoint": "extensions.eira_inventor_holographic_lab.plugin",
            "render_pipeline": "drawing_media -> Engineering3D -> Blender -> GLB -> Safari",
            "engineering3d_capability": contract.get("capability"),
            "blender_executable": contract.get("blender_executable"),
        })
        mesh.register_system(NODE_ID, descriptor)
        registered = mesh.registered_systems()
        mesh.close()
        if NODE_ID not in json.dumps(registered, default=str):
            die("OmniVenom targeted registration verification failed")

    except BaseException:
        for rel in FILES:
            bak = backup_root / rel
            dst = TARGET / rel
            if bak.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bak, dst)
        raise

finally:
    shutil.rmtree(stage_root, ignore_errors=True)
    shutil.rmtree(backup_root, ignore_errors=True)

print("E2E_CODE_INSTALL=PASS")
print("ARCHIVE_PRESERVED=true")
print("CORE_MAIN_PRESERVED=true")
print("OMNIVENOM_TARGETED=PASS")
print("PIPELINE=drawing_media -> Engineering3D -> Blender -> GLB -> Safari")
print("RESTART=Ctrl+C then python3 -m extensions.eira_inventor_holographic_lab.server --host 100.107.25.56 --port 8787")
