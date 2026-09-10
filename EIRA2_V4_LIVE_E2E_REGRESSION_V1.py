#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE").resolve()
TARGET = "eira_probe/regression/v4_live_e2e.txt"
REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
SCHEMA = "eira2_v4_live_e2e_regression_v1"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_load_failed:" + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transport_repo() -> Path:
    candidates = []
    probe = ROOT / "eira_probe"
    if probe.is_dir():
        candidates.extend(sorted(probe.glob("transport_runtime_*/repo"), reverse=True))
    for p in candidates:
        if (p / "EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py").is_file() and (p / "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py").is_file() and (p / ".git").is_dir():
            r = subprocess.run(["git", "fetch", "--quiet", "origin", "master"], cwd=str(p), capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                subprocess.run(["git", "checkout", "--quiet", "master"], cwd=str(p), capture_output=True, text=True, timeout=120)
                subprocess.run(["git", "reset", "--hard", "origin/master"], cwd=str(p), capture_output=True, text=True, timeout=120)
                return p
    p = Path(tempfile.mkdtemp(prefix="eira_v4_e2e_repo_", dir="/tmp")) / "repo"
    r = subprocess.run(["git", "clone", "--quiet", REPO_URL, str(p)], capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError("transport_repo_clone_failed:" + (r.stderr or r.stdout)[-1200:])
    return p


def main() -> int:
    started = time.time()
    if not ROOT.is_dir():
        raise RuntimeError("live_root_unavailable")
    worker_path = ROOT / "extensions" / "engineering_worker_ai" / "plugin.py"
    watcher_path = ROOT / "extensions" / "repair_watcher_ai" / "plugin.py"
    if not worker_path.is_file():
        raise RuntimeError("v4_worker_missing")
    if not watcher_path.is_file():
        raise RuntimeError("watcher_missing")

    worker = load(worker_path, "eira_v4_live_regression_worker")
    marker = "EIRA_V4_LIVE_E2E_OK_" + str(int(time.time()))
    verify_code = "from pathlib import Path; p=Path(%r); assert p.read_text().strip()==%r" % (TARGET, marker)
    request = {
        "root": str(ROOT),
        "objective": "Create exactly one regression artifact at %s containing exactly %s and no other content. This is a controlled end-to-end engineering regression. Do not modify any other file." % (TARGET, marker),
        "failure_evidence": ["Regression artifact does not yet contain the required unique marker: " + marker],
        "organism_interference": ["Controlled regression requires proof that the canonical engineering deployment path can materialize a qualified candidate into LIVE."],
        "verification_argv": [sys.executable, "-c", verify_code],
        "timeout_seconds": 1800,
    }
    built = worker.build(request)
    if built.get("ok") is not True:
        raise RuntimeError("v4_build_not_qualified:" + json.dumps(built, sort_keys=True)[-4000:])
    changed = built.get("changed_paths") or []
    if changed != [TARGET]:
        raise RuntimeError("unexpected_candidate_scope:" + json.dumps(changed))
    candidate = (built.get("candidates") or {}).get(TARGET) or {}
    content = candidate.get("content")
    if candidate.get("exists") is not True or not isinstance(content, str):
        raise RuntimeError("candidate_content_missing")
    payload = content.encode()
    if payload.decode().strip() != marker:
        raise RuntimeError("candidate_marker_mismatch")

    live = ROOT / TARGET
    before = live.read_bytes() if live.is_file() else None
    before_sha = sha(before) if before is not None else None

    watcher = load(watcher_path, "eira_v4_live_regression_watcher")
    authorize = getattr(watcher, "authorize_transport_request", None)
    if not callable(authorize):
        raise RuntimeError("watcher_transport_authority_unavailable")
    rid = "v4_live_e2e_" + str(int(time.time()))
    outer = {
        "schema": "eira2_transport_request_v1",
        "request_id": rid,
        "operation": "deploy",
        "autonomous_engineering": True,
        "sandbox_evidence": {
            "schema": SCHEMA,
            "worker_schema": built.get("schema"),
            "changed_paths": changed,
            "tests": built.get("tests"),
            "review_passed": built.get("review_passed"),
            "truth_honesty_gate": built.get("truth_honesty_gate"),
            "candidate_sha256": sha(payload),
            "target_path": TARGET,
            "live_mutated_during_creation": False,
        },
        "deployment": {"target": {"path": TARGET, "expected_before_sha256": before_sha}},
    }
    auth = authorize(outer)
    if not isinstance(auth, dict) or auth.get("authorized") is not True:
        raise RuntimeError("watcher_rejected:" + json.dumps(auth, sort_keys=True)[-2400:])

    repo = transport_repo()
    consumer = load(repo / "EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py", "eira_v4_live_regression_transport")
    lane = consumer._run_lane(ROOT, repo, rid, TARGET, payload, before_sha)

    if not live.is_file() or live.read_bytes() != payload:
        current = consumer.sha256_file(live) if live.is_file() else None
        rollback = consumer._rollback(ROOT, repo, rid + "_rollback", TARGET, before, current)
        raise RuntimeError("live_post_verify_failed;rollback=" + json.dumps(rollback, sort_keys=True)[-1800:])

    result = {
        "schema": SCHEMA,
        "ok": True,
        "request_id": rid,
        "worker_schema": built.get("schema"),
        "opencode_aider_build_qualified": True,
        "changed_paths": changed,
        "tests_passed": all(x.get("ok") is True for x in (built.get("tests") or [])),
        "opencode_review_passed": built.get("review_passed") is True,
        "truth_honesty_gate_passed": (built.get("truth_honesty_gate") or {}).get("ok") is True,
        "watcher_authorized": True,
        "builder_lane_invoked": True,
        "lane_receipt": lane.get("lane_receipt") or {},
        "live_target": str(live),
        "live_sha256": sha(live.read_bytes()),
        "candidate_sha256": sha(payload),
        "live_bytes_match_candidate": live.read_bytes() == payload,
        "marker": marker,
        "elapsed_seconds": round(time.time() - started, 3),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print("EIRA2_V4_LIVE_E2E_REGRESSION=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error": f"{type(exc).__name__}:{exc}"}, indent=2, sort_keys=True))
        print("EIRA2_V4_LIVE_E2E_REGRESSION=FAIL")
        raise
