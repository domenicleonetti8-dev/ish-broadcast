#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/plugin.py"

NEW = r"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = "eira2_engineering_worker_opencode_aider_v5_canonical"
EXTENSION_ID = "eira.engineering.worker"
DEFAULT_OPENCODE_MODEL = "ollama/qwen2.5-coder:3b"
DEFAULT_AIDER_MODEL = "ollama_chat/qwen2.5-coder:3b"
DEFAULT_STAGE_TIMEOUTS = {"inspect": 300, "plan": 300, "aider": 600, "review": 300, "test": 300}
MAX_STDIO = 2_000_000
MAX_CHANGED_FILES = 64
MAX_CANDIDATE_BYTES = 8_000_000
ALLOWED_MODELS = {DEFAULT_OPENCODE_MODEL, DEFAULT_AIDER_MODEL}
PINNED_BINARIES = {
    "opencode": Path.home() / ".opencode/bin/opencode",
    "aider": Path.home() / ".local/bin/aider",
    "python3": Path("/usr/bin/python3"),
    "git": Path("/usr/bin/git"),
}
SENSITIVE_ENV_TOKENS = ("TOKEN", "SECRET", "PASSWORD", "PASS", "KEY", "CREDENTIAL", "COOKIE", "AUTH")
PROTECTED_PREFIXES = (
    "extensions/repair_watcher_ai/",
    "tools/eira2_transaction_executor.py",
    "tools/eira2_superprobe",
    "eira2/",
)

def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _safe_rel(value: str) -> str:
    p = Path(value)
    if p.is_absolute() or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + value)
    return p.as_posix()

def _clean_env() -> dict[str, str]:
    keep = {"HOME", "PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "LOGNAME"}
    env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in keep and not any(tok in k.upper() for tok in SENSITIVE_ENV_TOKENS):
            env[k] = v
    env.update({
        "EIRA_ENGINEERING_WORKSPACE_ONLY": "1",
        "EIRA_ENGINEERING_LIVE_WRITE": "0",
        "AIDER_YES_ALWAYS": "true",
        "AIDER_AUTO_COMMITS": "false",
        "PYTHONUNBUFFERED": "1",
    })
    return env

def _binary(name: str) -> str:
    p = PINNED_BINARIES[name]
    if not p.is_file() or not os.access(p, os.X_OK):
        raise RuntimeError(name + "_binary_unavailable:" + str(p))
    return str(p)

def _decode_timeout_stream(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)

def _run(argv: list[str], cwd: Path, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env or _clean_env(),
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=max(1, min(int(timeout), 3600)))
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            stdout, stderr = proc.communicate()
        stdout = _decode_timeout_stream(stdout or exc.stdout)
        stderr = _decode_timeout_stream(stderr or exc.stderr)
    return {
        "argv": argv,
        "returncode": 124 if timed_out else proc.returncode,
        "stdout": (stdout or "")[-MAX_STDIO:],
        "stderr": (stderr or "")[-MAX_STDIO:],
        "elapsed_seconds": round(time.time() - started, 3),
        "timed_out": timed_out,
    }

def _stage(stage_dir: Path, name: str, status: str, **extra: Any) -> None:
    stage_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "stage": name, "status": status, "unix": time.time(), **extra}
    tmp = stage_dir / (name + ".json.tmp")
    final = stage_dir / (name + ".json")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, final)

def _manifest_rows(root: Path) -> list[dict[str, Any]]:
    manifest = root / "eira2-package-manifest.json"
    if not manifest.is_file():
        raise RuntimeError("canonical_package_manifest_unavailable")
    obj = json.loads(manifest.read_text(encoding="utf-8"))
    rows = obj.get("files")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("canonical_package_manifest_empty")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("path"):
            raise RuntimeError("canonical_package_manifest_invalid_row")
        rel = _safe_rel(str(row["path"]))
        out.append({"path": rel, "sha256": row.get("sha256"), "size": row.get("size")})
    return out

def _capture_source_state(root: Path, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        rel = row["path"]
        p = root / rel
        if not p.is_file() or p.is_symlink():
            raise RuntimeError("canonical_source_missing_or_symlink:" + rel)
        st1 = p.stat()
        digest = _sha_file(p)
        st2 = p.stat()
        if (st1.st_size, st1.st_mtime_ns, st1.st_ino) != (st2.st_size, st2.st_mtime_ns, st2.st_ino):
            raise RuntimeError("canonical_source_changed_while_reading:" + rel)
        if row.get("sha256") and row["sha256"] != digest:
            raise RuntimeError("canonical_manifest_sha_mismatch:" + rel)
        if row.get("size") is not None and int(row["size"]) != st2.st_size:
            raise RuntimeError("canonical_manifest_size_mismatch:" + rel)
        state[rel] = {"sha256": digest, "size": st2.st_size, "mode": st2.st_mode & 0o777}
    return state

def _copy_frozen_snapshot(root: Path, rows: list[dict[str, Any]], state: dict[str, dict[str, Any]], dst: Path) -> None:
    for row in rows:
        rel = row["path"]
        src = root / rel
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        if out.is_symlink() or not out.is_file():
            raise RuntimeError("snapshot_type_violation:" + rel)
        if _sha_file(out) != state[rel]["sha256"]:
            raise RuntimeError("snapshot_hash_mismatch:" + rel)
        if out.stat().st_size != state[rel]["size"]:
            raise RuntimeError("snapshot_size_mismatch:" + rel)
    final_state = _capture_source_state(root, rows)
    if final_state != state:
        raise RuntimeError("canonical_source_drift_during_snapshot")

def _snapshot(root: Path, session: Path, stage_dir: Path) -> tuple[Path, dict[str, dict[str, Any]], str]:
    rows = _manifest_rows(root)
    before = _capture_source_state(root, rows)
    frozen = session / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    _copy_frozen_snapshot(root, rows, before, frozen)
    fp = _sha_bytes(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())
    _stage(stage_dir, "snapshot", "PASS", file_count=len(before), fingerprint=fp)
    return frozen, before, fp

def _clone_snapshot(frozen: Path, dst: Path) -> None:
    shutil.copytree(frozen, dst, symlinks=False)
    git = _binary("git")
    cmds = [
        [git, "init", "-q"],
        [git, "config", "user.name", "EIRA Engineering Sandbox"],
        [git, "config", "user.email", "eira-engineering@localhost"],
        [git, "add", "-A"],
        [git, "commit", "-qm", "frozen baseline"],
    ]
    for argv in cmds:
        r = _run(argv, dst, 120)
        if r["returncode"] != 0:
            raise RuntimeError("sandbox_git_setup_failed:" + r["stderr"][-1200:])

def _workspace(root: Path) -> dict[str, Path | str | dict[str, dict[str, Any]]]:
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError("eira_root_unavailable")
    session = Path(tempfile.mkdtemp(prefix="eira_engineering_v5_", dir="/tmp"))
    stage_dir = session / "stages"
    frozen, source_state, source_fp = _snapshot(root, session, stage_dir)
    opencode_box = session / "opencode"
    aider_box = session / "aider"
    review_box = session / "review"
    _clone_snapshot(frozen, opencode_box)
    _clone_snapshot(frozen, aider_box)
    _clone_snapshot(frozen, review_box)
    return {
        "session": session, "stages": stage_dir, "frozen": frozen,
        "opencode": opencode_box, "aider": aider_box, "review": review_box,
        "source_state": source_state, "source_fingerprint": source_fp,
    }

def _inventory(base: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(base.rglob("*")):
        if ".git" in p.parts or not p.exists():
            continue
        rel = p.relative_to(base).as_posix()
        if p.is_symlink():
            out[rel] = {"type": "symlink", "target": os.readlink(p)}
        elif p.is_file():
            st = p.stat()
            out[rel] = {"type": "file", "sha256": _sha_file(p), "size": st.st_size, "mode": st.st_mode & 0o777}
    return out

def _changed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

def _assert_candidate_paths(changed: list[str]) -> None:
    if len(changed) > MAX_CHANGED_FILES:
        raise RuntimeError("candidate_changed_file_limit_exceeded")
    for rel in changed:
        _safe_rel(rel)
        if any(rel.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            raise RuntimeError("protected_path_requires_separate_owner_authorization:" + rel)

def _parse_review(stdout: str) -> bool:
    lines = [x.strip() for x in stdout.splitlines() if x.strip()]
    return bool(lines) and lines[-1] == "REVIEW=PASS"

def _validate_request(request: dict[str, Any]) -> None:
    if not isinstance(request, dict):
        raise TypeError("engineering_worker_request_must_be_dict")
    if not str(request.get("objective") or "").strip():
        raise RuntimeError("objective_required")
    evidence = request.get("failure_evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(x, dict) for x in evidence):
        raise RuntimeError("structured_failure_evidence_required")
    for row in evidence:
        if not row.get("source") or not row.get("observation") or not row.get("reproduction"):
            raise RuntimeError("failure_evidence_requires_source_observation_reproduction")
    for key in ("opencode_model", "aider_model"):
        if request.get(key) and request[key] not in ALLOWED_MODELS:
            raise RuntimeError("model_not_allowlisted:" + str(request[key]))

def _run_tests(box: Path, changed: list[str], request: dict[str, Any], stage_dir: Path) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    git = _binary("git")
    py = _binary("python3")
    r = _run([git, "diff", "--check"], box, 120)
    tests.append({"name": "git_diff_check", "ok": r["returncode"] == 0, "returncode": r["returncode"]})
    for rel in changed:
        p = box / rel
        if rel.endswith(".py") and p.is_file():
            r = _run([py, "-m", "py_compile", rel], box, 120)
            tests.append({"name": "py_compile:" + rel, "ok": r["returncode"] == 0, "returncode": r["returncode"]})
    verify = request.get("verification_argv")
    if not isinstance(verify, list) or not verify or not all(isinstance(x, str) and x for x in verify):
        raise RuntimeError("verification_argv_required")
    if Path(verify[0]).is_absolute() and Path(verify[0]) not in {Path(_binary("python3")), Path(_binary("git"))}:
        raise RuntimeError("verification_executable_not_allowlisted")
    r = _run(verify, box, int(request.get("test_timeout_seconds") or DEFAULT_STAGE_TIMEOUTS["test"]))
    tests.append({"name": "defect_verification", "ok": r["returncode"] == 0, "returncode": r["returncode"], "timed_out": r["timed_out"]})
    _stage(stage_dir, "tests", "PASS" if all(t["ok"] for t in tests) else "FAIL", tests=tests)
    return tests

def _candidate_bundle(box: Path, baseline: dict[str, Any], changed: list[str], source_fp: str) -> dict[str, Any]:
    final_inventory = _inventory(box)
    final_changed = _changed(baseline, final_inventory)
    if final_changed != changed:
        raise RuntimeError("candidate_changed_after_qualification")
    total = 0
    files: dict[str, Any] = {}
    for rel in final_changed:
        p = box / rel
        meta = final_inventory.get(rel)
        if meta and meta.get("type") == "symlink":
            raise RuntimeError("symlink_candidate_rejected:" + rel)
        if p.is_file():
            data = p.read_bytes()
            total += len(data)
            if total > MAX_CANDIDATE_BYTES:
                raise RuntimeError("candidate_byte_limit_exceeded")
            files[rel] = {
                "operation": "write",
                "before": baseline.get(rel),
                "after": meta,
                "content_hex": data.hex(),
            }
        else:
            files[rel] = {"operation": "delete", "before": baseline.get(rel), "after": None}
    envelope = {"schema": "eira2_engineering_candidate_bundle_v1", "source_fingerprint": source_fp, "files": files}
    envelope["bundle_sha256"] = _sha_bytes(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode())
    return envelope

def inspect(request: dict[str, Any]) -> dict[str, Any]:
    _validate_request(request)
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    ws = _workspace(root)
    stage_dir = ws["stages"]
    try:
        prompt = (
            "Inspect this frozen EIRA snapshot. Do not edit. Use only evidence visible in the snapshot and the supplied objective. "
            "Identify reproducible defects, canonical owner, exact paths, and a bounded proposed file scope. "
            "Do not claim LIVE runtime truth from model inference.\n\nOBJECTIVE:\n" + str(request["objective"])
        )
        _stage(stage_dir, "opencode_inspect", "START")
        r = _run([_binary("opencode"), "run", "--model", request.get("opencode_model") or DEFAULT_OPENCODE_MODEL, prompt],
                 ws["opencode"], int(request.get("inspect_timeout_seconds") or DEFAULT_STAGE_TIMEOUTS["inspect"]))
        mutations = _changed(_inventory(ws["frozen"]), _inventory(ws["opencode"]))
        ok = r["returncode"] == 0 and not mutations
        _stage(stage_dir, "opencode_inspect", "PASS" if ok else "FAIL", returncode=r["returncode"], timed_out=r["timed_out"], mutations=mutations)
        return {"schema": SCHEMA, "mode": "inspect", "ok": ok, "opencode": r, "sandbox_mutations": mutations,
                "source_fingerprint": ws["source_fingerprint"], "workspace": str(ws["session"]), "live_mutated": False}
    except Exception as exc:
        _stage(stage_dir, "failure", "FAIL", error=type(exc).__name__ + ":" + str(exc))
        raise

def build(request: dict[str, Any]) -> dict[str, Any]:
    _validate_request(request)
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    ws = _workspace(root)
    stage_dir = ws["stages"]
    try:
        baseline = _inventory(ws["frozen"])
        objective = str(request["objective"]).strip()

        _stage(stage_dir, "opencode_plan", "START")
        plan_prompt = (
            "You are the planning reviewer. Do not edit. Produce a concise repair plan grounded only in supplied structured failure evidence. "
            "Return exact relative file paths under FILE_SCOPE, one per line, then PLAN text. Never use absolute LIVE paths.\n\nOBJECTIVE:\n"
            + objective + "\n\nFAILURE_EVIDENCE:\n" + json.dumps(request["failure_evidence"], sort_keys=True)
        )
        plan = _run([_binary("opencode"), "run", "--model", request.get("opencode_model") or DEFAULT_OPENCODE_MODEL, plan_prompt],
                    ws["opencode"], int(request.get("plan_timeout_seconds") or DEFAULT_STAGE_TIMEOUTS["plan"]))
        if plan["returncode"] != 0 or _changed(baseline, _inventory(ws["opencode"])):
            raise RuntimeError("opencode_plan_failed_or_mutated")
        _stage(stage_dir, "opencode_plan", "PASS", returncode=plan["returncode"], timed_out=plan["timed_out"])

        allowed_paths = request.get("allowed_paths")
        if not isinstance(allowed_paths, list) or not allowed_paths:
            raise RuntimeError("allowed_paths_required")
        allowed_paths = sorted({_safe_rel(str(x)) for x in allowed_paths})
        for rel in allowed_paths:
            if any(rel.startswith(prefix) for prefix in PROTECTED_PREFIXES):
                raise RuntimeError("protected_path_not_allowed_in_worker:" + rel)

        aider_prompt = (
            "Implement only the evidence-backed repair. You may modify ONLY these relative paths:\n"
            + "\n".join(allowed_paths)
            + "\nDo not access absolute paths. Do not create alternate/versioned/backup subsystems. "
              "Keep all work in this workspace. Preserve unrelated behavior.\n\nOBJECTIVE:\n"
            + objective + "\n\nPLAN:\n" + plan["stdout"][-16000:]
        )
        _stage(stage_dir, "aider", "START")
        aider_argv = [_binary("aider"), "--yes-always", "--no-auto-commits", "--no-dirty-commits",
                      "--model", request.get("aider_model") or DEFAULT_AIDER_MODEL, "--message", aider_prompt] + allowed_paths
        ad = _run(aider_argv, ws["aider"], int(request.get("aider_timeout_seconds") or DEFAULT_STAGE_TIMEOUTS["aider"]))
        if ad["returncode"] != 0:
            _stage(stage_dir, "aider", "FAIL", returncode=ad["returncode"], timed_out=ad["timed_out"])
            raise RuntimeError("aider_build_failed")
        changed = _changed(baseline, _inventory(ws["aider"]))
        if not changed:
            raise RuntimeError("aider_no_material_change")
        if any(rel not in allowed_paths for rel in changed):
            raise RuntimeError("aider_changed_path_outside_allowlist")
        _assert_candidate_paths(changed)
        _stage(stage_dir, "aider", "PASS", changed=changed)

        pre_test_inventory = _inventory(ws["aider"])
        tests = _run_tests(ws["aider"], changed, request, stage_dir)
        if not tests or any(t["ok"] is not True for t in tests):
            raise RuntimeError("qualification_failed")
        post_test_inventory = _inventory(ws["aider"])
        if pre_test_inventory != post_test_inventory:
            raise RuntimeError("tests_mutated_candidate")

        shutil.rmtree(ws["review"])
        shutil.copytree(ws["aider"], ws["review"], symlinks=False)
        review_before = _inventory(ws["review"])
        diff = _run([_binary("git"), "diff", "--no-ext-diff", "--binary", "HEAD", "--"] + changed, ws["aider"], 120)
        review_prompt = (
            "Adversarially review this exact candidate diff against the objective and structured evidence. Do not edit. "
            "Reject if evidence is insufficient, scope exceeds allowed paths, protected ownership is weakened, tests do not prove the defect, "
            "or unrelated behavior changes. Your final nonblank line must be exactly REVIEW=PASS or REVIEW=FAIL.\n\nOBJECTIVE:\n"
            + objective + "\n\nEVIDENCE:\n" + json.dumps(request["failure_evidence"], sort_keys=True)
            + "\n\nDIFF:\n" + diff["stdout"][-30000:]
        )
        _stage(stage_dir, "opencode_review", "START")
        rev = _run([_binary("opencode"), "run", "--model", request.get("opencode_model") or DEFAULT_OPENCODE_MODEL, review_prompt],
                   ws["review"], int(request.get("review_timeout_seconds") or DEFAULT_STAGE_TIMEOUTS["review"]))
        if _inventory(ws["review"]) != review_before:
            raise RuntimeError("opencode_review_mutated_candidate")
        if rev["returncode"] != 0 or not _parse_review(rev["stdout"]):
            _stage(stage_dir, "opencode_review", "FAIL", returncode=rev["returncode"], timed_out=rev["timed_out"])
            raise RuntimeError("adversarial_review_failed")
        _stage(stage_dir, "opencode_review", "PASS")

        final_tests = _run_tests(ws["aider"], changed, request, stage_dir)
        if any(t["ok"] is not True for t in final_tests):
            raise RuntimeError("final_qualification_failed")
        final_inventory = _inventory(ws["aider"])
        if final_inventory != post_test_inventory:
            raise RuntimeError("candidate_changed_after_review")
        bundle = _candidate_bundle(ws["aider"], baseline, changed, str(ws["source_fingerprint"]))
        _stage(stage_dir, "candidate_seal", "PASS", bundle_sha256=bundle["bundle_sha256"], changed=changed)
        return {
            "schema": SCHEMA, "mode": "build", "ok": True, "workspace": str(ws["session"]),
            "source_fingerprint": ws["source_fingerprint"], "changed_paths": changed,
            "candidate_bundle": bundle, "tests": final_tests, "review_passed": True,
            "live_mutated": False, "requires_watcher_builder_deployment": True,
            "deployment_contract": "Watcher must re-check LIVE before hashes/source fingerprint and use canonical transactional Builder; worker has no LIVE mutation authority.",
        }
    except Exception as exc:
        _stage(stage_dir, "failure", "FAIL", error=type(exc).__name__ + ":" + str(exc))
        return {"schema": SCHEMA, "mode": "build", "ok": False, "error": type(exc).__name__ + ":" + str(exc),
                "workspace": str(ws["session"]), "source_fingerprint": ws["source_fingerprint"], "live_mutated": False}

def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    checks["unsafe_absolute_rejected"] = False
    try:
        _safe_rel("/tmp/x")
    except RuntimeError:
        checks["unsafe_absolute_rejected"] = True
    checks["unsafe_parent_rejected"] = False
    try:
        _safe_rel("../x")
    except RuntimeError:
        checks["unsafe_parent_rejected"] = True
    checks["review_exact_pass"] = _parse_review("x\nREVIEW=PASS\n")
    checks["review_embedded_pass_rejected"] = not _parse_review("foo REVIEW=PASS bar")
    checks["model_allowlist"] = DEFAULT_OPENCODE_MODEL in ALLOWED_MODELS and DEFAULT_AIDER_MODEL in ALLOWED_MODELS
    checks["direct_live_write_false"] = True
    return {"schema": SCHEMA, "ok": all(checks.values()), "checks": checks}

def status(root: str | Path | None = None) -> dict[str, Any]:
    r = Path(root or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    return {
        "schema": SCHEMA, "extension_id": EXTENSION_ID, "root": str(r),
        "opencode": _binary("opencode"), "aider": _binary("aider"),
        "opencode_model": DEFAULT_OPENCODE_MODEL, "aider_model": DEFAULT_AIDER_MODEL,
        "direct_live_write": False, "deployment_authority": "Watcher -> canonical Builder",
        "snapshot_contract": "single frozen manifest-verified snapshot reused by OpenCode/Aider/review",
        "candidate_contract": "immutable multi-file bundle with before/after metadata and source fingerprint",
    }

def ask(request: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(request, str):
        request = json.loads(request)
    if not isinstance(request, dict):
        raise TypeError("engineering_worker_request_must_be_dict")
    mode = str(request.get("mode") or "status")
    if mode == "status":
        return status(request.get("root"))
    if mode == "inspect":
        return inspect(request)
    if mode in {"build", "repair"}:
        return build(request)
    if mode == "self_test":
        return self_test()
    raise RuntimeError("unsupported_engineering_worker_mode:" + mode)

def capabilities() -> dict[str, Any]:
    return {
        "extension_id": EXTENSION_ID,
        "schema": SCHEMA,
        "modes": ["status", "inspect", "build", "repair", "self_test"],
        "live_deployment": "none; Watcher -> canonical Builder only",
    }
"""

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print("EIRA2_ENGINEERING_WORKER_V5_CANONICAL=PASS")
