#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/plugin.py"
NEW = r'''from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_engineering_worker_opencode_aider_v2"
EXTENSION_ID = "eira.engineering.worker"
DEFAULT_TIMEOUT = 1800
ESCALATE = {
    "ambiguous_destructive_intent",
    "conflicting_owner_directives",
    "irreversible_external_action",
    "missing_required_secret_or_credential",
    "explicit_owner_approval_required",
    "unrecoverable_verification_failure",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(argv: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        p = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True,
                           timeout=max(1, min(int(timeout), 3600)), check=False, env=env)
    except subprocess.TimeoutExpired as exc:
        return {"argv": argv, "returncode": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "timeout",
                "elapsed_seconds": round(time.time() - started, 3), "timed_out": True}
    return {"argv": argv, "returncode": p.returncode, "stdout": p.stdout or "", "stderr": p.stderr or "",
            "elapsed_seconds": round(time.time() - started, 3), "timed_out": False}


def _safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + str(value))
    return p.as_posix()


def _which(name: str) -> str | None:
    return shutil.which(name)


def _git_root(root: Path) -> Path:
    root = root.resolve()
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], text=True, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("eira_git_root_unavailable")
    resolved = Path(p.stdout.strip()).resolve()
    if resolved != root:
        raise RuntimeError("requested_root_is_not_git_root")
    return resolved


def _tracked_files(root: Path) -> list[str]:
    p = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("git_ls_files_failed:" + p.stderr.decode(errors="replace")[-1200:])
    return [x.decode("utf-8", errors="strict") for x in p.stdout.split(b"\0") if x]


def _hashes(base: Path, rels: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in rels:
        p = base / rel
        out[rel] = _sha256(p.read_bytes()) if p.is_file() else None
    return out


def _snapshot(root: Path) -> tuple[Path, list[str], dict[str, str | None]]:
    root = _git_root(root)
    base = root / "eira_probe" / "engineering_worker_ai" / "sandboxes"
    base.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="worker_", dir=str(base)))
    copied: list[str] = []
    for rel in _tracked_files(root):
        src = root / rel
        if src.is_file():
            dst = sandbox / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(rel)
    for argv in (["git", "init", "-q"], ["git", "config", "user.name", "EIRA Engineering Sandbox"],
                 ["git", "config", "user.email", "eira-engineering-sandbox@localhost"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "sandbox baseline"]):
        r = _run(list(argv), sandbox, 120)
        if r["returncode"] != 0:
            raise RuntimeError("sandbox_git_setup_failed:" + r["stderr"][-1200:])
    return sandbox, copied, _hashes(sandbox, copied)


def _base_env(sandbox: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["EIRA_ENGINEERING_SANDBOX"] = "1"
    env["EIRA_ENGINEERING_LIVE_WRITE"] = "0"
    env["AIDER_YES_ALWAYS"] = "true"
    env["AIDER_AUTO_COMMITS"] = "false"
    return env


def _opencode_bin() -> str:
    binary = _which("opencode") or _which("opencode2")
    if not binary:
        raise RuntimeError("opencode_not_installed")
    return binary


def _aider_bin() -> str:
    binary = _which("aider")
    if not binary:
        raise RuntimeError("aider_not_installed")
    return binary


def _model_args(model: str | None) -> list[str]:
    return ["--model", model] if model else []


def _gate(event: dict[str, Any]) -> dict[str, Any]:
    reason = str(event.get("reason") or "").strip()
    if event.get("scope_violation"):
        return {"decision": "REJECT", "reason": "scope_violation"}
    if event.get("tests_ok") is False:
        return {"decision": "RETRY_OR_REJECT", "reason": "tests_failed"}
    if event.get("review_ok") is False:
        return {"decision": "RETRY_OR_REJECT", "reason": "review_failed"}
    if event.get("destructive") and not reason:
        return {"decision": "ASK_OWNER", "reason": "ambiguous_destructive_intent"}
    if event.get("irreversible") or reason in ESCALATE:
        return {"decision": "ASK_OWNER", "reason": reason or "irreversible_external_action"}
    if event.get("wants_live_deploy") and not event.get("watcher_authorized"):
        return {"decision": "BLOCK", "reason": "watcher_authorization_required"}
    return {"decision": "CONTINUE_AUTONOMOUSLY", "reason": None}


def status(root: str | Path | None = None) -> dict[str, Any]:
    root_path = Path(root or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    models = []
    if _which("ollama"):
        p = subprocess.run(["ollama", "list"], text=True, capture_output=True, check=False, timeout=30)
        if p.returncode == 0:
            models = [line.split()[0] for line in p.stdout.splitlines()[1:] if line.split()]
    return {"schema": SCHEMA, "extension_id": EXTENSION_ID, "root": str(root_path),
            "opencode": _which("opencode") or _which("opencode2"), "aider": _which("aider"), "ollama": _which("ollama"),
            "ollama_models": models, "sandbox_only": True, "live_direct_write_allowed": False,
            "conversation_authority": False, "model_authority": False,
            "deployment_authority": "repair_watcher_ai -> canonical builder lane", "default_mode": "autonomous"}


def inspect(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("objective_required")
    sandbox, copied, baseline = _snapshot(root)
    prompt = ("Read-only EIRA engineering inspection. Work only in this disposable sandbox. Do not edit files. "
              "Identify exact files, interfaces, risks, and a surgical plan. EIRA remains sole conversation/runtime authority.\n\nOBJECTIVE:\n" + objective)
    argv = [_opencode_bin(), "run", "--auto", *_model_args(request.get("opencode_model")), prompt]
    result = _run(argv, sandbox, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _base_env(sandbox))
    after = _hashes(sandbox, copied)
    mutated = sorted(rel for rel in copied if after.get(rel) != baseline.get(rel))
    return {"schema": SCHEMA, "mode": "inspect", "sandbox": str(sandbox), "tracked_files_copied": len(copied),
            "sandbox_mutations_detected": mutated, "live_mutated": False, "opencode": result,
            "ok": result["returncode"] == 0 and not mutated}


def propose_file_replacement(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    target = _safe_rel(str(request.get("target_path") or ""))
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("objective_required")
    if _gate(request).get("decision") == "ASK_OWNER":
        return {"schema": SCHEMA, "ok": False, "needs_owner_input": True, "gate": _gate(request)}
    sandbox, copied, baseline = _snapshot(root)
    target_file = sandbox / target
    if target not in copied or not target_file.is_file():
        raise RuntimeError("target_not_tracked_file:" + target)
    before = target_file.read_bytes()

    analysis_prompt = ("Inspect this disposable EIRA snapshot. Do not edit. Determine the safest complete replacement for exactly one target file. "
                       "Preserve interfaces and authority boundaries. Target: " + target + "\nObjective: " + objective)
    oc = _run([_opencode_bin(), "run", "--auto", *_model_args(request.get("opencode_model")), analysis_prompt],
              sandbox, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _base_env(sandbox))
    if oc["returncode"] != 0:
        raise RuntimeError("opencode_analysis_failed:" + oc["stderr"][-1600:])
    after_analysis = _hashes(sandbox, copied)
    if any(after_analysis.get(rel) != baseline.get(rel) for rel in copied):
        raise RuntimeError("opencode_inspection_scope_violation")

    aider_prompt = ("Modify ONLY " + target + ". Disposable sandbox only. Produce the complete surgical implementation. Preserve compatible interfaces. "
                    "Do not modify any other repository file.\n\nOBJECTIVE:\n" + objective + "\n\nOPENCODE ANALYSIS:\n" + oc["stdout"][-16000:])
    aider_argv = [_aider_bin(), "--yes-always", "--no-auto-commits", "--no-dirty-commits", "--message", aider_prompt,
                  *_model_args(request.get("aider_model")), target]
    ad = _run(aider_argv, sandbox, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _base_env(sandbox))
    if ad["returncode"] != 0:
        raise RuntimeError("aider_edit_failed:" + ad["stderr"][-1600:])

    after_edit = _hashes(sandbox, copied)
    changed_paths = sorted(rel for rel in copied if after_edit.get(rel) != baseline.get(rel))
    if changed_paths != [target]:
        raise RuntimeError("aider_scope_violation:" + json.dumps(changed_paths))
    candidate = target_file.read_bytes()
    if candidate == before:
        raise RuntimeError("aider_produced_no_change")

    tests: list[dict[str, Any]] = []
    if target.endswith(".py"):
        t = _run(["python3", "-m", "py_compile", target], sandbox, 120, _base_env(sandbox))
        tests.append({"name": "py_compile", "ok": t["returncode"] == 0, "stderr": t["stderr"][-2000:]})
    argv = request.get("test_argv")
    if argv is not None:
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise RuntimeError("test_argv_must_be_nonempty_string_list")
        t = _run(argv, sandbox, int(request.get("test_timeout_seconds") or 300), _base_env(sandbox))
        tests.append({"name": "requested_tests", "ok": t["returncode"] == 0, "returncode": t["returncode"],
                      "stdout_tail": t["stdout"][-8000:], "stderr_tail": t["stderr"][-4000:]})
    tests_ok = all(row.get("ok") is True for row in tests) if tests else True
    if not tests_ok:
        raise RuntimeError("candidate_tests_failed:" + json.dumps(tests)[-2400:])

    import difflib
    diff = "".join(difflib.unified_diff(before.decode("utf-8", errors="replace").splitlines(True),
                                        candidate.decode("utf-8", errors="replace").splitlines(True),
                                        fromfile=target + ".before", tofile=target + ".candidate"))
    review_prompt = ("Review this proposed EIRA single-file change. Do not edit files. Reject architectural bypasses, second conversation authorities, "
                     "direct LIVE mutation, or model authority over EIRA. End with exactly REVIEW=PASS or REVIEW=FAIL.\n\nTARGET: " + target + "\n\nDIFF:\n" + diff[-24000:])
    review = _run([_opencode_bin(), "run", "--auto", *_model_args(request.get("opencode_model")), review_prompt],
                  sandbox, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _base_env(sandbox))
    review_ok = review["returncode"] == 0 and "REVIEW=PASS" in review["stdout"] and "REVIEW=FAIL" not in review["stdout"]
    if not review_ok:
        raise RuntimeError("opencode_review_rejected:" + (review["stdout"] + review["stderr"])[-2400:])

    final_hashes = _hashes(sandbox, copied)
    final_changed = sorted(rel for rel in copied if final_hashes.get(rel) != baseline.get(rel))
    if final_changed != [target]:
        raise RuntimeError("post_review_scope_violation:" + json.dumps(final_changed))

    return {"schema": SCHEMA, "mode": "propose_file_replacement", "target_path": target, "sandbox": str(sandbox),
            "tracked_files_copied": len(copied), "before_sha256": _sha256(before), "candidate_sha256": _sha256(candidate),
            "candidate_bytes": len(candidate), "candidate": candidate.decode("utf-8", errors="strict"), "diff": diff,
            "tests": tests, "tests_ok": tests_ok, "review_passed": True, "changed_paths": final_changed,
            "live_mutated": False, "requires_watcher_builder_deployment": True, "needs_owner_input": False, "ok": True}


def self_test() -> dict[str, Any]:
    checks = [
        (status().get("live_direct_write_allowed") is False, "no_live_direct_write"),
        (_gate({})["decision"] == "CONTINUE_AUTONOMOUSLY", "autonomous_default"),
        (_gate({"scope_violation": True})["decision"] == "REJECT", "scope_fail_closed"),
        (_gate({"tests_ok": False})["decision"] == "RETRY_OR_REJECT", "tests_fail_closed"),
        (_gate({"wants_live_deploy": True, "watcher_authorized": False})["decision"] == "BLOCK", "watcher_gate"),
    ]
    return {"schema": SCHEMA, "ok": all(ok for ok, _ in checks), "checks": [{"name": name, "ok": ok} for ok, name in checks]}


def ask(request: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(request, str):
        request = json.loads(request)
    if not isinstance(request, dict):
        raise TypeError("engineering_worker_request_must_be_dict")
    mode = str(request.get("mode") or "inspect")
    if mode == "status": return status(request.get("root"))
    if mode == "inspect": return inspect(request)
    if mode in {"propose", "propose_file_replacement"}: return propose_file_replacement(request)
    if mode in {"gate", "human_input_required"}: return {"schema": SCHEMA, **_gate(request.get("event") or request)}
    if mode == "self_test": return self_test()
    raise RuntimeError("unsupported_engineering_worker_mode:" + mode)


def capabilities() -> dict[str, Any]:
    return {"schema": SCHEMA, "extension_id": EXTENSION_ID,
            "capabilities": ["engineering_worker_status", "engineering_repository_inspect", "engineering_file_replacement_propose",
                             "engineering_autonomy_gate", "engineering_worker_self_test"],
            "sandbox_only": True, "conversation_authority": False, "live_direct_write_allowed": False,
            "model_authority": False, "default_mode": "autonomous",
            "engineering_roles": {"opencode": "inspector_planner_reviewer", "aider": "sandbox_code_surgeon"},
            "deployment_authority": "repair_watcher_ai -> canonical builder lane"}
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    import hashlib, json
    print(json.dumps({"ok": True, "target": TARGET, "bytes": len(NEW.encode()), "sha256": hashlib.sha256(NEW.encode()).hexdigest()}))
