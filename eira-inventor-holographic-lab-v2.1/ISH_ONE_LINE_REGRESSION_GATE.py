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

SOURCE_COMMIT = "8f0fdef51661b82c2900dd49f1b39bed9e030d18"
BASE = f"https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{SOURCE_COMMIT}/eira-inventor-holographic-lab-v2.1/extensions/eira_inventor_holographic_lab/"
FILES = (
    "engineering3d_bridge.py",
    "blender_bridge.py",
    "plugin.py",
    "server.py",
    "regression_selftest.py",
    "static/index.html",
)
LIVE = Path("/media/domenicleonetti/easystore/EIRA/LIVE").resolve()
TARGET = LIVE / "extensions" / "eira_inventor_holographic_lab"

def die(msg):
    raise SystemExit("EIRA INVENTOR LAB REGRESSION GATE: " + msg)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

if not TARGET.is_dir(): die("active extension missing: " + str(TARGET))
main = LIVE / "main.py"
main_before = sha(main) if main.is_file() else None
archive = TARGET / "archive"
db = archive / "inventor_archive.sqlite3"
db_before = sha(db) if db.is_file() else None
archive_count_before = sum(1 for p in archive.rglob("*") if p.is_file()) if archive.is_dir() else 0
stage = Path(tempfile.mkdtemp(prefix="eira_lab_regression_stage_"))
backup = Path(tempfile.mkdtemp(prefix="eira_lab_regression_backup_"))
try:
    for rel in FILES:
        dst = stage / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(BASE + rel, headers={"User-Agent":"EIRA-InventorLab-Regression"})
        with urllib.request.urlopen(req, timeout=60) as r: data = r.read(8_000_000)
        if not data: die("empty download: " + rel)
        dst.write_bytes(data)
        if dst.suffix == ".py": compile(dst.read_text(encoding="utf-8"), str(dst), "exec")
        print("FETCHED=" + rel + " SHA256=" + hashlib.sha256(data).hexdigest())
    for rel in FILES:
        src = TARGET / rel
        if src.is_file():
            b = backup / rel; b.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, b)
    for rel in FILES:
        src = stage / rel; dst = TARGET / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".regression_tmp"); shutil.copy2(src, tmp); os.replace(tmp, dst)
    if main_before and sha(main) != main_before: die("protected main.py changed")
    if db_before and db.is_file() and sha(db) != db_before: die("archive database changed during code sync")
    archive_count_after = sum(1 for p in archive.rglob("*") if p.is_file()) if archive.is_dir() else 0
    if archive_count_after != archive_count_before: die(f"archive file count changed {archive_count_before}->{archive_count_after}")
    sys.path.insert(0, str(LIVE))
    for name in list(sys.modules):
        if name.startswith("extensions.eira_inventor_holographic_lab"):
            sys.modules.pop(name, None)
    test = importlib.import_module("extensions.eira_inventor_holographic_lab.regression_selftest")
    print("REGRESSION_FAST_START")
    fast = test.run(full=False, timeout=300)
    print(json.dumps(fast, indent=2, default=str))
    print("REGRESSION_FAST_PASS")
    print("REGRESSION_FULL_START")
    full = test.run(full=True, timeout=300)
    print(json.dumps(full, indent=2, default=str))
    print("REGRESSION_FULL_PASS")
    if main_before and sha(main) != main_before: die("protected main.py changed during regression")
    if db_before and db.is_file() and sha(db) != db_before: die("real archive database changed during regression")
    archive_count_end = sum(1 for p in archive.rglob("*") if p.is_file()) if archive.is_dir() else 0
    if archive_count_end != archive_count_before: die(f"real archive mutated during regression {archive_count_before}->{archive_count_end}")
    print("INVENTOR_LAB_END_TO_END=PASS")
    print("ARCHIVE_PRESERVED=true")
    print("CORE_MAIN_PRESERVED=true")
    print("SOURCE_COMMIT=" + SOURCE_COMMIT)
    print("RESTART_REQUIRED=true")
except BaseException as exc:
    print("REGRESSION_GATE_FAIL=" + type(exc).__name__ + ":" + str(exc))
    print("NEW_CODE_LEFT_INSTALLED_FOR_DIAGNOSIS=true")
    raise
finally:
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
