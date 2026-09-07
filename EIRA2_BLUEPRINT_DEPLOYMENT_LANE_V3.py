#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_builder_blueprint_v2"
PACKET_ID = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
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


def run(cmd: list[str], cwd: Path, timeout: int = 1200) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
    return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-12000:]}


def safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError(f"unsafe_relative_path:{value}")
    return p.as_posix()


def load_packet(path: Path) -> dict[str, Any]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise RuntimeError("blueprint_schema_mismatch")
    pid = str(packet.get("packet_id") or "")
    if not PACKET_ID.fullmatch(pid):
        raise RuntimeError("invalid_packet_id")
    if packet.get("apply") is not True:
        raise RuntimeError("blueprint_apply_not_true")
    if not isinstance(packet.get("payloads"), list) or not packet["payloads"]:
        raise RuntimeError("payloads_missing")
    commit = str(packet.get("source_commit") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("source_commit_invalid")
    return packet


def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    rel = safe_rel(repo_path)
    p = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{rel}"], capture_output=True, timeout=120, check=False)
    if p.returncode:
        raise RuntimeError(f"source_blob_missing:{rel}:{p.stderr[-500:].decode(errors='replace')}")
    return p.stdout


def materialize(root: Path, packet: dict[str, Any], repo: Path) -> tuple[Path, list[dict[str, Any]]]:
    stage = Path("/tmp/eira2_blueprint_staging") / str(packet["packet_id"])
    if stage.exists():
        shutil.rmtree(stage)
    payload_root = stage / "payloads"
    payload_root.mkdir(parents=True)
    rows = []
    for i, item in enumerate(packet["payloads"]):
        repo_path = safe_rel(str(item.get("repo_path") or ""))
        target_path = safe_rel(str(item.get("target_path") or ""))
        target = (root / target_path).resolve()
        target.relative_to(root)
        before = str(item.get("before_sha256") or "").lower()
        if before and (not target.is_file() or sha256_file(target) != before):
            raise RuntimeError(f"live_before_hash_mismatch:{target_path}")
        data = git_blob(repo, str(packet["source_commit"]), repo_path)
        staged_rel = f"payloads/{i:03d}_{Path(target_path).name}"
        staged = stage / staged_rel
        staged.write_bytes(data)
        if target_path.endswith(".py"):
            q = subprocess.run([sys.executable, "-m", "py_compile", str(staged)], capture_output=True, text=True, timeout=60)
            if q.returncode:
                raise RuntimeError(f"payload_python_compile_failed:{target_path}:{q.stderr[-800:]}")
        rows.append({"staged_path": staged_rel, "target_path": target_path, "sha256": sha256_bytes(data), "before_sha256": before or None})
    return stage, rows


def load_watcher(root: Path):
    path = root / "extensions" / "repair_watcher_ai" / "plugin.py"
    spec = importlib.util.spec_from_file_location("eira2_live_repair_watcher_v3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("repair_watcher_import_failed")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def superprobe(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    result = run([sys.executable, str(root / "tools" / "eira2_superprobe_engine.py"), "--root", str(root)], root)
    report_path = root / "eira_probe" / "eira2_superprobe_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    if result["returncode"] != 0 or report.get("ok") is not True:
        raise RuntimeError("superprobe_failed")
    return result, report


def watcher_plan(watcher: Any, packet: dict[str, Any], stage: Path, rows: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    build = getattr(watcher, "_build_plan", None)
    if not callable(build):
        raise RuntimeError("watcher_build_plan_missing")
    package = {
        "schema": "eira2_verified_replacement_package_v1",
        "packet_id": packet["packet_id"],
        "package_id": packet["packet_id"],
        "eira2_only": True,
        "offsystem_stage_root": str(stage),
        "stage_root": str(stage),
        "source_commit": packet["source_commit"],
        "bridges": list(packet.get("bridges") or []),
        "bash_blocks": list(packet.get("bash_blocks") or []),
        "retire_after_acceptance": list(packet.get("retire_after_acceptance") or []),
    }
    index = {"schema": "eira2_verified_replacement_index_v1", "files": rows}
    sig = inspect.signature(build)
    args = []
    for p in sig.parameters.values():
        name = p.name.casefold()
        if "package" in name:
            args.append(package)
        elif "index" in name or "files" in name:
            args.append(index)
        elif "report" in name or "probe" in name or "evidence" in name:
            args.append(report)
        else:
            raise RuntimeError("watcher_build_plan_signature_unsupported:" + str(sig))
    plan = build(*args)
    if not isinstance(plan, dict):
        raise RuntimeError("watcher_plan_not_dict")
    plan = dict(plan)
    plan["schema"] = "eira2_watcher_builder_plan_v1"
    plan["authorized_by"] = "repair_watcher_ai"
    plan["superprobe_evidence_verified"] = True
    plan["eira2_only"] = True
    plan["builder_probe_may_decide_changes"] = False
    plan["offsystem_stage_root"] = str(stage)
    plan["files"] = rows
    plan.setdefault("bridges", list(packet.get("bridges") or []))
    plan.setdefault("bash_blocks", list(packet.get("bash_blocks") or []))
    plan.setdefault("retire_after_acceptance", list(packet.get("retire_after_acceptance") or []))
    plan["acceptance_verified"] = False
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--source-repo-root", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve(); packet_path = Path(a.packet).resolve(); repo = Path(a.source_repo_root).resolve()
    packet = load_packet(packet_path); pid = str(packet["packet_id"])
    receipt = root / "eira_probe" / "blueprint_receipts" / f"{pid}.lane_v2.json"
    try:
        stage, rows = materialize(root, packet, repo)
        pre, report = superprobe(root)
        watcher, watcher_path = load_watcher(root)
        plan = watcher_plan(watcher, packet, stage, rows, report)
        plan_path = root / "eira_probe" / "eira2_builder_plan.json"
        atomic_json(plan_path, plan)
        builder_receipt_path = root / "eira_probe" / "eira2_builder_receipt.json"
        build = run([sys.executable, str(root / "tools" / "eira2_builder_probe.py"), "--root", str(root), "--plan", str(plan_path), "--receipt", str(builder_receipt_path)], root)
        if build["returncode"] != 0:
            raise RuntimeError("builder_failed:" + (build["stderr"] or build["stdout"])[-1200:])
        post, post_report = superprobe(root)
        builder_receipt = json.loads(builder_receipt_path.read_text(encoding="utf-8")) if builder_receipt_path.is_file() else {}
        accepted = builder_receipt.get("ok") is True and post_report.get("ok") is True
        atomic_json(receipt, {"schema":"eira2_blueprint_lane_v3_receipt","packet_id":pid,"status":"accepted" if accepted else "failed_postflight","watcher_plan_authority_used":True,"watcher_plugin":str(watcher_path),"builder_receipt":builder_receipt,"preflight":pre,"postflight":post,"generated_unix":time.time()})
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V3":"PASS" if accepted else "FAIL","packet_id":pid}, indent=2))
        return 0 if accepted else 3
    except Exception as exc:
        atomic_json(receipt, {"schema":"eira2_blueprint_lane_v3_receipt","packet_id":pid,"status":"rejected_or_failed","error":f"{type(exc).__name__}:{exc}"[:1800],"generated_unix":time.time()})
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V3":"FAIL","packet_id":pid,"error":f"{type(exc).__name__}:{exc}"}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
