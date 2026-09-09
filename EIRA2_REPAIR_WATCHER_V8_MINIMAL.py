#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

WATCHER_VERSION = "8.0.0-minimal-transport"
VERSION = WATCHER_VERSION
SCHEMA = "eira2_transport_request_v1"
PLAN_SCHEMA = "eira2_builder_plan_v4"
LEGACY_NAME = "plugin_legacy_v2_6_0.py"
ROOT = Path(os.environ.get("EIRA_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
_legacy = None


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


def _safe_relpath(value: Any) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise ValueError("unsafe_relative_path")
    if ".git" in p.parts:
        raise ValueError("git_metadata_write_blocked")
    return p.as_posix()


def _inbox() -> str:
    p = ROOT / "eira_probe" / "watcher_inbox_v8"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _overlap(a: str, b: str) -> bool:
    ap, bp = Path(a).parts, Path(b).parts
    n = min(len(ap), len(bp))
    return ap[:n] == bp[:n]


def authorize_transport_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict) or request.get("schema") != SCHEMA:
        return {"authorized": False, "reason": "schema_mismatch"}
    op = str(request.get("operation") or "").casefold()
    if op == "inspect":
        return {"authorized": True, "authorized_by": "repair_watcher_ai", "watcher_version": WATCHER_VERSION, "operation": "inspect", "policy": "read_only"}
    if op != "deploy":
        return {"authorized": False, "reason": "unsupported_operation"}
    dep = request.get("deployment") or {}
    auto = dep.get("autonomous_job") or {}
    target = dep.get("target") or {}
    try:
        target_path = _safe_relpath(auto.get("target_path") or target.get("path"))
    except Exception as exc:
        return {"authorized": False, "reason": str(exc)}
    return {
        "authorized": True,
        "authorized_by": "repair_watcher_ai",
        "watcher_version": WATCHER_VERSION,
        "operation": "deploy",
        "target_path": target_path,
        "policy": "payload_hash_no_duplicate_or_overlap_then_builder",
        "live_before_hash_gate": False,
    }


def inspect_once() -> dict[str, Any]:
    inbox = Path(_inbox())
    idx, pkg = inbox / "file_index.json", inbox / "surgery_package.json"
    if not idx.is_file() or not pkg.is_file():
        return {"ok": True, "status": "idle", "watcher_version": WATCHER_VERSION, "builder_plan": None}
    try:
        index = json.loads(idx.read_text(encoding="utf-8"))
        package = json.loads(pkg.read_text(encoding="utf-8"))
        rows = index.get("files") or []
        if not rows:
            raise RuntimeError("file_index_empty")
        stage = (inbox / "stage").resolve()
        stage.relative_to(ROOT)
        files: list[dict[str, str]] = []
        targets: list[str] = []
        for row in rows:
            target = _safe_relpath(row.get("target_path"))
            staged = _safe_relpath(row.get("staged_path"))
            for prior in targets:
                if _overlap(prior, target):
                    raise RuntimeError(f"duplicate_or_overlapping_target:{prior}:{target}")
            targets.append(target)
            p = (stage / staged).resolve()
            p.relative_to(stage)
            if not p.is_file():
                raise RuntimeError("staged_missing:" + staged)
            actual = _sha(p)
            expected = str(row.get("sha256") or "").lower()
            if expected and actual != expected:
                raise RuntimeError("staged_hash_mismatch:" + staged)
            files.append({"target_path": target, "staged_path": staged, "sha256": actual})
        plan = {
            "schema": PLAN_SCHEMA,
            "authorized_by": "repair_watcher_ai",
            "watcher_version": WATCHER_VERSION,
            "created_unix": time.time(),
            "offsystem_stage_root": str(stage),
            "files": files,
            "package_fingerprint_sha256": package.get("package_fingerprint_sha256"),
            "live_before_hash_gate": False,
            "authorization_contract": "payload_hash_no_duplicate_or_overlap_then_builder",
        }
        out = ROOT / "eira_probe" / "eira2_builder_plan.json"
        _atomic(out, plan)
        return {"ok": True, "status": "authorized", "watcher_version": WATCHER_VERSION, "builder_plan": str(out), "file_count": len(files)}
    except Exception as exc:
        return {"ok": False, "status": "rejected", "watcher_version": WATCHER_VERSION, "error": f"{type(exc).__name__}:{exc}"}


def health() -> dict[str, Any]:
    return {"ok": True, "name": "repair_watcher_ai", "version": WATCHER_VERSION, "plan_schema": PLAN_SCHEMA, "legacy": LEGACY_NAME, "live_before_hash_gate": False}


def _load_legacy():
    global _legacy
    if _legacy is not None:
        return _legacy
    path = Path(__file__).with_name(LEGACY_NAME)
    if not path.exists():
        raise AttributeError(f"legacy_watcher_missing:{path}")
    spec = importlib.util.spec_from_file_location("eira2_repair_watcher_legacy", path)
    if spec is None or spec.loader is None:
        raise AttributeError("legacy_watcher_spec_failed")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _legacy = mod
    return mod


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_load_legacy(), name)
