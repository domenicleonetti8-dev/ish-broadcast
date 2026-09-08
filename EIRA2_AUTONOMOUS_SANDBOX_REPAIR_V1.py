#!/usr/bin/env python3
from __future__ import annotations

import hashlib, importlib.util, json, os, py_compile, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_autonomous_repair_v1"
DENY_PREFIXES = (
    "main.py", "engine/", "brain/", "council/", "routers/", "voice/",
    "identity/", "memory/", "reasoning/", "speech/",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file(): return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + value)
    return p.as_posix()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_load_failed:" + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_verified_engineering(root: Path):
    candidates = [
        root / "extensions" / "verified_engineering_ai" / "plugin.py",
        root / "extensions" / "verified_engineering_ai" / "__init__.py",
        root / "extensions" / "verified_engineering_ai.py",
    ]
    for p in candidates:
        if p.is_file():
            mod = load_module(p, "eira2_verified_engineering_runtime")
            fn = getattr(mod, "ask", None)
            if callable(fn): return fn, p
    raise RuntimeError("verified_engineering_ask_unavailable")


def load_watcher(root: Path):
    p = root / "extensions" / "repair_watcher_ai" / "plugin.py"
    if not p.is_file(): raise RuntimeError("repair_watcher_plugin_missing")
    return load_module(p, "eira2_autonomous_repair_watcher")


def watcher_authorize_candidate(root: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    watcher = load_watcher(root)
    for name in ("authorize_candidate", "approve_candidate", "authorize_repair", "authorize_transport_request"):
        fn = getattr(watcher, name, None)
        if not callable(fn): continue
        payload = evidence if name != "authorize_transport_request" else {
            "schema": "eira2_transport_request_v1",
            "request_id": evidence["request_id"],
            "operation": "deploy",
            "autonomous_repair_evidence": evidence,
        }
        out = fn(payload)
        if isinstance(out, dict) and (out.get("authorized") is True or out.get("approved") is True or out.get("ok") is True):
            return {"authorized": True, "method": name, "watcher": out}
    raise RuntimeError("watcher_candidate_authorization_failed")


def extract_candidate(answer: Any) -> bytes:
    if isinstance(answer, bytes): return answer
    if isinstance(answer, str): return answer.encode("utf-8")
    if isinstance(answer, dict):
        for key in ("candidate", "content", "source", "code", "replacement"):
            value = answer.get(key)
            if isinstance(value, str): return value.encode("utf-8")
    raise RuntimeError("verified_engineering_returned_no_candidate")


def run_tests(candidate: Path, spec: dict[str, Any], sandbox: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    if candidate.suffix == ".py":
        try:
            py_compile.compile(str(candidate), doraise=True)
            results.append({"name": "python_compile", "ok": True})
        except Exception as exc:
            results.append({"name": "python_compile", "ok": False, "error": f"{type(exc).__name__}:{exc}"})
    for i, test in enumerate(spec.get("tests") or []):
        if not isinstance(test, dict): continue
        argv = test.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise RuntimeError("invalid_test_argv")
        timeout = min(max(int(test.get("timeout_seconds") or 120), 1), 900)
        env = dict(os.environ)
        env["EIRA2_CANDIDATE_PATH"] = str(candidate)
        p = subprocess.run(argv, cwd=str(sandbox), text=True, capture_output=True, timeout=timeout, check=False, env=env)
        results.append({"name": str(test.get("name") or f"test_{i}"), "ok": p.returncode == 0, "returncode": p.returncode, "stdout_tail": (p.stdout or "")[-4000:], "stderr_tail": (p.stderr or "")[-4000:]})
    return {"results": results, "all_passed": bool(results) and all(r.get("ok") is True for r in results)}


def build_candidate(root: Path, request: dict[str, Any], sandbox: Path) -> tuple[Path, dict[str, Any]]:
    target_rel = safe_rel(str((request.get("target") or {}).get("path") or ""))
    if target_rel == "main.py" or any(target_rel.startswith(p) for p in DENY_PREFIXES if p.endswith("/")):
        raise RuntimeError("autonomous_core_boundary_denied:" + target_rel)
    live = (root / target_rel).resolve(); live.relative_to(root)
    current = live.read_bytes() if live.is_file() else b""
    ask, provider_path = load_verified_engineering(root)
    task = str(request.get("task") or "").strip()
    if not task: raise RuntimeError("autonomous_task_missing")
    prompt = {
        "task": task,
        "target_path": target_rel,
        "current_source": current.decode("utf-8", errors="replace"),
        "requirements": request.get("requirements") or {},
        "mode": "isolated_sandbox_candidate_only",
        "must_return_complete_replacement": True,
        "must_not_modify_live": True,
    }
    try:
        answer = ask(prompt)
    except TypeError:
        answer = ask(json.dumps(prompt, sort_keys=True))
    payload = extract_candidate(answer)
    candidate = sandbox / Path(target_rel).name
    candidate.write_bytes(payload)
    return candidate, {
        "provider": str(provider_path.relative_to(root)),
        "before_sha256": sha256_bytes(current) if current else None,
        "candidate_sha256": sha256_bytes(payload),
        "candidate_bytes": len(payload),
    }


def execute(root: Path, repo: Path, request: dict[str, Any], base, initial_auth: dict[str, Any]) -> dict[str, Any]:
    rid = str(request.get("request_id") or "")
    if request.get("autonomous_schema") not in {None, SCHEMA}: raise RuntimeError("autonomous_schema_invalid")
    target_rel = safe_rel(str((request.get("target") or {}).get("path") or ""))
    with tempfile.TemporaryDirectory(prefix="eira2_autonomous_repair_") as td:
        sandbox = Path(td)
        candidate, build = build_candidate(root, request, sandbox)
        tests = run_tests(candidate, request, sandbox)
        if tests.get("all_passed") is not True:
            raise RuntimeError("sandbox_tests_failed:" + json.dumps(tests, sort_keys=True)[-3000:])
        evidence = {
            "schema": "eira2_autonomous_repair_evidence_v1",
            "request_id": rid,
            "target_path": target_rel,
            "initial_watcher_authorization": initial_auth,
            "sandbox_isolated": True,
            "build": build,
            "tests": tests,
            "evaluated": True,
            "generated_unix": time.time(),
        }
        approval = watcher_authorize_candidate(root, evidence)
        evidence["post_test_watcher_approval"] = approval
        payload = candidate.read_bytes()
        live = root / target_rel
        before = sha256_file(live)
        lane = base._run_lane(root, repo, rid, target_rel, payload, before)
        after = sha256_file(live)
        expected = sha256_bytes(payload)
        if after != expected: raise RuntimeError("autonomous_post_deploy_sha256_mismatch")
        evidence.update({
            "builder_invoked": True,
            "before_sha256": before,
            "after_sha256": after,
            "completion_sha256": after,
            "candidate_sha256": expected,
            "lane_receipt": lane.get("lane_receipt") or {},
            "executed": True,
            "verified": True,
        })
        return evidence
