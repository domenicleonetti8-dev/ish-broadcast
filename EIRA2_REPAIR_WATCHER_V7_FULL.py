#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

VERSION = "7.0.1"
SCHEMA = "eira2_transport_request_v1"
PLAN_SCHEMA = "eira2_builder_plan_v4"
ROOT = Path(os.environ.get("EIRA_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + str(value))
    if ".git" in p.parts:
        raise RuntimeError("git_metadata_write_blocked")
    return p.as_posix()


def _inbox() -> str:
    path = ROOT / "eira_probe" / "watcher_inbox_v7"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def authorize_transport_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict) or request.get("schema") != SCHEMA:
        return {"authorized": False, "reason": "schema_mismatch"}

    op = str(request.get("operation") or "").casefold()
    if op not in {"inspect", "deploy"}:
        return {"authorized": False, "reason": "unsupported_operation"}

    if op == "inspect":
        return {
            "authorized": True,
            "authorized_by": "repair_watcher_ai",
            "watcher_version": VERSION,
            "operation": "inspect",
            "policy": "read_only",
        }

    dep = request.get("deployment") or {}
    autonomous_job = dep.get("autonomous_job") or {}
    target = dep.get("target") or {}

    try:
        target_path = _safe_rel(str(autonomous_job.get("target_path") or target.get("path") or ""))
    except Exception as exc:
        return {"authorized": False, "reason": str(exc)}

    if autonomous_job:
        if not str(autonomous_job.get("objective") or "").strip():
            return {"authorized": False, "reason": "autonomous_objective_missing"}
        if request.get("autonomous_engineering") is True:
            evidence = request.get("sandbox_evidence") or {}
            if evidence.get("sandbox_tests_passed") is not True:
                return {"authorized": False, "reason": "sandbox_tests_not_passed"}
            if str(evidence.get("target_path") or "") != target_path:
                return {"authorized": False, "reason": "sandbox_target_mismatch"}
        return {
            "authorized": True,
            "authorized_by": "repair_watcher_ai",
            "watcher_version": VERSION,
            "operation": "deploy",
            "deployment_mode": "autonomous_engineering",
            "target_path": target_path,
            "policy": "sandbox_first_builder_write_no_live_hash_gate",
        }

    source = dep.get("source") or {}
    if not source:
        return {"authorized": False, "reason": "source_missing"}

    if source.get("manifest"):
        try:
            _safe_rel(str(source.get("manifest") or ""))
        except Exception as exc:
            return {"authorized": False, "reason": str(exc)}
    else:
        source_path = str(source.get("path") or "")
        commit = str(source.get("commit") or "")
        if not source_path:
            return {"authorized": False, "reason": "source_path_missing"}
        try:
            _safe_rel(source_path)
        except Exception as exc:
            return {"authorized": False, "reason": str(exc)}
        if not COMMIT_RE.fullmatch(commit):
            return {"authorized": False, "reason": "source_commit_invalid"}

    return {
        "authorized": True,
        "authorized_by": "repair_watcher_ai",
        "watcher_version": VERSION,
        "operation": "deploy",
        "deployment_mode": "pinned_source",
        "target_path": target_path,
        "policy": "broad_eira_live_write_with_root_containment_staging_backup_rollback",
    }


def inspect_once() -> dict[str, Any]:
    inbox = Path(_inbox())
    index_path = inbox / "file_index.json"
    package_path = inbox / "surgery_package.json"
    if not index_path.is_file() or not package_path.is_file():
        return {"ok": True, "status": "idle", "watcher_version": VERSION, "builder_plan": None}

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        package = json.loads(package_path.read_text(encoding="utf-8"))
        rows = index.get("files") or []
        if not rows:
            raise RuntimeError("file_index_empty")

        stage = (inbox / "stage").resolve()
        stage.relative_to(ROOT)
        files = []
        seen_targets: set[str] = set()

        for row in rows:
            target = _safe_rel(str(row.get("target_path") or ""))
            staged = _safe_rel(str(row.get("staged_path") or ""))
            if target in seen_targets:
                raise RuntimeError("duplicate_target:" + target)
            seen_targets.add(target)

            expected = str(row.get("sha256") or "").lower()
            p = (stage / staged).resolve()
            p.relative_to(stage)
            if not p.is_file():
                raise RuntimeError("staged_missing:" + staged)
            actual = _sha(p)
            if expected and actual != expected:
                raise RuntimeError("staged_hash_mismatch:" + staged)

            files.append({
                "target_path": target,
                "staged_path": staged,
                "sha256": actual,
            })

        plan = {
            "schema": PLAN_SCHEMA,
            "authorized_by": "repair_watcher_ai",
            "watcher_version": VERSION,
            "created_unix": time.time(),
            "offsystem_stage_root": str(stage),
            "files": files,
            "package_fingerprint_sha256": package.get("package_fingerprint_sha256"),
            "authorization_contract": "validated_stage_then_builder_atomic_write",
        }
        out = ROOT / "eira_probe" / "eira2_builder_plan.json"
        _atomic(out, plan)
        return {
            "ok": True,
            "status": "authorized",
            "watcher_version": VERSION,
            "builder_plan": str(out),
            "file_count": len(files),
            "authorization_contract": plan["authorization_contract"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "rejected",
            "watcher_version": VERSION,
            "error": f"{type(exc).__name__}:{exc}",
        }


def health() -> dict[str, Any]:
    return {
        "ok": True,
        "name": "repair_watcher_ai",
        "version": VERSION,
        "root": str(ROOT),
        "plan_schema": PLAN_SCHEMA,
    }
