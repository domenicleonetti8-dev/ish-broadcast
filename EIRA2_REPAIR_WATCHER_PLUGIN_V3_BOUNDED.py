from __future__ import annotations

import importlib.util
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any

WATCHER_VERSION = "3.0.0-eira2-bounded-transport-authority"
LEGACY_NAME = "plugin_legacy_v2_6_0.py"
_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_legacy = None


def _safe_relpath(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path_missing")
    p = PurePosixPath(value.strip())
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("unsafe_path")
    if p.parts and p.parts[0] in {".git", ".."}:
        raise ValueError("unsafe_path")
    return p.as_posix()


def _deny(request_id: str, operation: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "authorized": False,
        "authorized_by": "repair_watcher_ai",
        "watcher_version": WATCHER_VERSION,
        "request_id": request_id,
        "operation": operation,
        "read_only": operation == "inspect",
        "builder_required": operation == "deploy",
        "write_authority_granted": False,
        "superprobe_required_for_authorization": False,
        "reason": reason,
        "generated_unix": time.time(),
    }


def authorize_transport_request(request: Any) -> dict[str, Any]:
    started = time.perf_counter()
    if not isinstance(request, dict):
        return _deny("", "", "request_not_dict")

    schema = request.get("schema")
    request_id = str(request.get("request_id") or "")
    operation = str(request.get("operation") or "")

    if schema != "eira2_transport_request_v1":
        return _deny(request_id, operation, "schema_mismatch")
    if not request_id:
        return _deny(request_id, operation, "request_id_missing")
    if operation not in {"inspect", "deploy"}:
        return _deny(request_id, operation, "operation_not_allowed")

    if operation == "inspect":
        paths = request.get("inspection_paths") or []
        try:
            for value in paths:
                _safe_relpath(value)
        except Exception as exc:
            return _deny(request_id, operation, f"inspection_path_invalid:{type(exc).__name__}")
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return {
            "ok": True,
            "authorized": True,
            "authorized_by": "repair_watcher_ai",
            "watcher_version": WATCHER_VERSION,
            "request_id": request_id,
            "operation": operation,
            "read_only": True,
            "builder_required": False,
            "fast_read_only_authorization": True,
            "fast_deploy_authorization": False,
            "superprobe_required_for_authorization": False,
            "write_authority_granted": False,
            "authorization_elapsed_ms": elapsed_ms,
            "generated_unix": time.time(),
        }

    deployment = request.get("deployment")
    if not isinstance(deployment, dict):
        return _deny(request_id, operation, "deployment_missing")
    source = deployment.get("source")
    target = deployment.get("target")
    if not isinstance(source, dict) or not isinstance(target, dict):
        return _deny(request_id, operation, "deployment_source_or_target_missing")

    commit = str(source.get("commit") or "")
    if not _HEX40.match(commit):
        return _deny(request_id, operation, "source_commit_invalid")
    try:
        source_path = _safe_relpath(source.get("path"))
        target_path = _safe_relpath(target.get("path"))
    except Exception as exc:
        return _deny(request_id, operation, f"deployment_path_invalid:{type(exc).__name__}")

    requirements = request.get("requirements") or {}
    if requirements and not isinstance(requirements, dict):
        return _deny(request_id, operation, "requirements_not_dict")
    if isinstance(requirements, dict):
        if requirements.get("watcher_authorizes") is False:
            return _deny(request_id, operation, "watcher_authorization_explicitly_disabled")
        if requirements.get("builder_invoked") is False:
            return _deny(request_id, operation, "builder_invocation_explicitly_disabled")

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "ok": True,
        "authorized": True,
        "authorized_by": "repair_watcher_ai",
        "watcher_version": WATCHER_VERSION,
        "request_id": request_id,
        "operation": operation,
        "read_only": False,
        "builder_required": True,
        "fast_read_only_authorization": False,
        "fast_deploy_authorization": True,
        "superprobe_required_for_authorization": False,
        "write_authority_granted": True,
        "source_commit": commit.lower(),
        "source_path": source_path,
        "target_path": target_path,
        "authorization_elapsed_ms": elapsed_ms,
        "generated_unix": time.time(),
    }


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
