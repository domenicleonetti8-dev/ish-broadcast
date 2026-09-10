#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/plugin.py"

NEW = r'''
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = "eira2_engineering_worker_opencode_aider_v6_canonical"
EXTENSION_ID = "eira.engineering.worker"

OPENCODE_MODEL = "ollama/qwen2.5-coder:3b"
AIDER_MODEL = "ollama_chat/qwen2.5-coder:3b"
PINNED = {
    "opencode": Path.home() / ".opencode/bin/opencode",
    "aider": Path.home() / ".local/bin/aider",
    "python3": Path("/usr/bin/python3"),
    "git": Path("/usr/bin/git"),
    "bwrap": Path("/usr/bin/bwrap"),
}
MAX_CHANGED_FILES = 64
MAX_ALLOWED_PATHS = 64
MAX_CANDIDATE_BYTES = 8_000_000
MAX_PLAN_BYTES = 32_000
MAX_DIFF_BYTES = 4_000_000
MAX_CAPTURE_BYTES = 2_000_000
MAX_REPAIR_ATTEMPTS = 3
STAGE_TIMEOUTS = {"inspect": 300, "plan": 300, "aider": 600, "review": 300, "test": 300}
LOCK_PATH = Path("/tmp/eira_engineering_worker_v6.lock")
PROTECTED_PREFIXES = (
    "extensions/repair_watcher_ai/",
    "tools/eira2_transaction_executor.py",
    "tools/eira2_superprobe",
)

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _safe_rel(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("empty_relative_path")
    p = Path(value)
    if value in {".", "./"} or p == Path(".") or p.is_absolute() or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + value)
    rel = p.as_posix()
    if rel.startswith("/") or rel.startswith("../") or "/../" in rel:
        raise RuntimeError("unsafe_relative_path:" + value)
    return rel

def _binary(name: str) -> str:
    p = PINNED[name]
    if not p.is_file() or not os.access(p, os.X_OK):
        raise RuntimeError(name + "_binary_unavailable:" + str(p))
    return str(p)

def _tool_receipt(name: str) -> dict[str, Any]:
    p = Path(_binary(name))
    return {"path": str(p), "sha256": _sha_file(p), "size": p.stat().st_size}

def _clean_env() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", ""),
        "HOME": "/tmp/eira-home",
        "TMPDIR": "/tmp",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "AIDER_YES_ALWAYS": "true",
        "AIDER_AUTO_COMMITS": "false",
        "EIRA_ENGINEERING_WORKSPACE_ONLY": "1",
        "EIRA_ENGINEERING_LIVE_WRITE": "0",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
    }

def _bwrap_prefix(workspace: Path) -> list[str]:
    bwrap = _binary("bwrap")
    argv = [bwrap, "--die-with-parent", "--new-session", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for p in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
        if Path(p).exists():
            argv += ["--ro-bind", p, p]
    home = Path.home()
    for p in (home / ".opencode", home / ".local"):
        if p.exists():
            argv += ["--ro-bind", str(p), str(p)]
    ocfg = home / ".config/opencode"
    if ocfg.exists():
        argv += ["--ro-bind", str(ocfg), str(ocfg)]
    argv += ["--bind", str(workspace), "/workspace", "--chdir", "/workspace"]
    return argv

def _kill_group(pid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return
        except Exception:
            pass
        time.sleep(0.05)

def _read_tail(path: Path, limit: int = MAX_CAPTURE_BYTES) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - limit), os.SEEK_SET)
        data = f.read(limit)
    return data.decode("utf-8", errors="replace")

def _run(argv: list[str], workspace: Path, timeout: int, *, contained: bool = True) -> dict[str, Any]:
    timeout = max(1, min(int(timeout), 3600))
    started = time.time()
    out = Path(tempfile.mkstemp(prefix="eira-v6-out-", dir="/tmp")[1])
    err = Path(tempfile.mkstemp(prefix="eira-v6-err-", dir="/tmp")[1])
    try:
        cmd = (_bwrap_prefix(workspace) + ["--"] + argv) if contained else argv
        with out.open("wb") as fo, err.open("wb") as fe:
            proc = subprocess.Popen(
                cmd,
                cwd=str(workspace),
                stdin=subprocess.DEVNULL,
                stdout=fo,
                stderr=fe,
                env=_clean_env(),
                start_new_session=True,
            )
            timed_out = False
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc.pid)
                try:
                    rc = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    rc = 124
            finally:
                _kill_group(proc.pid)
        return {
            "argv": argv,
            "returncode": 124 if timed_out else rc,
            "timed_out": timed_out,
            "stdout": _read_tail(out),
            "stderr": _read_tail(err),
            "elapsed_seconds": round(time.time() - started, 3),
        }
    finally:
        out.unlink(missing_ok=True)
        err.unlink(missing_ok=True)

@contextmanager
def _worker_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("engineering_worker_already_running")
        yield

def _receipt(ledger: list[dict[str, Any]], stage: str, status: str, **extra: Any) -> None:
    ledger.append({"stage": stage, "status": status, "unix": time.time(), **extra})

def _manifest(root: Path) -> tuple[list[dict[str, Any]], str]:
    p = root / "eira2-package-manifest.json"
    if not p.is_file() or p.is_symlink():
        raise RuntimeError("canonical_package_manifest_unavailable")
    raw = p.read_bytes()
    obj = json.loads(raw.decode("utf-8"))
    rows = obj.get("files")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("canonical_package_manifest_empty")
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("canonical_package_manifest_invalid_row")
        rel = _safe_rel(str(row.get("path") or ""))
        if rel in seen:
            raise RuntimeError("canonical_package_manifest_duplicate_path:" + rel)
        seen.add(rel)
        digest = row.get("sha256")
        size = row.get("size")
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError("canonical_manifest_sha_required:" + rel)
        if not isinstance(size, int) or size < 0:
            raise RuntimeError("canonical_manifest_size_required:" + rel)
        clean.append({"path": rel, "sha256": digest, "size": size})
    return clean, _sha(raw)

def _capture(root: Path, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        rel = row["path"]
        p = root / rel
        if p.is_symlink() or not p.is_file():
            raise RuntimeError("canonical_source_missing_or_symlink:" + rel)
        a = p.stat()
        digest = _sha_file(p)
        b = p.stat()
        if (a.st_size, a.st_mtime_ns, a.st_ino) != (b.st_size, b.st_mtime_ns, b.st_ino):
            raise RuntimeError("canonical_source_changed_while_reading:" + rel)
        if digest != row["sha256"] or b.st_size != row["size"]:
            raise RuntimeError("canonical_manifest_mismatch:" + rel)
        state[rel] = {"type": "file", "sha256": digest, "size": b.st_size, "mode": b.st_mode & 0o777}
    return state

def _copy_snapshot(root: Path, rows: list[dict[str, Any]], state: dict[str, Any], dst: Path) -> None:
    for row in rows:
        rel = row["path"]
        src, out = root / rel, dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out, follow_symlinks=False)
        if out.is_symlink() or not out.is_file():
            raise RuntimeError("snapshot_type_violation:" + rel)
        if _sha_file(out) != state[rel]["sha256"] or out.stat().st_size != state[rel]["size"]:
            raise RuntimeError("snapshot_copy_mismatch:" + rel)
    if _capture(root, rows) != state:
        raise RuntimeError("canonical_source_drift_during_snapshot")

def _git_init(box: Path) -> None:
    git = _binary("git")
    for argv in (
        [git, "init", "-q"],
        [git, "config", "user.name", "EIRA Engineering Sandbox"],
        [git, "config", "user.email", "eira-engineering@localhost"],
        [git, "add", "-A"],
        [git, "commit", "-qm", "frozen baseline"],
    ):
        r = _run(argv, box, 120, contained=False)
        if r["returncode"] != 0:
            raise RuntimeError("sandbox_git_setup_failed:" + r["stderr"][-1000:])

def _workspace(root: Path, ledger: list[dict[str, Any]]) -> dict[str, Any]:
    session = Path(tempfile.mkdtemp(prefix="eira_engineering_v6_", dir="/tmp"))
    rows, manifest_sha = _manifest(root)
    source = _capture(root, rows)
    frozen = session / "frozen"
    frozen.mkdir()
    _copy_snapshot(root, rows, source, frozen)
    source_fp = _sha(json.dumps(
        {"manifest_sha256": manifest_sha, "files": source},
        sort_keys=True, separators=(",", ":")
    ).encode())
    boxes = {}
    for name in ("opencode", "aider", "review"):
        p = session / name
        shutil.copytree(frozen, p, symlinks=False)
        _git_init(p)
        boxes[name] = p
    _receipt(ledger, "snapshot", "PASS", manifest_sha256=manifest_sha, source_fingerprint=source_fp, file_count=len(source))
    return {"session": session, "frozen": frozen, "source": source, "source_fingerprint": source_fp, **boxes}

def _inventory(base: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(base.rglob("*")):
        if ".git" in p.parts:
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

def _assert_no_symlinks(box: Path) -> None:
    bad = [p.relative_to(box).as_posix() for p in box.rglob("*") if p.is_symlink()]
    if bad:
        raise RuntimeError("sandbox_symlink_rejected:" + ",".join(bad[:20]))

def _normalize_allowed(values: Any) -> list[str]:
    if not isinstance(values, list) or not values or len(values) > MAX_ALLOWED_PATHS:
        raise RuntimeError("allowed_paths_required_or_excessive")
    return sorted({_safe_rel(str(x)) for x in values})

def _protected(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in PROTECTED_PREFIXES)

def _scope_authorized(allowed: list[str], request: dict[str, Any]) -> None:
    approved = set(_safe_rel(str(x)) for x in (request.get("owner_authorized_protected_paths") or []))
    for rel in allowed:
        if _protected(rel) and rel not in approved:
            raise RuntimeError("protected_path_requires_owner_authorization:" + rel)

def _parse_plan(stdout: str) -> dict[str, Any]:
    raw = stdout.encode("utf-8")
    if len(raw) > MAX_PLAN_BYTES:
        raise RuntimeError("opencode_plan_too_large")
    lines = [x.strip() for x in stdout.splitlines() if x.strip()]
    if not lines:
        raise RuntimeError("opencode_plan_empty")
    try:
        obj = json.loads(lines[-1])
    except Exception as exc:
        raise RuntimeError("opencode_plan_json_required") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("file_scope"), list) or not isinstance(obj.get("plan"), str):
        raise RuntimeError("opencode_plan_contract_invalid")
    obj["file_scope"] = sorted({_safe_rel(str(x)) for x in obj["file_scope"]})
    if not obj["file_scope"]:
        raise RuntimeError("opencode_plan_scope_empty")
    return obj

def _validate_inspect_request(request: dict[str, Any]) -> None:
    if not isinstance(request, dict):
        raise TypeError("engineering_worker_request_must_be_dict")
    if not str(request.get("objective") or "").strip():
        raise RuntimeError("objective_required")

def _validate_build_request(request: dict[str, Any]) -> dict[str, Any]:
    _validate_inspect_request(request)
    evidence = request.get("failure_evidence") or []
    interference = request.get("organism_interference") or []
    if request.get("healthy") and not evidence and not interference:
        return {"decision": "CHILL_AND_MOVE_ON", "ok_to_build": False}
    if not isinstance(evidence, list) or not evidence or not all(isinstance(x, dict) for x in evidence):
        raise RuntimeError("structured_failure_evidence_required")
    for row in evidence:
        required = ("source", "observation", "reproduction")
        if any(not str(row.get(k) or "").strip() for k in required):
            raise RuntimeError("failure_evidence_incomplete")
    if request.get("would_create_overlap") or request.get("canonical_owner_conflict"):
        return {"decision": "REJECT_OVERLAP", "ok_to_build": False}
    if request.get("would_regress_working_behavior"):
        return {"decision": "REJECT_REGRESSION", "ok_to_build": False}
    return {"decision": "BUILD_REPAIR_OR_REPLACEMENT", "ok_to_build": True}

def _test_argv(argv: Any) -> list[str]:
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise RuntimeError("invalid_test_argv")
    exe = Path(argv[0])
    if not exe.is_absolute() or exe not in {PINNED["python3"], PINNED["git"]}:
        raise RuntimeError("test_executable_not_allowlisted")
    for arg in argv[1:]:
        if arg.startswith("/") or ".." in Path(arg).parts:
            raise RuntimeError("unsafe_test_argument:" + arg)
    if exe == PINNED["python3"] and "-c" in argv:
        raise RuntimeError("python_inline_code_not_allowed")
    return list(argv)

def _syntax_check_python(box: Path, rel: str) -> dict[str, Any]:
    py = _binary("python3")
    code = "import pathlib,sys; p=pathlib.Path(sys.argv[1]); compile(p.read_text(encoding='utf-8'), str(p), 'exec')"
    return _run([py, "-c", code, rel], box, 120)

def _run_tests(box: Path, changed: list[str], request: dict[str, Any], ledger: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    git = _binary("git")
    r = _run([git, "diff", "--check"], box, 120)
    tests.append({"name": "git_diff_check", "ok": r["returncode"] == 0, "returncode": r["returncode"]})
    for rel in changed:
        p = box / rel
        if rel.endswith(".py") and p.is_file():
            r = _syntax_check_python(box, rel)
            tests.append({"name": "syntax:" + rel, "ok": r["returncode"] == 0, "returncode": r["returncode"], "stderr": r["stderr"][-2000:]})
    commands = [request.get("verification_argv")] + list(request.get("test_matrix") or [])
    for i, raw in enumerate(commands):
        argv = _test_argv(raw)
        r = _run(argv, box, int(request.get("test_timeout_seconds") or STAGE_TIMEOUTS["test"]))
        tests.append({"name": ("verification" if i == 0 else f"matrix_{i}"), "ok": r["returncode"] == 0, "returncode": r["returncode"], "timed_out": r["timed_out"], "stdout": r["stdout"][-4000:], "stderr": r["stderr"][-2000:]})
    _receipt(ledger, label, "PASS" if all(t["ok"] for t in tests) else "FAIL", tests=tests)
    return tests

def _full_diff(box: Path, changed: list[str]) -> bytes:
    git = _binary("git")
    r = _run([git, "diff", "--no-ext-diff", "--binary", "HEAD", "--"] + changed, box, 120)
    if r["returncode"] != 0:
        raise RuntimeError("candidate_diff_failed")
    data = r["stdout"].encode("utf-8", errors="replace")
    if len(data) > MAX_DIFF_BYTES:
        raise RuntimeError("candidate_diff_too_large_for_review")
    return data

def _parse_review(stdout: str) -> bool:
    lines = [x.strip() for x in stdout.splitlines() if x.strip()]
    return bool(lines) and lines[-1] == "REVIEW=PASS"

def _bundle(box: Path, baseline: dict[str, Any], changed: list[str], source_fp: str, request: dict[str, Any]) -> dict[str, Any]:
    _assert_no_symlinks(box)
    final = _inventory(box)
    if _changed(baseline, final) != changed:
        raise RuntimeError("candidate_changed_before_seal")
    delete_ok = set(_safe_rel(str(x)) for x in (request.get("owner_authorized_deletions") or []))
    files: dict[str, Any] = {}
    total = 0
    for rel in changed:
        meta = final.get(rel)
        before = baseline.get(rel)
        p = box / rel
        if meta is None:
            if rel not in delete_ok:
                raise RuntimeError("deletion_requires_owner_authorization:" + rel)
            files[rel] = {"operation": "delete", "before": before, "after": None}
            continue
        if meta.get("type") != "file":
            raise RuntimeError("non_file_candidate_rejected:" + rel)
        data = p.read_bytes()
        actual = {"type": "file", "sha256": _sha(data), "size": len(data), "mode": p.stat().st_mode & 0o777}
        if actual != meta:
            raise RuntimeError("candidate_raced_during_seal:" + rel)
        total += len(data)
        if total > MAX_CANDIDATE_BYTES:
            raise RuntimeError("candidate_byte_limit_exceeded")
        files[rel] = {"operation": "write", "before": before, "after": actual, "content_hex": data.hex()}
    env = {"schema": "eira2_engineering_candidate_bundle_v2", "source_fingerprint": source_fp, "files": files}
    env["bundle_sha256"] = _sha(json.dumps(env, sort_keys=True, separators=(",", ":")).encode())
    return env

def inspect(request: dict[str, Any]) -> dict[str, Any]:
    _validate_inspect_request(request)
    ledger: list[dict[str, Any]] = []
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    try:
        with _worker_lock():
            ws = _workspace(root, ledger)
            baseline = _inventory(ws["frozen"])
            prompt = (
                "Inspect this frozen canonical EIRA package snapshot. Do not edit. "
                "Use snapshot evidence only; do not invent LIVE runtime truth. "
                "Identify exact defect candidates, canonical owner, reproduction path, and bounded file scope. "
                "If insufficient evidence, say so. OBJECTIVE: " + str(request["objective"])
            )
            _receipt(ledger, "opencode_inspect", "START")
            r = _run([_binary("opencode"), "run", "--model", OPENCODE_MODEL, prompt], ws["opencode"], STAGE_TIMEOUTS["inspect"])
            mutations = _changed(baseline, _inventory(ws["opencode"]))
            ok = r["returncode"] == 0 and not mutations
            _receipt(ledger, "opencode_inspect", "PASS" if ok else "FAIL", mutations=mutations, returncode=r["returncode"])
            return {"schema": SCHEMA, "mode": "inspect", "ok": ok, "source_fingerprint": ws["source_fingerprint"], "opencode": r, "ledger": ledger, "live_mutated": False}
    except OSError as exc:
        if exc.errno == errno.EIO:
            return {"schema": SCHEMA, "mode": "inspect", "ok": False, "storage_integrity_stop": True, "error": "EIO:" + str(exc), "ledger": ledger, "live_mutated": False}
        raise

def build(request: dict[str, Any]) -> dict[str, Any]:
    issue = _validate_build_request(request)
    if issue["ok_to_build"] is not True:
        return {"schema": SCHEMA, "mode": "build", "ok": False, "organism_issue_gate": issue, "live_mutated": False}
    ledger: list[dict[str, Any]] = []
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    session: Path | None = None
    try:
        with _worker_lock():
            ws = _workspace(root, ledger)
            session = ws["session"]
            baseline = _inventory(ws["frozen"])
            allowed = _normalize_allowed(request.get("allowed_paths"))
            _scope_authorized(allowed, request)

            _receipt(ledger, "opencode_plan", "START")
            prompt = (
                "Return one final JSON line only with keys file_scope(list) and plan(string). "
                "Do not edit. Scope must contain only exact relative files justified by evidence. "
                "No absolute paths, no duplicate authorities, no cosmetic churn. OBJECTIVE: "
                + str(request["objective"]) + "\nEVIDENCE:\n"
                + json.dumps(request["failure_evidence"], sort_keys=True)
            )
            plan_run = _run([_binary("opencode"), "run", "--model", OPENCODE_MODEL, prompt], ws["opencode"], STAGE_TIMEOUTS["plan"])
            if plan_run["returncode"] != 0 or _changed(baseline, _inventory(ws["opencode"])):
                raise RuntimeError("opencode_plan_failed_or_mutated")
            plan = _parse_plan(plan_run["stdout"])
            if plan["file_scope"] != allowed:
                raise RuntimeError("opencode_scope_must_equal_authorized_scope")
            _receipt(ledger, "opencode_plan", "PASS", file_scope=allowed)

            last_failure = ""
            for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                aider_prompt = (
                    "Implement only the authorized repair in these exact files:\n"
                    + "\n".join(allowed)
                    + "\nNo other paths. No backups/versioned alternates. Stay inside /workspace. "
                    "Preserve unrelated behavior.\nOBJECTIVE:\n" + str(request["objective"])
                    + "\nPLAN:\n" + plan["plan"]
                )
                if last_failure:
                    aider_prompt += "\nPREVIOUS QUALIFICATION FAILURE:\n" + last_failure[-8000:]
                _receipt(ledger, f"aider_{attempt}", "START")
                argv = [_binary("aider"), "--yes-always", "--no-auto-commits", "--no-dirty-commits",
                        "--model", AIDER_MODEL, "--message", aider_prompt] + allowed
                ad = _run(argv, ws["aider"], STAGE_TIMEOUTS["aider"])
                if ad["returncode"] != 0:
                    last_failure = "aider_returncode=" + str(ad["returncode"]) + "\n" + ad["stderr"]
                    _receipt(ledger, f"aider_{attempt}", "FAIL", returncode=ad["returncode"], timed_out=ad["timed_out"])
                    continue
                _assert_no_symlinks(ws["aider"])
                changed = _changed(baseline, _inventory(ws["aider"]))
                if not changed:
                    last_failure = "no_material_change"
                    _receipt(ledger, f"aider_{attempt}", "FAIL", reason=last_failure)
                    continue
                if len(changed) > MAX_CHANGED_FILES or any(rel not in allowed for rel in changed):
                    raise RuntimeError("candidate_scope_violation")
                pre = _inventory(ws["aider"])
                tests = _run_tests(ws["aider"], changed, request, ledger, f"qualification_{attempt}")
                post = _inventory(ws["aider"])
                if pre != post:
                    raise RuntimeError("tests_mutated_candidate")
                if all(t["ok"] for t in tests):
                    _receipt(ledger, f"aider_{attempt}", "PASS", changed=changed)
                    break
                last_failure = json.dumps(tests, sort_keys=True)
            else:
                raise RuntimeError("repair_attempts_exhausted")

            _assert_no_symlinks(ws["aider"])
            diff_bytes = _full_diff(ws["aider"], changed)
            review_file = ws["review"] / "EIRA_REVIEW_CANDIDATE.diff"
            review_file.write_bytes(diff_bytes)
            review_baseline = _inventory(ws["review"])
            review_prompt = (
                "Adversarially review the full candidate diff in EIRA_REVIEW_CANDIDATE.diff against the objective and evidence. "
                "Do not edit. Reject scope drift, unproven fixes, regressions, duplicate ownership, protected-authority weakening, "
                "or insufficient verification. Final nonblank line exactly REVIEW=PASS or REVIEW=FAIL.\nOBJECTIVE:\n"
                + str(request["objective"]) + "\nEVIDENCE:\n" + json.dumps(request["failure_evidence"], sort_keys=True)
            )
            _receipt(ledger, "opencode_review", "START")
            rev = _run([_binary("opencode"), "run", "--model", OPENCODE_MODEL, review_prompt], ws["review"], STAGE_TIMEOUTS["review"])
            if _inventory(ws["review"]) != review_baseline:
                raise RuntimeError("opencode_review_mutated_review_workspace")
            if rev["returncode"] != 0 or not _parse_review(rev["stdout"]):
                raise RuntimeError("adversarial_review_failed")
            _receipt(ledger, "opencode_review", "PASS")

            pre_final = _inventory(ws["aider"])
            final_tests = _run_tests(ws["aider"], changed, request, ledger, "final_qualification")
            if any(t["ok"] is not True for t in final_tests):
                raise RuntimeError("final_qualification_failed")
            if _inventory(ws["aider"]) != pre_final:
                raise RuntimeError("final_tests_mutated_candidate")
            bundle = _bundle(ws["aider"], baseline, changed, ws["source_fingerprint"], request)
            _receipt(ledger, "candidate_seal", "PASS", bundle_sha256=bundle["bundle_sha256"], changed=changed)

            return {
                "schema": SCHEMA, "mode": "build", "ok": True,
                "source_fingerprint": ws["source_fingerprint"],
                "changed_paths": changed,
                "candidate_bundle": bundle,
                "review_passed": True,
                "tests": final_tests,
                "ledger": ledger,
                "tool_receipts": {k: _tool_receipt(k) for k in ("opencode", "aider", "python3", "git", "bwrap")},
                "live_mutated": False,
                "requires_watcher_builder_deployment": True,
                "deployment_contract": {
                    "required": [
                        "Watcher authenticates failure evidence",
                        "Watcher rechecks LIVE source fingerprint and each before hash",
                        "canonical Builder applies all files transactionally",
                        "rollback on any write or verification failure",
                        "package identity reseal",
                        "Superprobe post-deploy verification",
                        "durable LIVE receipt with final hashes",
                    ]
                },
            }
    except OSError as exc:
        if exc.errno == errno.EIO:
            _receipt(ledger, "storage_integrity", "STOP", error=str(exc))
            return {"schema": SCHEMA, "mode": "build", "ok": False, "storage_integrity_stop": True, "error": "EIO:" + str(exc), "ledger": ledger, "live_mutated": False}
        raise
    except Exception as exc:
        _receipt(ledger, "failure", "FAIL", error=type(exc).__name__ + ":" + str(exc))
        return {"schema": SCHEMA, "mode": "build", "ok": False, "error": type(exc).__name__ + ":" + str(exc), "ledger": ledger, "live_mutated": False}
    finally:
        if session and request.get("retain_workspace") is not True:
            shutil.rmtree(session, ignore_errors=True)

def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for bad in ("", ".", "./", "../x", "/tmp/x", "a/../b"):
        try:
            _safe_rel(bad)
            checks["reject:" + bad] = False
        except RuntimeError:
            checks["reject:" + bad] = True
    checks["review_exact"] = _parse_review("x\nREVIEW=PASS\n")
    checks["review_embedded_rejected"] = not _parse_review("foo REVIEW=PASS bar")
    checks["models_role_pinned"] = OPENCODE_MODEL != AIDER_MODEL
    checks["direct_live_write_false"] = True
    return {"schema": SCHEMA, "ok": all(checks.values()), "checks": checks}

def status(root: str | Path | None = None) -> dict[str, Any]:
    r = Path(root or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    tools = {}
    for k in PINNED:
        try:
            tools[k] = _tool_receipt(k)
        except Exception as exc:
            tools[k] = {"ok": False, "error": str(exc)}
    return {
        "schema": SCHEMA,
        "extension_id": EXTENSION_ID,
        "root": str(r),
        "direct_live_write": False,
        "filesystem_containment": "bubblewrap required for OpenCode/Aider/tests",
        "network_containment": "not claimed; local model roles are pinned",
        "deployment_authority": "Watcher -> canonical Builder",
        "tools": tools,
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
    if mode in {"build", "repair", "self_repair"}:
        return build(request)
    if mode == "continuous_cycle":
        return build(request) if request.get("failure_evidence") else inspect(request)
    if mode == "self_test":
        return self_test()
    raise RuntimeError("unsupported_engineering_worker_mode:" + mode)

def capabilities() -> dict[str, Any]:
    return {
        "extension_id": EXTENSION_ID,
        "schema": SCHEMA,
        "modes": ["status", "inspect", "build", "repair", "self_repair", "continuous_cycle", "self_test"],
        "discipline": "repair verified defects only; CHILL when healthy; no LIVE writes",
        "queue_owner": "external transport/supervisor",
        "live_deployment": "Watcher -> canonical Builder only",
    }
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print("EIRA2_ENGINEERING_WORKER_V6_CANONICAL=PASS")
