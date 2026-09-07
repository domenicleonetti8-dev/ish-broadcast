#!/usr/bin/env python3
from __future__ import annotations

import argparse, ast, hashlib, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
REMOTE_BLUEPRINTS = Path("eira2_transport_bus/to_superprobe/blueprints")
RETURN_ROOT = Path("eira2_transport_bus/from_superprobe/deployments")
TRANSPORT_SCHEMA = "eira2_blueprint_transport_v2"
LANE_SCHEMA = "eira2_builder_blueprint_v2"
LANE_NAME = "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, check=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sync_repo(work: Path) -> None:
    if not (work / ".git").is_dir():
        if work.exists():
            shutil.rmtree(work)
        p = run(["git", "clone", "--quiet", REPO_URL, str(work)], timeout=300)
        if p.returncode:
            raise RuntimeError("git_clone_failed:" + p.stderr[-800:])
    for cmd in (["git", "fetch", "--quiet", "origin", "master"], ["git", "checkout", "--quiet", "master"], ["git", "reset", "--hard", "origin/master"]):
        p = run(list(cmd), cwd=work, timeout=300)
        if p.returncode:
            raise RuntimeError("git_sync_failed:" + p.stderr[-800:])


def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{repo_path}"], capture_output=True, timeout=120, check=False)
    if p.returncode:
        raise RuntimeError("source_blob_missing:" + p.stderr[-800:].decode(errors="replace"))
    return p.stdout


def extract_embedded_payload(source: bytes, target_path: str) -> bytes:
    text = source.decode("utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "NEW" for t in targets):
                value = ast.literal_eval(node.value)
                if not isinstance(value, str):
                    raise RuntimeError("embedded_NEW_not_string")
                raw = value.encode("utf-8")
                if target_path.endswith(".py"):
                    compile(value, target_path, "exec")
                return raw
    raise RuntimeError("embedded_NEW_payload_missing")


def materialize_payload(repo: Path, blueprint: dict[str, Any]) -> tuple[str, str, str]:
    source = blueprint.get("source") or {}
    target = blueprint.get("target") or {}
    commit = str(source.get("commit") or "")
    path = str(source.get("path") or "")
    expected_source = str(source.get("sha256") or "").lower()
    target_path = str(target.get("path") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("source_commit_invalid")
    if not path or not target_path:
        raise RuntimeError("source_or_target_missing")
    source_bytes = git_blob(repo, commit, path)
    if expected_source and sha256_bytes(source_bytes) != expected_source:
        raise RuntimeError("source_sha256_mismatch")

    # Transport artifacts may be either direct payloads or self-contained replacement installers.
    if path.endswith(".py") and b"NEW = " in source_bytes and b"TARGET = " in source_bytes:
        payload = extract_embedded_payload(source_bytes, target_path)
    else:
        payload = source_bytes

    generated_rel = f".eira2_generated/{blueprint['blueprint_id']}/{Path(target_path).name}"
    generated = repo / generated_rel
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(payload)
    p = run(["git", "add", generated_rel], cwd=repo)
    if p.returncode:
        raise RuntimeError("generated_git_add_failed:" + p.stderr[-500:])
    p = run([
        "git", "-c", "user.name=EIRA Transport Materializer", "-c", "user.email=eira-transport@localhost",
        "commit", "--quiet", "-m", f"Materialize {blueprint['blueprint_id']} payload",
    ], cwd=repo)
    if p.returncode:
        raise RuntimeError("generated_commit_failed:" + p.stderr[-500:])
    synthetic_commit = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    return synthetic_commit, generated_rel, sha256_bytes(payload)


def watcher_version(root: Path) -> str | None:
    path = root / "extensions" / "repair_watcher_ai" / "plugin.py"
    if not path.is_file():
        return None
    m = re.search(r"^VERSION\s*=\s*[\"']([^\"']+)", path.read_text(encoding="utf-8", errors="replace"), re.M)
    return m.group(1) if m else None


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def publish_receipt(work: Path, rel: Path) -> str:
    # Drop the local synthetic payload commit before publishing transport evidence.
    p = run(["git", "reset", "--hard", "origin/master"], cwd=work)
    if p.returncode:
        raise RuntimeError("git_reset_before_publish_failed:" + p.stderr[-500:])
    p = run(["git", "add", rel.as_posix()], cwd=work)
    if p.returncode:
        raise RuntimeError("receipt_git_add_failed:" + p.stderr[-500:])
    diff = run(["git", "diff", "--cached", "--quiet"], cwd=work)
    if diff.returncode == 0:
        return run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    p = run([
        "git", "-c", "user.name=EIRA Return Transport", "-c", "user.email=eira-return@localhost",
        "commit", "--quiet", "-m", "Return EIRA2 deployment receipt",
    ], cwd=work)
    if p.returncode:
        raise RuntimeError("receipt_commit_failed:" + p.stderr[-500:])
    p = run(["git", "pull", "--rebase", "--quiet", "origin", "master"], cwd=work, timeout=300)
    if p.returncode:
        raise RuntimeError("receipt_rebase_failed:" + p.stderr[-800:])
    p = run(["git", "push", "--quiet", "origin", "master"], cwd=work, timeout=300)
    if p.returncode:
        raise RuntimeError("receipt_push_failed:" + p.stderr[-800:])
    return run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()


def process_blueprint(root: Path, work: Path, src: Path, state_dir: Path) -> dict[str, Any]:
    raw = src.read_bytes()
    digest = sha256_bytes(raw)
    blueprint = json.loads(raw.decode("utf-8"))
    if not isinstance(blueprint, dict) or blueprint.get("schema") != TRANSPORT_SCHEMA:
        return {"ignored": True, "path": src.name}
    blueprint_id = str(blueprint.get("blueprint_id") or "")
    if not ID_RE.fullmatch(blueprint_id):
        raise RuntimeError("invalid_blueprint_id")
    done = state_dir / f"{digest}.json"
    if done.exists():
        return {"already_handled": True, "blueprint_id": blueprint_id}

    target = blueprint.get("target") or {}
    target_path = str(target.get("path") or "")
    before_expected = str(target.get("expected_before_sha256") or "").lower()
    live_target = root / target_path
    before_actual = sha256_file(live_target) if live_target.is_file() else None
    transaction_id = f"{int(time.time())}-{digest[:12]}"
    receipt_rel = RETURN_ROOT / f"{blueprint_id}__{transaction_id}__receipt.json"
    receipt_abs = work / receipt_rel
    error: str | None = None
    lane_proc: subprocess.CompletedProcess[str] | None = None
    after_actual: str | None = before_actual
    payload_sha: str | None = None

    try:
        if before_expected and before_actual != before_expected:
            raise RuntimeError(f"live_before_hash_mismatch:{before_actual}")
        synthetic_commit, generated_rel, payload_sha = materialize_payload(work, blueprint)
        local_packet_dir = root / "eira_probe" / "transport_inbox" / "materialized_blueprints"
        local_packet_dir.mkdir(parents=True, exist_ok=True)
        packet_path = local_packet_dir / f"{blueprint_id}__{transaction_id}.json"
        packet = {
            "schema": LANE_SCHEMA,
            "packet_id": f"{blueprint_id}-{transaction_id}"[:96],
            "apply": True,
            "source_commit": synthetic_commit,
            "payloads": [{
                "repo_path": generated_rel,
                "target_path": target_path,
                "before_sha256": before_expected,
            }],
        }
        atomic_json(packet_path, packet)
        lane = work / LANE_NAME
        lane_proc = run([
            sys.executable, str(lane), "--root", str(root), "--packet", str(packet_path),
            "--source-repo-root", str(work),
        ], cwd=root, timeout=1800)
        after_actual = sha256_file(live_target) if live_target.is_file() else None
        if lane_proc.returncode:
            raise RuntimeError("deployment_lane_failed:" + (lane_proc.stderr or lane_proc.stdout)[-1200:])
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"[:2000]
        after_actual = sha256_file(live_target) if live_target.is_file() else None

    packet_id = f"{blueprint_id}-{transaction_id}"[:96]
    lane_receipt_path = root / "eira_probe" / "blueprint_receipts" / f"{packet_id}.lane_v4.json"
    builder_receipt_path = root / "eira_probe" / "eira2_builder_receipt.json"
    superprobe_path = root / "eira_probe" / "eira2_superprobe_report.json"
    lane_receipt = read_json(lane_receipt_path)
    builder_receipt = read_json(builder_receipt_path)
    superprobe = read_json(superprobe_path)

    watcher_authorized = bool(lane_proc and lane_proc.returncode == 0 and lane_receipt.get("status") == "accepted")
    builder_deployed = bool(watcher_authorized and after_actual and after_actual != before_actual)
    package_ok = bool(superprobe.get("package_identity_ok") is True)
    superprobe_ok = bool(superprobe.get("ok") is True)
    discrepancies = superprobe.get("discrepancy_count")
    evidence_fp = superprobe.get("evidence_fingerprint") or superprobe.get("shared_evidence_fingerprint")
    rollback = bool(builder_receipt.get("rollback_performed") is True or builder_receipt.get("rolled_back") is True)

    if rollback:
        status = "ROLLED_BACK"
    elif error is None and watcher_authorized and builder_deployed and package_ok and superprobe_ok and discrepancies == 0:
        status = "DEPLOYED_SUCCESSFULLY"
    else:
        status = "DEPLOYMENT_FAILED"

    source_checks = {}
    if live_target.is_file() and target_path == "eira2/live.py":
        text = live_target.read_text(encoding="utf-8", errors="replace")
        source_checks = {
            "v1_text_route_present": '"/v1/text"' in text,
            "v1_listen_route_present": '"/v1/listen"' in text,
            "native_pcm_transcription_bound": "runtime.native_input.transcribe_pcm" in text,
            "canonical_runtime_process_bound": "runtime.process" in text,
        }
    acceptance_results = {
        "target_hash_changed": bool(after_actual and after_actual != before_actual),
        "payload_sha256_matches_target": bool(payload_sha and after_actual == payload_sha),
        "package_identity_ok": package_ok,
        "superprobe_ok": superprobe_ok,
        "superprobe_zero_discrepancy": discrepancies == 0,
        "single_target_only": True,
        "runtime_source_checks": source_checks,
        "live_http_roundtrip_verified": False,
        "note": "HTTP roundtrip requires the live process to be running the newly deployed file; this receipt does not fake that check.",
    }

    receipt = {
        "schema": "eira2_immediate_deployment_return_receipt_v1",
        "blueprint_id": blueprint_id,
        "transaction_id": transaction_id,
        "status": status,
        "completed_utc": utc_now(),
        "watcher_authorized": watcher_authorized,
        "watcher_version": watcher_version(root),
        "builder_deployed": builder_deployed,
        "builder_receipt": str(builder_receipt_path) if builder_receipt_path.is_file() else None,
        "target_path": target_path,
        "before_sha256": before_actual,
        "after_sha256": after_actual,
        "payload_sha256": payload_sha,
        "package_identity_ok": package_ok,
        "superprobe_schema": superprobe.get("schema"),
        "superprobe_ok": superprobe_ok,
        "superprobe_discrepancy_count": discrepancies,
        "superprobe_evidence_fingerprint": evidence_fp,
        "acceptance_results": acceptance_results,
        "rollback_performed": rollback,
        "error": error,
        "lane_receipt": str(lane_receipt_path) if lane_receipt_path.is_file() else None,
        "transport_blueprint_sha256": digest,
    }

    # Preserve the receipt while returning the repo to origin/master.
    receipt_copy = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    run(["git", "reset", "--hard", "origin/master"], cwd=work)
    receipt_abs.parent.mkdir(parents=True, exist_ok=True)
    receipt_abs.write_text(receipt_copy, encoding="utf-8")
    return_commit = publish_receipt(work, receipt_rel)
    receipt["return_transport_commit"] = return_commit
    atomic_json(done, receipt)
    return receipt


def process_once(root: Path, work: Path, state_dir: Path) -> list[dict[str, Any]]:
    sync_repo(work)
    results: list[dict[str, Any]] = []
    remote = work / REMOTE_BLUEPRINTS
    for src in sorted(remote.glob("*.json")):
        try:
            result = process_blueprint(root, work, src, state_dir)
            if not result.get("ignored") and not result.get("already_handled"):
                results.append(result)
            # Each publish may update origin; resync before the next blueprint.
            sync_repo(work)
        except Exception as exc:
            results.append({"status": "CONSUMER_ERROR", "path": src.name, "error": f"{type(exc).__name__}:{exc}"})
            sync_repo(work)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/media/domenicleonetti/easystore/EIRA/LIVE")
    ap.add_argument("--work", default="/tmp/eira2_bidirectional_transport_v1")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    state = root / "eira_probe" / "bidirectional_consumer_state_v1"
    if not root.is_dir():
        raise SystemExit("EIRA_ROOT_MISSING")
    state.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            rows = process_once(root, work, state)
            if rows:
                print(json.dumps({"EIRA2_BIDIRECTIONAL_CONSUMER": "PASS", "results": rows}, indent=2), flush=True)
        except Exception as exc:
            print(json.dumps({"EIRA2_BIDIRECTIONAL_CONSUMER": "FAIL", "error": f"{type(exc).__name__}:{exc}"}, indent=2), file=sys.stderr, flush=True)
            if args.once:
                return 2
        if args.once:
            return 0
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
