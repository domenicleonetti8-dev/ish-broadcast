#!/usr/bin/env python3
from __future__ import annotations

import ast, hashlib, importlib.util, json, os, re, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from typing import Any

REQUEST_SCHEMA = "eira2_transport_request_v1"
LANE_NAME = "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
HERE = Path(__file__).resolve().parent


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 2400) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, check=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + value)
    return p.as_posix()


def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    rel = safe_rel(repo_path)
    p = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{rel}"], capture_output=True, timeout=180, check=False)
    if p.returncode:
        raise RuntimeError("source_blob_missing:" + p.stderr[-1200:].decode(errors="replace"))
    return p.stdout


def extract_payload(source: bytes, target_path: str) -> bytes:
    if b"NEW = " not in source or b"TARGET = " not in source:
        return source
    text = source.decode("utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "NEW" for t in targets):
                value = ast.literal_eval(node.value)
                if not isinstance(value, str):
                    raise RuntimeError("embedded_NEW_not_string")
                if target_path.endswith(".py"):
                    compile(value, target_path, "exec")
                return value.encode()
    return source


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_load_failed:" + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _qualification_success(result: Any, returncode: int) -> tuple[bool, str | None]:
    if returncode != 0 or not isinstance(result, dict):
        return False, None
    if result.get("ok") is True:
        return True, "ok_true"
    if result.get("pass") is True:
        return True, "pass_true"
    if str(result.get("status") or "").casefold() in {"pass", "passed", "success", "successful"}:
        return True, "status_pass"
    return False, None


def _execute_read_only_qualification(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    q = spec.get("execute_source") or {}
    commit = str(q.get("commit") or "")
    repo_path = safe_rel(str(q.get("path") or ""))
    expected = str(q.get("sha256") or "").lower()
    timeout = int(q.get("timeout_seconds") or 480)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("qualification_commit_invalid")
    runtime = root / "eira_probe" / "qualification_runtime"
    repo = runtime / "repo"
    runtime.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").is_dir():
        p = run(["git", "clone", "--quiet", "https://github.com/domenicleonetti8-dev/ish-broadcast.git", str(repo)], timeout=300)
        if p.returncode:
            raise RuntimeError("qualification_clone_failed:" + p.stderr[-800:])
    for cmd in (["git", "fetch", "--quiet", "origin", "master"], ["git", "checkout", "--quiet", "master"], ["git", "reset", "--hard", "origin/master"]):
        p = run(cmd, cwd=repo, timeout=300)
        if p.returncode:
            raise RuntimeError("qualification_sync_failed:" + p.stderr[-800:])
    raw = git_blob(repo, commit, repo_path)
    actual = sha256_bytes(raw)
    if expected and actual != expected:
        raise RuntimeError("qualification_source_sha256_mismatch")
    suffix = Path(repo_path).suffix or ".py"
    with tempfile.TemporaryDirectory(prefix="eira2_qual_", dir=str(runtime)) as td:
        path = Path(td) / ("qualification" + suffix)
        path.write_bytes(raw)
        cmd = [sys.executable, str(path)] if suffix == ".py" else [str(path)]
        p = run(cmd, cwd=root, timeout=timeout)
    stdout = (p.stdout or "").strip()
    stderr = (p.stderr or "").strip()
    parsed = None
    if stdout:
        for line in reversed(stdout.splitlines()):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    parsed = obj
                    break
            except Exception:
                pass
    ok, contract = _qualification_success(parsed, p.returncode)
    return {"schema": "eira2_transport_read_only_qualification_v2", "source_commit": commit, "source_path": repo_path, "source_sha256": actual, "returncode": p.returncode, "stdout_tail": stdout[-12000:], "stderr_tail": stderr[-6000:], "result": parsed, "ok": ok, "accepted_success_contract": contract, "qualification_contract_normalized": True, "mutates_live": False}


def inspect_request(root: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    spec = request.get("inspection") or {}
    signatures = [str(x) for x in (spec.get("signatures") or []) if str(x)]
    roots = [str(x) for x in (spec.get("roots") or ["eira2", "extensions"]) if str(x)]
    suffixes = set(spec.get("suffixes") or [".py", ".js", ".html", ".json"])
    rows = []
    scanned = 0
    for relroot in roots:
        base = (root / safe_rel(relroot)).resolve()
        base.relative_to(root)
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in suffixes:
                continue
            scanned += 1
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            matched = [s for s in signatures if s in text]
            if not matched:
                continue
            lines = text.splitlines()
            hits = [i for i, line in enumerate(lines) if any(s in line for s in matched)]
            contexts = []
            for idx in hits[:12]:
                a = max(0, idx - 40)
                b = min(len(lines), idx + 41)
                contexts.append({"start_line": a + 1, "end_line": b, "source": "\n".join(f"{i+1:05d}: {lines[i]}" for i in range(a, b))})
            rows.append({"path": p.resolve().relative_to(root).as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size, "matched_signatures": matched, "contexts": contexts})
    served = []
    for url in spec.get("served_urls") or []:
        try:
            with urllib.request.urlopen(str(url), timeout=20) as r:
                body = r.read(); status = getattr(r, "status", 200)
            text = body.decode("utf-8", errors="replace")
            matched = [s for s in signatures if s in text]
            served.append({"url": str(url), "status": status, "bytes": len(body), "sha256": sha256_bytes(body), "matched_signatures": matched, "source": text[:200000] if matched else None})
        except Exception as exc:
            served.append({"url": str(url), "error": f"{type(exc).__name__}:{exc}"})
    evidence = {"schema": "eira2_transport_inspection_evidence_v3", "request_id": request["request_id"], "watcher_authorization": auth, "mutates_live": False, "candidate_files_scanned": scanned, "matching_files": rows, "served": served, "generated_unix": time.time()}
    if spec.get("execute_source"):
        q = _execute_read_only_qualification(root, spec); evidence["qualification"] = q
        if q.get("ok") is not True:
            raise RuntimeError("read_only_qualification_failed:" + json.dumps(q, sort_keys=True)[-2400:])
    raw = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode(); evidence["evidence_sha256"] = sha256_bytes(raw)
    return evidence


def synthetic_commit(work: Path, request_id: str, gen_rel: str, payload: bytes) -> str:
    blob = subprocess.run(["git", "-C", str(work), "hash-object", "-w", "--stdin"], input=payload, capture_output=True, timeout=120, check=False)
    if blob.returncode:
        raise RuntimeError("materialize_blob_failed:" + blob.stderr[-1200:].decode(errors="replace"))
    blob_sha = blob.stdout.decode().strip(); index = work / ".git" / f"eira2_index_{os.getpid()}"; index.unlink(missing_ok=True); env = dict(os.environ); env["GIT_INDEX_FILE"] = str(index)
    try:
        p = subprocess.run(["git", "read-tree", "HEAD"], cwd=str(work), text=True, capture_output=True, timeout=120, check=False, env=env)
        if p.returncode: raise RuntimeError("materialize_read_tree_failed:" + (p.stdout + p.stderr)[-1200:])
        p = subprocess.run(["git", "update-index", "--add", "--cacheinfo", "100644", blob_sha, gen_rel], cwd=str(work), text=True, capture_output=True, timeout=120, check=False, env=env)
        if p.returncode: raise RuntimeError("materialize_update_index_failed:" + (p.stdout + p.stderr)[-1600:])
        tree = subprocess.run(["git", "write-tree"], cwd=str(work), text=True, capture_output=True, timeout=120, check=False, env=env)
        if tree.returncode: raise RuntimeError("materialize_write_tree_failed:" + (tree.stdout + tree.stderr)[-1600:])
        parent = run(["git", "rev-parse", "HEAD"], cwd=work, timeout=120).stdout.strip()
        c = run(["git", "-c", "user.name=EIRA Transport V3", "-c", "user.email=eira-transport-v3@localhost", "commit-tree", tree.stdout.strip(), "-p", parent, "-m", f"Materialize {request_id}"], cwd=work, timeout=120)
        if c.returncode: raise RuntimeError("materialize_commit_tree_failed:" + (c.stdout + c.stderr)[-1600:])
        return c.stdout.strip()
    finally:
        index.unlink(missing_ok=True)


def _run_lane(root: Path, work: Path, request_id: str, target_path: str, payload: bytes, before_sha: str | None) -> dict[str, Any]:
    gen_rel = f".eira2_generated/{request_id}/{Path(target_path).name}"
    synth = synthetic_commit(work, request_id, gen_rel, payload)
    packet = root / "eira_probe" / "transport_inbox" / "canonical_requests" / f"{request_id}.json"; packet.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(packet, {"schema": "eira2_builder_blueprint_v2", "packet_id": request_id, "apply": True, "source_commit": synth, "payloads": [{"repo_path": gen_rel, "target_path": target_path, "before_sha256": before_sha}]})
    lane = work / LANE_NAME
    p = run([sys.executable, str(lane), "--root", str(root), "--packet", str(packet), "--source-repo-root", str(work)], cwd=root, timeout=4200)
    if p.returncode: raise RuntimeError("deployment_lane_failed:" + (p.stderr or p.stdout)[-1800:])
    receipt_path = root / "eira_probe" / "blueprint_receipts" / f"{request_id}.lane_v4.json"; lane_receipt = {}
    if receipt_path.is_file():
        try: lane_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception: lane_receipt = {}
    return {"synthetic_commit": synth, "lane_receipt": lane_receipt}


def _legacy_deploy(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    dep = request.get("deployment") or {}; source = dep.get("source") or {}; target = dep.get("target") or {}
    commit = str(source.get("commit") or ""); repo_path = str(source.get("path") or ""); target_path = safe_rel(str(target.get("path") or "")); before = str(target.get("expected_before_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit): raise RuntimeError("source_commit_invalid")
    live = root / target_path; before_actual = sha256_file(live) if live.is_file() else None
    if before and before_actual != before: raise RuntimeError("live_before_hash_mismatch:" + str(before_actual))
    source_bytes = git_blob(work, commit, repo_path); expected = str(source.get("sha256") or "").lower()
    if expected and sha256_bytes(source_bytes) != expected: raise RuntimeError("source_sha256_mismatch")
    payload = extract_payload(source_bytes, target_path); lane = _run_lane(root, work, request["request_id"], target_path, payload, before or None)
    after = sha256_file(live) if live.is_file() else None
    if after != sha256_bytes(payload): raise RuntimeError("post_deploy_sha256_mismatch")
    return {"schema": "eira2_transport_deployment_evidence_v3", "request_id": request["request_id"], "watcher_authorization": auth, "builder_invoked": True, "before_sha256": before_actual, "after_sha256": after, "completion_sha256": after, "payload_sha256": sha256_bytes(payload), "legacy_contract": True, "lane_receipt": lane.get("lane_receipt") or {}, "generated_unix": time.time()}


def _manifest_deploy(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    bridge = _load(HERE / "EIRA2_BLUEPRINT_PAYLOAD_BRIDGE_V1.py", "eira2_payload_bridge_v1_runtime")
    dep = request.get("deployment") or {}; source = dep.get("source") or {}; target = dep.get("target") or {}; target_path = safe_rel(str(target.get("path") or "")); before_expected = str(target.get("expected_before_sha256") or "").lower()
    live = root / target_path; before_actual = sha256_file(live) if live.is_file() else None
    if before_expected and before_actual != before_expected: raise RuntimeError("live_before_hash_mismatch:" + str(before_actual))
    payload, bridge_evidence = bridge.materialize_source(work, source); payload = extract_payload(payload, target_path); lane = _run_lane(root, work, request["request_id"], target_path, payload, before_expected or None)
    after = sha256_file(live) if live.is_file() else None; expected = sha256_bytes(payload)
    if after != expected: raise RuntimeError(f"post_deploy_sha256_mismatch:{after}:{expected}")
    return {"schema": "eira2_transport_deployment_evidence_v3", "request_id": request["request_id"], "watcher_authorization": auth, "builder_invoked": True, "before_sha256": before_actual, "after_sha256": after, "completion_sha256": after, "payload_sha256": expected, "payload_bridge": bridge_evidence, "lane_receipt": lane.get("lane_receipt") or {}, "generated_unix": time.time()}


def _post_verify(root: Path, target_path: str, expected_sha: str, job: dict[str, Any]) -> dict[str, Any]:
    live = root / target_path; actual = sha256_file(live) if live.is_file() else None; checks = [{"name": "landed_sha256", "ok": actual == expected_sha, "expected": expected_sha, "actual": actual}]
    argv = job.get("post_verify_argv")
    if argv is not None:
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv): raise RuntimeError("post_verify_argv_must_be_nonempty_string_list")
        timeout = max(1, min(int(job.get("post_verify_timeout_seconds") or 300), 1800)); env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root), "HOME": str(root), "EIRA_AUTONOMOUS_POST_VERIFY": "1"}
        p = subprocess.run(argv, cwd=str(root), text=True, capture_output=True, timeout=timeout, check=False, env=env); checks.append({"name": "post_verify_argv", "ok": p.returncode == 0, "returncode": p.returncode, "stdout_tail": (p.stdout or "")[-12000:], "stderr_tail": (p.stderr or "")[-6000:]})
    return {"ok": all(x.get("ok") is True for x in checks), "checks": checks}


def _rollback(root: Path, work: Path, request_id: str, target_path: str, before: bytes | None, current_sha: str | None) -> dict[str, Any]:
    if before is None: return {"attempted": False, "reason": "new_file_delete_requires_builder_delete_contract"}
    rb_id = request_id + ".rollback"; lane = _run_lane(root, work, rb_id, target_path, before, current_sha); live = root / target_path; after = sha256_file(live) if live.is_file() else None; expected = sha256_bytes(before)
    return {"attempted": True, "ok": after == expected, "expected_sha256": expected, "after_sha256": after, **lane}


def _autonomous_deploy(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    auto = _load(HERE / "EIRA2_AUTONOMOUS_ENGINEERING_LOOP_V1.py", "eira2_autonomous_engineering_v1_runtime")
    dep = request.get("deployment") or {}; job = dep.get("autonomous_job") or {}; prepared = auto.prepare_candidate(root, request); payload = prepared["payload"]; target_path = prepared["target_path"]; before_sha = prepared.get("before_sha256")
    live = root / target_path; before = live.read_bytes() if live.is_file() else None; payload_sha = sha256_bytes(payload); lane = _run_lane(root, work, request["request_id"], target_path, payload, before_sha); post = _post_verify(root, target_path, payload_sha, job)
    if post.get("ok") is not True:
        current = sha256_file(live) if live.is_file() else None; rollback = _rollback(root, work, request["request_id"], target_path, before, current)
        raise RuntimeError("autonomous_post_deploy_verification_failed:" + json.dumps({"post_verify": post, "rollback": rollback}, sort_keys=True)[-3200:])
    after = sha256_file(live) if live.is_file() else None
    return {"schema": "eira2_transport_autonomous_deployment_evidence_v1", "request_id": request["request_id"], "watcher_authorization": auth, "builder_invoked": True, "autonomous_engineering": prepared["evidence"], "before_sha256": before_sha, "after_sha256": after, "completion_sha256": after, "payload_sha256": payload_sha, "post_deploy_verification": post, "lane_receipt": lane.get("lane_receipt") or {}, "generated_unix": time.time()}


def deploy_request(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    dep = request.get("deployment") or {}
    if dep.get("autonomous_job"): return _autonomous_deploy(root, work, request, auth)
    source = dep.get("source") or {}
    if source.get("manifest"): return _manifest_deploy(root, work, request, auth)
    return _legacy_deploy(root, work, request, auth)
