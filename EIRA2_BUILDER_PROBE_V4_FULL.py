#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "eira2_builder_plan_v4"
RECEIPT_SCHEMA = "eira2_builder_receipt_v4"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + str(value))
    if ".git" in p.parts:
        raise RuntimeError("git_metadata_write_blocked")
    return p.as_posix()


def compile_if_python(path: Path, target: str) -> None:
    if not target.endswith(".py"):
        return
    q = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if q.returncode:
        raise RuntimeError("python_compile_failed:" + target + ":" + q.stderr[-1200:])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    plan_path = Path(args.plan).resolve()
    receipt = Path(args.receipt).resolve()
    tx = f"{int(time.time())}-{os.getpid()}"
    backups = root / "eira_probe" / "builder_backups_v4" / tx

    applied: list[str] = []
    backup_rows: list[tuple[Path, Path, bool]] = []

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("schema") != PLAN_SCHEMA:
            raise RuntimeError("builder_plan_schema_mismatch")
        if plan.get("authorized_by") != "repair_watcher_ai":
            raise RuntimeError("watcher_authorization_missing")

        stage = Path(str(plan.get("offsystem_stage_root") or "")).resolve()
        if not stage.is_dir():
            raise RuntimeError("stage_root_missing")

        rows = plan.get("files") or []
        if not rows:
            raise RuntimeError("files_missing")

        verified = []
        seen_targets: set[str] = set()
        for row in rows:
            staged_rel = safe_rel(str(row.get("staged_path") or ""))
            target_rel = safe_rel(str(row.get("target_path") or ""))
            if target_rel in seen_targets:
                raise RuntimeError("duplicate_target:" + target_rel)
            seen_targets.add(target_rel)

            src = (stage / staged_rel).resolve()
            src.relative_to(stage)
            if not src.is_file():
                raise RuntimeError("staged_missing:" + staged_rel)

            expected = str(row.get("sha256") or "").lower()
            actual = sha(src)
            if expected and actual != expected:
                raise RuntimeError("staged_hash_mismatch:" + staged_rel)

            compile_if_python(src, target_rel)

            target = (root / target_rel).resolve()
            target.relative_to(root)
            if target.exists() and not target.is_file():
                raise RuntimeError("target_not_regular_file:" + target_rel)

            verified.append((src, target, target_rel, actual))

        # Backup the state that exists at write time. There is deliberately no
        # expected-before hash gate: legitimate LIVE changes do not block transport.
        for _, target, target_rel, _ in verified:
            backup = backups / target_rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            existed = target.is_file()
            if existed:
                shutil.copy2(target, backup)
            backup_rows.append((target, backup, existed))

        for src, target, target_rel, payload_sha in verified:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + f".eira2tmp.{os.getpid()}")
            shutil.copy2(src, tmp)
            os.replace(tmp, target)
            actual_after = sha(target)
            if actual_after != payload_sha:
                raise RuntimeError("post_write_hash_mismatch:" + target_rel)
            applied.append(target_rel)

        payload = {
            "schema": RECEIPT_SCHEMA,
            "ok": True,
            "transaction_id": tx,
            "authorized_by": "repair_watcher_ai",
            "applied": applied,
            "live_before_hash_gate": False,
            "payload_integrity_verified": True,
            "post_write_verified": True,
            "rollback_performed": False,
            "completed_unix": time.time(),
        }
        atomic_json(receipt, payload)
        print("EIRA2_BUILDER_PROBE=PASS")
        print(json.dumps(payload, sort_keys=True))
        return 0

    except Exception as exc:
        rolled = False
        rollback_errors = []
        for target, backup, existed in reversed(backup_rows):
            try:
                if existed and backup.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
                    rolled = True
                elif not existed and target.exists():
                    target.unlink()
                    rolled = True
            except Exception as rb_exc:
                rollback_errors.append(f"{type(rb_exc).__name__}:{rb_exc}")

        payload = {
            "schema": RECEIPT_SCHEMA,
            "ok": False,
            "transaction_id": tx,
            "applied": applied,
            "live_before_hash_gate": False,
            "rollback_performed": rolled,
            "rollback_errors": rollback_errors[-10:],
            "error": f"{type(exc).__name__}:{exc}",
            "completed_unix": time.time(),
        }
        atomic_json(receipt, payload)
        print("EIRA2_BUILDER_PROBE=FAIL", file=sys.stderr)
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
