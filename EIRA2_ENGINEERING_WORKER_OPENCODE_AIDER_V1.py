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

SCHEMA = "eira2_engineering_worker_opencode_aider_v1"
EXTENSION_ID = "eira.engineering.worker"
DEFAULT_TIMEOUT = 1800
DENIED_LIVE_PREFIXES = (
    "main.py", "engine/", "brain/", "council/", "routers/", "voice/",
    "identity/", "memory/", "reasoning/", "speech/"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(argv: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.time()
    p = subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=max(1, min(int(timeout), 3600)),
        check=False,
        env=env,
    )
    return {
        "argv": argv,
        "returncode": p.returncode,
        "stdout": p.stdout or "",
        "stderr": p.stderr or "",
        "elapsed_seconds": round(time.time() - started, 3),
    }


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


def _snapshot(root: Path) -> tuple[Path, list[str]]:
    root = _git_root(root)
    base = root / "eira_probe" / "engineering_worker_ai" / "sandboxes"
    base.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="worker_", dir=str(base)))
    copied: list[str] = []
    for rel in _tracked_files(root):
        src = root / rel
        if not src.is_file():
            continue
        dst = sandbox / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    _run(["git", "init", "-q"], sandbox, 60)
    _run(["git", "config", "user.name", "EIRA Engineering Sandbox"], sandbox, 60)
    _run(["git", "config", "user.email", "eira-engineering-sandbox@localhost"], sandbox, 60)
    _run(["git", "add", "-A"], sandbox, 120)
    baseline = _run(["git", "commit", "-qm", "sandbox baseline"], sandbox, 120)
    if baseline["returncode"] != 0:
        raise RuntimeError("sandbox_baseline_commit_failed:" + baseline["stderr"][-1200:])
    return sandbox, copied


def _ollama_models() -> list[str]:
    if not _which("ollama"):
        return []
    p = subprocess.run(["ollama", "list"], text=True, capture_output=True, check=False, timeout=30)
    if p.returncode != 0:
        return []
    out = []
    for line in p.stdout.splitlines()[1:]:
        cols = line.split()
        if cols:
            out.append(cols[0])
    return out


def status(root: str | Path | None = None) -> dict[str, Any]:
    root_path = Path(root or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    return {
        "schema": SCHEMA,
        "extension_id": EXTENSION_ID,
        "root": str(root_path),
        "opencode": _which("opencode") or _which("opencode2"),
        "aider": _which("aider"),
        "ollama": _which("ollama"),
        "ollama_models": _ollama_models(),
        "live_direct_write_allowed": False,
        "sandbox_only": True,
        "deployment_authority": "repair_watcher_ai -> canonical builder lane",
        "conversation_authority": False,
    }


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


def _model_args(tool: str, model: str | None) -> list[str]:
    if not model:
        return []
    if tool == "opencode":
        return ["--model", model]
    return ["--model", model]


def _base_env(sandbox: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(sandbox / ".home")
    env["EIRA_ENGINEERING_SANDBOX"] = "1"
    env["EIRA_ENGINEERING_LIVE_WRITE"] = "0"
    (sandbox / ".home").mkdir(parents=True, exist_ok=True)
    return env


def inspect(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("objective_required")
    sandbox, copied = _snapshot(root)
    prompt = (
        "You are the read-only systems inspector for EIRA. Work only inside this disposable sandbox. "
        "Do not edit files. Analyze the repository evidence for this objective and report exact files, interfaces, risks, and a surgical plan. "
        "EIRA remains the conversation/runtime authority; you are only an engineering worker.\n\nOBJECTIVE:\n" + objective
    )
    argv = [_opencode_bin(), "run", *_model_args("opencode", request.get("opencode_model")), prompt]
    result = _run(argv, sandbox, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _base_env(sandbox))
    return {
        "schema": SCHEMA,
        "mode": "inspect",
        "sandbox": str(sandbox),
        "tracked_files_copied": len(copied),
        "live_mutated": False,
        "opencode": result,
        "ok": result["returncode"] == 0,
    }


def propose_file_replacement(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    target = _safe_rel(str(request.get("target_path") or ""))
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("objective_required")
    sandbox, copied = _snapshot(root)
    target_file = sandbox / target
    if not target_file.is_file():
        raise RuntimeError("target_not_tracked_file:" + target)
    before = target_file.read_bytes()

    analysis_prompt = (
        "Inspect this disposable EIRA repository snapshot. Do not edit anything. Determine the safest complete replacement for exactly one target file. "
        "Preserve interfaces and EIRA authority boundaries. Target: " + target + "\nObjective: " + objective
    )
    oc = _run(
        [_opencode_bin(), "run", *_model_args("opencode", request.get("opencode_model")), analysis_prompt],
        sandbox,
        int(request.get("timeout_seconds") or DEFAULT_TIMEOUT),
        _base_env(sandbox),
    )
    if oc["returncode"] != 0:
        raise RuntimeError("opencode_analysis_failed:" + oc["stderr"][-1600:])

    aider_prompt = (
        "Modify ONLY " + target + ". This is a disposable sandbox, not LIVE. Produce the complete surgical implementation for the objective below. "
        "Preserve compatible interfaces. Do not modify any other file.\n\nOBJECTIVE:\n" + objective +
        "\n\nOPENCODE ANALYSIS:\n" + oc["stdout"][-16000:]
    )
    aider_argv = [_aider_bin(), *_model_args("aider", request.get("aider_model")), "--message", aider_prompt, "--", target]
    ad = _run(aider_argv, sandbox, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _base_env(sandbox))
    if ad["returncode"] != 0:
        raise RuntimeError("aider_edit_failed:" + ad["stderr"][-1600:])

    diff = _run(["git", "diff", "--", target], sandbox, 120)
    changed = _run(["git", "status", "--porcelain"], sandbox, 120)
    changed_paths = []
    for line in changed["stdout"].splitlines():
        if len(line) >= 4:
            changed_paths.append(line[3:].strip())
    if any(p != target for p in changed_paths):
        raise RuntimeError("aider_scope_violation:" + json.dumps(changed_paths))
    if not target_file.is_file():
        raise RuntimeError("aider_deleted_target")
    candidate = target_file.read_bytes()
    if candidate == before:
        raise RuntimeError("aider_produced_no_change")

    review_prompt = (
        "Review this proposed single-file EIRA change. Do not edit files. Reject architectural bypasses, second conversation authorities, direct LIVE mutation, "
        "or Ollama/model authority over EIRA. Check interface preservation and likely regressions.\n\nTARGET: " + target + "\n\nDIFF:\n" + diff["stdout"][-20000:]
    )
    review = _run(
        [_opencode_bin(), "run", *_model_args("opencode", request.get("opencode_model")), review_prompt],
        sandbox,
        int(request.get("timeout_seconds") or DEFAULT_TIMEOUT),
        _base_env(sandbox),
    )
    if review["returncode"] != 0:
        raise RuntimeError("opencode_review_failed:" + review["stderr"][-1600:])

    return {
        "schema": SCHEMA,
        "mode": "propose_file_replacement",
        "target_path": target,
        "sandbox": str(sandbox),
        "tracked_files_copied": len(copied),
        "before_sha256": _sha256(before),
        "candidate_sha256": _sha256(candidate),
        "candidate_bytes": len(candidate),
        "candidate": candidate.decode("utf-8", errors="strict"),
        "diff": diff["stdout"],
        "opencode_analysis": oc["stdout"],
        "aider_output": ad["stdout"],
        "opencode_review": review["stdout"],
        "live_mutated": False,
        "requires_watcher_builder_deployment": True,
        "ok": True,
    }


def ask(request: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(request, str):
        request = json.loads(request)
    if not isinstance(request, dict):
        raise TypeError("engineering_worker_request_must_be_dict")
    mode = str(request.get("mode") or "inspect")
    if mode == "status":
        return status(request.get("root"))
    if mode == "inspect":
        return inspect(request)
    if mode in {"propose", "propose_file_replacement"}:
        return propose_file_replacement(request)
    raise RuntimeError("unsupported_engineering_worker_mode:" + mode)


def capabilities() -> dict[str, Any]:
    return {
        "extension_id": EXTENSION_ID,
        "capabilities": [
            "engineering_worker_status",
            "engineering_repository_inspect",
            "engineering_file_replacement_propose",
        ],
        "sandbox_only": True,
        "conversation_authority": False,
        "live_direct_write_allowed": False,
        "model_backend": "ollama_or_configured_cli_provider",
        "engineering_roles": {"opencode": "inspector_and_reviewer", "aider": "sandbox_code_surgeon"},
    }
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print(json.dumps({"ok": True, "target": TARGET, "bytes": len(NEW.encode()), "sha256": __import__("hashlib").sha256(NEW.encode()).hexdigest()}))
