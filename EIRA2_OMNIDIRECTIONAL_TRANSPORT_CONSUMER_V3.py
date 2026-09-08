#!/usr/bin/env python3
from __future__ import annotations

import importlib.util, json, os, subprocess, sys, time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_load_failed:" + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_v2 = _load(HERE / "EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py", "eira2_transport_v2_compat")
_bridge = _load(HERE / "EIRA2_BLUEPRINT_PAYLOAD_BRIDGE_V1.py", "eira2_payload_bridge_v1")
_auto = _load(HERE / "EIRA2_AUTONOMOUS_ENGINEERING_LOOP_V1.py", "eira2_autonomous_engineering_v1")

# Preserve every public V2 helper and contract by default.
for _name in dir(_v2):
    if _name.startswith("__"):
        continue
    globals().setdefault(_name, getattr(_v2, _name))


def _normalized_qualification(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    q = _ORIGINAL_QUAL(root, spec)
    result = q.get("result")
    success = False
    contract = None
    if q.get("returncode") == 0 and isinstance(result, dict):
        if result.get("ok") is True:
            success = True
            contract = "ok_true"
        elif result.get("pass") is True:
            success = True
            contract = "pass_true"
        elif result.get("status") in {"PASS", "PASSED", "pass", "passed"}:
            success = True
            contract = "status_pass"
    q["ok"] = success
    q["accepted_success_contract"] = contract
    q["qualification_contract_normalized"] = True
    return q


_ORIGINAL_QUAL = _v2._execute_read_only_qualification


def inspect_request(root: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    original = _v2._execute_read_only_qualification
    _v2._execute_read_only_qualification = _normalized_qualification
    try:
        return _v2.inspect_request(root, request, auth)
    finally:
        _v2._execute_read_only_qualification = original


def _run_lane(root: Path, work: Path, request_id: str, target_path: str, payload: bytes, before_sha: str | None) -> dict[str, Any]:
    gen_rel = f".eira2_generated/{request_id}/{Path(target_path).name}"
    synth = _v2.synthetic_commit(work, request_id, gen_rel, payload)
    packet = root / "eira_probe" / "transport_inbox" / "canonical_requests" / f"{request_id}.json"
    packet.parent.mkdir(parents=True, exist_ok=True)
    _v2.atomic_json(packet, {
        "schema": "eira2_builder_blueprint_v2",
        "packet_id": request_id,
        "apply": True,
        "source_commit": synth,
        "payloads": [{
            "repo_path": gen_rel,
            "target_path": target_path,
            "before_sha256": before_sha,
        }],
    })
    lane = work / _v2.LANE_NAME
    p = _v2.run([sys.executable, str(lane), "--root", str(root), "--packet", str(packet), "--source-repo-root", str(work)], cwd=root, timeout=4200)
    if p.returncode:
        raise RuntimeError("deployment_lane_failed:" + (p.stderr or p.stdout)[-1800:])
    receipt_path = root / "eira_probe" / "blueprint_receipts" / f"{request_id}.lane_v4.json"
    lane_receipt = {}
    if receipt_path.is_file():
        try:
            lane_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception:
            lane_receipt = {}
    return {"synthetic_commit": synth, "lane_receipt": lane_receipt}


def _rollback(root: Path, work: Path, request_id: str, target_path: str, before: bytes | None, current_sha: str | None) -> dict[str, Any]:
    if before is None:
        live = root / target_path
        if live.exists():
            # Deletion is intentionally not performed directly. Autonomous creation of new files
            # must be retried/handled by a future builder delete contract rather than bypassing Builder.
            return {"attempted": False, "reason": "new_file_delete_requires_builder_delete_contract"}
        return {"attempted": False, "reason": "target_absent"}
    rb_id = request_id + ".rollback"
    lane = _run_lane(root, work, rb_id, target_path, before, current_sha)
    live = root / target_path
    after = _v2.sha256_file(live) if live.is_file() else None
    expected = _v2.sha256_bytes(before)
    return {"attempted": True, "ok": after == expected, "expected_sha256": expected, "after_sha256": after, **lane}


def _post_verify(root: Path, target_path: str, expected_sha: str, job: dict[str, Any]) -> dict[str, Any]:
    live = root / target_path
    actual = _v2.sha256_file(live) if live.is_file() else None
    checks = [{"name": "landed_sha256", "ok": actual == expected_sha, "expected": expected_sha, "actual": actual}]
    argv = job.get("post_verify_argv")
    if argv is not None:
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise RuntimeError("post_verify_argv_must_be_nonempty_string_list")
        timeout = max(1, min(int(job.get("post_verify_timeout_seconds") or 300), 1800))
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root), "HOME": str(root), "EIRA_AUTONOMOUS_POST_VERIFY": "1"}
        p = subprocess.run(argv, cwd=str(root), text=True, capture_output=True, timeout=timeout, check=False, env=env)
        checks.append({"name": "post_verify_argv", "ok": p.returncode == 0, "returncode": p.returncode, "stdout_tail": (p.stdout or "")[-12000:], "stderr_tail": (p.stderr or "")[-6000:]})
    return {"ok": all(x.get("ok") is True for x in checks), "checks": checks}


def _autonomous_deploy(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    dep = request.get("deployment") or {}
    job = dep.get("autonomous_job") or {}
    prepared = _auto.prepare_candidate(root, request)
    payload = prepared["payload"]
    target_path = prepared["target_path"]
    before_sha = prepared.get("before_sha256")
    live = root / target_path
    before = live.read_bytes() if live.is_file() else None
    payload_sha = _v2.sha256_bytes(payload)
    lane = _run_lane(root, work, request["request_id"], target_path, payload, before_sha)
    post = _post_verify(root, target_path, payload_sha, job)
    if post.get("ok") is not True:
        current = _v2.sha256_file(live) if live.is_file() else None
        rollback = _rollback(root, work, request["request_id"], target_path, before, current)
        raise RuntimeError("autonomous_post_deploy_verification_failed:" + json.dumps({"post_verify": post, "rollback": rollback}, sort_keys=True)[-3200:])
    after = _v2.sha256_file(live) if live.is_file() else None
    return {
        "schema": "eira2_transport_autonomous_deployment_evidence_v1",
        "request_id": request["request_id"],
        "watcher_authorization": auth,
        "builder_invoked": True,
        "autonomous_engineering": prepared["evidence"],
        "before_sha256": before_sha,
        "after_sha256": after,
        "completion_sha256": after,
        "payload_sha256": payload_sha,
        "post_deploy_verification": post,
        "lane_receipt": lane.get("lane_receipt") or {},
        "generated_unix": time.time(),
    }


def _manifest_deploy(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    dep = request.get("deployment") or {}
    source = dep.get("source") or {}
    target = dep.get("target") or {}
    target_path = _v2.safe_rel(str(target.get("path") or ""))
    before_expected = str(target.get("expected_before_sha256") or "").lower()
    live = root / target_path
    before_actual = _v2.sha256_file(live) if live.is_file() else None
    if before_expected and before_actual != before_expected:
        raise RuntimeError("live_before_hash_mismatch:" + str(before_actual))
    payload, bridge_evidence = _bridge.materialize_source(work, source)
    payload = _v2.extract_payload(payload, target_path)
    lane = _run_lane(root, work, request["request_id"], target_path, payload, before_expected or None)
    after = _v2.sha256_file(live) if live.is_file() else None
    expected = _v2.sha256_bytes(payload)
    if after != expected:
        raise RuntimeError(f"post_deploy_sha256_mismatch:{after}:{expected}")
    return {
        "schema": "eira2_transport_deployment_evidence_v3",
        "request_id": request["request_id"],
        "watcher_authorization": auth,
        "builder_invoked": True,
        "before_sha256": before_actual,
        "after_sha256": after,
        "completion_sha256": after,
        "payload_sha256": expected,
        "payload_bridge": bridge_evidence,
        "lane_receipt": lane.get("lane_receipt") or {},
        "generated_unix": time.time(),
    }


def deploy_request(root: Path, work: Path, request: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    dep = request.get("deployment") or {}
    if dep.get("autonomous_job"):
        return _autonomous_deploy(root, work, request, auth)
    source = dep.get("source") or {}
    if source.get("manifest"):
        return _manifest_deploy(root, work, request, auth)
    return _v2.deploy_request(root, work, request, auth)
