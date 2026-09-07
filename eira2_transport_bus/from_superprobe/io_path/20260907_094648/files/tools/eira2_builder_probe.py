#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_builder_probe_v1"
PLAN_SCHEMA = "eira2_watcher_builder_plan_v1"
DEFAULT_ROOT = "/media/domenicleonetti/easystore/EIRA/LIVE"
DEFAULT_PLAN = "eira_probe/eira2_builder_plan.json"
DEFAULT_RECEIPT = "eira_probe/eira2_builder_receipt.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(value: str) -> str:
    clean = str(value or "").replace("\\", "/").strip("/")
    if not clean or ".." in Path(clean).parts:
        raise RuntimeError(f"unsafe_relative_path:{value}")
    return clean


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _compile_python(path: Path) -> None:
    if path.suffix == ".py":
        result = subprocess.run([sys.executable, "-m", "py_compile", str(path)], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"python_compile_failed:{path}:{(result.stderr or result.stdout)[-800:]}")


def _validate_bash(block: str) -> None:
    if not block.strip():
        return
    result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError("bash_syntax_invalid:" + (result.stderr or result.stdout)[-800:])


def _load_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise RuntimeError("builder_plan_schema_invalid")
    if plan.get("authorized_by") != "repair_watcher_ai":
        raise RuntimeError("builder_plan_not_watcher_authorized")
    if plan.get("superprobe_evidence_verified") is not True:
        raise RuntimeError("builder_plan_missing_verified_superprobe_evidence")
    return plan


def execute(root: Path, plan: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    if plan.get("eira2_only") is not True:
        raise RuntimeError("builder_probe_eira2_only_required")
    if plan.get("builder_probe_may_decide_changes") is not False:
        raise RuntimeError("builder_probe_authority_contract_invalid")

    work_root = Path(plan.get("offsystem_stage_root") or "").expanduser().resolve()
    try:
        work_root.relative_to(root)
        raise RuntimeError("builder_stage_must_be_off_live")
    except ValueError:
        pass
    if not work_root.is_dir():
        raise RuntimeError(f"offsystem_stage_missing:{work_root}")

    backup_root = root / "eira_probe" / "builder_backups" / time.strftime("%Y%m%dT%H%M%S")
    backup_root.mkdir(parents=True, exist_ok=True)
    applied: list[dict[str, Any]] = []
    created_bridges: list[dict[str, Any]] = []
    retired: list[str] = []

    try:
        for row in plan.get("files") or []:
            source_rel = _safe_rel(row.get("staged_path"))
            target_rel = _safe_rel(row.get("target_path"))
            source = (work_root / source_rel).resolve()
            target = (root / target_rel).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"target_outside_live:{target_rel}") from exc
            if not source.is_file():
                raise RuntimeError(f"staged_source_missing:{source_rel}")
            expected = str(row.get("sha256") or "").lower()
            if len(expected) != 64 or _sha256(source) != expected:
                raise RuntimeError(f"staged_source_hash_mismatch:{source_rel}")
            _compile_python(source)

            before_hash = _sha256(target) if target.is_file() else None
            if target.exists():
                backup = backup_root / target_rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)

            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=str(target.parent), prefix=target.name + ".builder.", delete=False) as tmp:
                temp_target = Path(tmp.name)
                with source.open("rb") as src:
                    shutil.copyfileobj(src, tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(temp_target, target)
            after_hash = _sha256(target)
            if after_hash != expected:
                raise RuntimeError(f"post_replace_hash_mismatch:{target_rel}")
            applied.append({"target_path": target_rel, "before_sha256": before_hash, "after_sha256": after_hash})

        for bridge in plan.get("bridges") or []:
            target_rel = _safe_rel(bridge.get("target_path"))
            target = (root / target_rel).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"bridge_target_outside_live:{target_rel}") from exc
            if target.exists():
                backup = backup_root / target_rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            content = str(bridge.get("content") or "")
            if bridge.get("kind") == "bash":
                _validate_bash(content)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".builder.tmp")
            tmp.write_text(content, encoding="utf-8")
            if target.suffix == ".py":
                _compile_python(tmp)
            os.replace(tmp, target)
            created_bridges.append({"target_path": target_rel, "sha256": _sha256(target), "kind": bridge.get("kind")})

        for block in plan.get("bash_blocks") or []:
            script = str(block.get("script") or "")
            _validate_bash(script)
            result = subprocess.run(["bash", "-lc", script], cwd=str(root), capture_output=True, text=True, timeout=int(block.get("timeout_seconds") or 120))
            if result.returncode != 0:
                raise RuntimeError("watcher_bash_block_failed:" + (result.stderr or result.stdout)[-1200:])

        if plan.get("acceptance_verified") is True:
            for rel in plan.get("retire_after_acceptance") or []:
                target_rel = _safe_rel(rel)
                target = (root / target_rel).resolve()
                try:
                    target.relative_to(root)
                except ValueError as exc:
                    raise RuntimeError(f"retire_target_outside_live:{target_rel}") from exc
                if target.exists():
                    backup = backup_root / "retired" / target_rel
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(backup))
                    retired.append(target_rel)

        receipt = {
            "ok": True,
            "schema": SCHEMA,
            "mode": "watcher_authorized_write_transport",
            "eira2_only": True,
            "authorized_by": "repair_watcher_ai",
            "superprobe_remained_read_only": True,
            "builder_probe_made_no_change_decisions": True,
            "backup_root": str(backup_root),
            "applied_files": applied,
            "constructed_bridges": created_bridges,
            "retired_after_acceptance": retired,
            "requires_post_superprobe_verification": True,
            "generated_unix": time.time(),
        }
        _atomic_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        # Immediate local rollback for anything already touched. Full transaction acceptance remains Watcher's job.
        for row in reversed(applied):
            rel = row["target_path"]
            backup = backup_root / rel
            target = root / rel
            if backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
            elif target.exists() and row.get("before_sha256") is None:
                target.unlink()
        receipt = {
            "ok": False,
            "schema": SCHEMA,
            "error": f"{type(exc).__name__}:{exc}"[:1400],
            "rollback_attempted": True,
            "backup_root": str(backup_root),
            "applied_before_failure": applied,
            "requires_watcher_reconciliation": True,
            "generated_unix": time.time(),
        }
        _atomic_json(receipt_path, receipt)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="EIRA2 BuilderProbe: Watcher-controlled write transport and bridge constructor.")
    parser.add_argument("--root", default=os.getenv("EIRA2_LIVE_ROOT", DEFAULT_ROOT))
    parser.add_argument("--plan", default=DEFAULT_PLAN)
    parser.add_argument("--receipt", default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    receipt_path = Path(args.receipt)
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    plan = _load_plan(plan_path)
    result = execute(root, plan, receipt_path)
    print(json.dumps({"ok": result["ok"], "receipt": str(receipt_path), "applied_files": len(result.get("applied_files") or []), "bridges": len(result.get("constructed_bridges") or [])}, sort_keys=True))
    print("EIRA2_BUILDER_PROBE=PASS")


if __name__ == "__main__":
    main()
