from __future__ import annotations

import hashlib, json, os, subprocess, sys, threading, time
from pathlib import Path
from typing import Any

ROLE = "repair_watcher_ai"
VERSION = "2.4.0-eira2-superprobe-v4"
SUPERPROBE_SCHEMA = "eira2_superprobe_forensic_v4"
SUPERPROBE_EVIDENCE_SCHEMA = "eira2_superprobe_evidence_v4"
PACKAGE_SCHEMA = "eira2_offsystem_surgery_package_v2"
INDEX_SCHEMA = "eira2_offsystem_file_index_v2"
BUILDER_PLAN_SCHEMA = "eira2_watcher_builder_plan_v2"
_LOCK = threading.RLock(); _STOP = threading.Event(); _THREAD: threading.Thread | None = None
_LAST_CHECK = 0.0; _LAST_ERROR = ""; _LAST_RESULT: dict[str, Any] = {}


def _root() -> Path:
    return Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).expanduser().resolve()


def _probe_dir() -> Path:
    p = _root() / "eira_probe"; p.mkdir(parents=True, exist_ok=True); return p


def _inbox() -> Path:
    p = Path(os.environ.get("EIRA2_SURGERY_INBOX", str(_probe_dir() / "offsystem_inbox"))).expanduser().resolve(); p.mkdir(parents=True, exist_ok=True); return p


def _read(path: Path) -> dict[str, Any]:
    try:
        v = json.loads(path.read_text(encoding="utf-8")); return v if isinstance(v, dict) else {}
    except Exception: return {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); t = path.with_name(path.name + ".tmp"); t.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"); os.replace(t, path)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""): h.update(c)
    return h.hexdigest()


def _run_superprobe() -> dict[str, Any]:
    root = _root(); probe = root / "tools" / "eira2_superprobe_engine.py"
    r = subprocess.run([sys.executable, str(probe), "--root", str(root), "--json"], cwd=str(root), capture_output=True, text=True, timeout=2400)
    combo = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode or "EIRA2_SUPERPROBE=PASS" not in combo: raise RuntimeError("superprobe_rejected:" + combo[-1200:])
    report = _read(_probe_dir() / "eira2_superprobe_report.json")
    if report.get("ok") is not True or report.get("schema") != SUPERPROBE_SCHEMA or report.get("evidence_schema") != SUPERPROBE_EVIDENCE_SCHEMA or report.get("mutates_live") is not False:
        raise RuntimeError("superprobe_receipt_invalid")
    for name, row in (report.get("artifacts") or {}).items():
        p = Path(str((row or {}).get("path") or ""))
        if not p.is_file() or _sha(p) != str((row or {}).get("sha256") or ""):
            raise RuntimeError(f"superprobe_artifact_invalid:{name}")
    return report


def _verify_package() -> tuple[dict[str, Any], dict[str, Any]]:
    inbox = _inbox(); package, index = _read(inbox / "surgery_package.json"), _read(inbox / "file_index.json")
    if package.get("schema") != PACKAGE_SCHEMA or index.get("schema") != INDEX_SCHEMA: raise RuntimeError("offsystem_package_missing_or_invalid")
    if package.get("built_off_live") is not True or package.get("writes_live") is not False or package.get("eira2_only") is not True: raise RuntimeError("offsystem_package_authority_invalid")
    if _sha(inbox / "file_index.json") != package.get("file_index_sha256"): raise RuntimeError("offsystem_file_index_hash_mismatch")
    seen = set()
    for row in index.get("files") or []:
        target, staged_rel, digest = str(row.get("target_path") or ""), str(row.get("staged_path") or row.get("target_path") or ""), str(row.get("sha256") or "")
        if not target or target in seen or ".." in Path(target).parts: raise RuntimeError("offsystem_target_invalid")
        seen.add(target); staged = (inbox / "stage" / staged_rel).resolve(); staged.relative_to((inbox / "stage").resolve())
        if not staged.is_file() or _sha(staged) != digest: raise RuntimeError(f"offsystem_staged_hash_invalid:{target}")
    if sorted(seen) != sorted(package.get("targets") or []): raise RuntimeError("offsystem_targets_mismatch")
    return package, index


def _impact(report: dict[str, Any], target: str) -> dict[str, Any]:
    row = (report.get("artifacts") or {}).get("semantic_impact_index") or {}
    payload = _read(Path(str(row.get("path") or "")))
    legacy = (payload.get("impact_index") or {}).get(target) or (payload.get("files") or {})
    if isinstance(legacy, dict) and target in legacy:
        value = legacy.get(target)
        return dict(value) if isinstance(value, dict) else {}
    for item in payload.get("rows") or []:
        if isinstance(item, dict) and str(item.get("path") or "") == target:
            return dict(item)
    return {}


def _build_plan(report: dict[str, Any], package: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    files, blast = [], {}
    for row in index.get("files") or []:
        target = str(row.get("target_path")); files.append({"target_path": target, "staged_path": str(row.get("staged_path") or target), "sha256": str(row.get("sha256"))}); blast[target] = _impact(report, target)
    fp = str(report.get("evidence_bundle_fingerprint_sha256") or "")
    if not fp:
        raise RuntimeError("superprobe_evidence_fingerprint_missing")
    return {"schema": BUILDER_PLAN_SCHEMA, "authorized_by": ROLE, "watcher_version": VERSION, "eira2_only": True, "superprobe_evidence_verified": True, "superprobe_evidence_fingerprint_sha256": fp, "pre_superprobe_fingerprint_sha256": fp, "package_fingerprint_sha256": package.get("package_fingerprint_sha256"), "source_commit_sha": package.get("source_commit_sha"), "builder_probe_may_decide_changes": False, "offsystem_stage_root": str((_inbox() / "stage").resolve()), "files": files, "bridges": [], "bash_blocks": [], "semantic_blast_radius": blast, "requires_package_reseal": True, "requires_post_superprobe": True, "rollback_on_post_probe_failure": True, "retire_after_acceptance": [], "generated_unix": time.time()}


def inspect_once() -> dict[str, Any]:
    global _LAST_CHECK, _LAST_ERROR, _LAST_RESULT
    with _LOCK:
        _LAST_CHECK = time.time()
        try:
            report = _run_superprobe(); package, index = _verify_package(); plan = _build_plan(report, package, index); path = _probe_dir() / "eira2_builder_plan.json"; _write(path, plan)
            _LAST_ERROR = ""; _LAST_RESULT = {"ok": True, "status": "builder_plan_ready", "builder_plan": str(path), "planned_files": len(plan["files"]), "evidence_fingerprint": plan["pre_superprobe_fingerprint_sha256"], "package_fingerprint": plan["package_fingerprint_sha256"], "apply_enabled": True}; return dict(_LAST_RESULT)
        except Exception as exc:
            _LAST_ERROR = f"{type(exc).__name__}:{exc}"[:1400]; _LAST_RESULT = {"ok": False, "status": "builder_plan_rejected", "error": _LAST_ERROR}; return dict(_LAST_RESULT)


def deploy_builder_probe() -> dict[str, Any]:
    plan = inspect_once()
    if not plan.get("ok"): return plan
    root = _root(); executor = root / "tools" / "eira2_transaction_executor.py"
    r = subprocess.run([sys.executable, str(executor), "--root", str(root), "--inbox", str(_inbox()), "--plan", str(_probe_dir() / "eira2_builder_plan.json")], cwd=str(root), capture_output=True, text=True, timeout=3600)
    combo = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode or "EIRA2_TRANSACTION_EXECUTOR=PASS" not in combo: return {"ok": False, "status": "transaction_failed_or_rolled_back", "detail": combo[-1600:]}
    receipt = _read(_probe_dir() / "eira2_transaction_receipt.json"); return {"ok": receipt.get("ok") is True, "status": receipt.get("status"), "receipt": receipt}


def check_once(*, apply_if_safe: bool = False) -> dict[str, Any]: return deploy_builder_probe() if apply_if_safe else inspect_once()
def _loop(interval_seconds: int) -> None:
    while not _STOP.wait(max(300, int(interval_seconds))): inspect_once()
def boot(interval_seconds: int = 900) -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive(): return status()
        _STOP.clear(); initial = inspect_once(); _THREAD = threading.Thread(target=_loop, args=(interval_seconds,), name="eira2-repair-watcher", daemon=True); _THREAD.start(); return {"ok": True, "status": "watching", "initial": initial, **status()}
def stop() -> dict[str, Any]:
    global _THREAD
    _STOP.set()
    if _THREAD and _THREAD.is_alive(): _THREAD.join(timeout=3)
    _THREAD = None; return status()
def status() -> dict[str, Any]: return {"ok": True, "node": ROLE, "version": VERSION, "watching": bool(_THREAD and _THREAD.is_alive()), "last_check": _LAST_CHECK, "last_error": _LAST_ERROR, "last_result": dict(_LAST_RESULT), "eira2_only": True, "superprobe_role": "read_only_exploratory_watchdog", "builder_probe_role": "watcher_controlled_write_transport_and_constructor", "single_watcher_authority": True, "apply_enabled": True}
def register(context=None): return {"node": ROLE, "version": VERSION, "ask": ask, "boot": boot, "status": status, "stop": stop, "check_once": check_once, "inspect_once": inspect_once, "deploy_builder_probe": deploy_builder_probe}
def ask(prompt: str, context=None):
    text = str(prompt or "").casefold()
    if any(w in text for w in ("deploy", "build", "repair", "apply")): return deploy_builder_probe()
    if any(w in text for w in ("inspect", "probe", "plan", "forensic", "semantic")): return inspect_once()
    if "stop" in text: return stop()
    return status()
