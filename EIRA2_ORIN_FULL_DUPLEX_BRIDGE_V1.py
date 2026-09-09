#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
DEFAULT_ROOT = "/media/domenicleonetti/easystore/EIRA/LIVE"
DEFAULT_CONTROL_REF = "master"
REQUEST_ROOT = Path("eira2_transport_bus/to_superprobe/requests")
BLUEPRINT_ROOT = Path("eira2_transport_bus/to_superprobe/blueprints")
OUT_ROOT = Path("eira2_transport_bus/from_superprobe")
BRIDGE_SCHEMA = "eira2_orin_full_duplex_bridge_v1"
ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, check=False)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def valid_id(value: str) -> bool:
    return bool(value) and len(value) <= 96 and all(ch in ID_CHARS for ch in value)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_load_failed:" + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def heal_git(repo: Path) -> None:
    git = repo / ".git"
    if not git.is_dir():
        return
    if (git / "rebase-merge").exists() or (git / "rebase-apply").exists():
        run(["git", "rebase", "--abort"], cwd=repo, timeout=120)
    if (git / "MERGE_HEAD").exists():
        run(["git", "merge", "--abort"], cwd=repo, timeout=120)
    lock = git / "index.lock"
    if lock.exists():
        try:
            if time.time() - lock.stat().st_mtime > 300:
                lock.unlink()
        except OSError:
            pass


def sync_repo(repo: Path, control_ref: str) -> None:
    if not (repo / ".git").is_dir():
        if repo.exists():
            shutil.rmtree(repo)
        p = run(["git", "clone", "--quiet", REPO_URL, str(repo)], timeout=600)
        if p.returncode:
            raise RuntimeError("git_clone_failed:" + (p.stdout + p.stderr)[-1800:])
    heal_git(repo)
    for cmd in (
        ["git", "fetch", "--quiet", "origin", "+refs/heads/*:refs/remotes/origin/*"],
        ["git", "checkout", "--quiet", "-B", "eira2_orin_bridge_runtime", f"origin/{control_ref}"],
        ["git", "reset", "--hard", f"origin/{control_ref}"],
        ["git", "clean", "-fd"],
    ):
        p = run(cmd, cwd=repo, timeout=600)
        if p.returncode:
            raise RuntimeError("git_sync_failed:" + (p.stdout + p.stderr)[-1800:])


def publish(repo: Path, control_ref: str, rel: Path, payload: dict[str, Any], message: str) -> str:
    sync_repo(repo, control_ref)
    atomic_json(repo / rel, payload)
    p = run(["git", "add", rel.as_posix()], cwd=repo, timeout=120)
    if p.returncode:
        raise RuntimeError("git_add_failed:" + (p.stdout + p.stderr)[-1200:])
    if run(["git", "diff", "--cached", "--quiet"], cwd=repo, timeout=120).returncode == 0:
        return run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=120).stdout.strip()
    p = run([
        "git", "-c", "user.name=EIRA Orin Bridge", "-c", "user.email=eira-orin-bridge@localhost",
        "commit", "--quiet", "-m", message,
    ], cwd=repo, timeout=120)
    if p.returncode:
        raise RuntimeError("git_commit_failed:" + (p.stdout + p.stderr)[-1600:])
    p = run(["git", "pull", "--rebase", "--quiet", "origin", control_ref], cwd=repo, timeout=600)
    if p.returncode:
        heal_git(repo)
        raise RuntimeError("git_rebase_failed:" + (p.stdout + p.stderr)[-1800:])
    p = run(["git", "push", "--quiet", "origin", f"HEAD:{control_ref}"], cwd=repo, timeout=600)
    if p.returncode:
        raise RuntimeError("git_push_failed:" + (p.stdout + p.stderr)[-1800:])
    return run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=120).stdout.strip()


def owner_lock(runtime: Path):
    runtime.mkdir(parents=True, exist_ok=True)
    fh = (runtime / "owner.lock").open("a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        fh.close()
        raise RuntimeError("orin_bridge_owner_already_active") from exc
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()) + "\n")
    fh.flush()
    os.fsync(fh.fileno())
    return fh


def load_transport(repo: Path):
    path = repo / "EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py"
    if not path.is_file():
        raise RuntimeError("canonical_transport_consumer_missing")
    return load_module(path, "eira2_orin_bridge_transport")


def load_blueprint(repo: Path):
    path = repo / "EIRA2_BIDIRECTIONAL_BLUEPRINT_CONSUMER_V1.py"
    if not path.is_file():
        raise RuntimeError("bidirectional_blueprint_consumer_missing")
    return load_module(path, "eira2_orin_bridge_blueprint")


def watcher_snapshot(root: Path) -> dict[str, Any]:
    path = root / "extensions" / "repair_watcher_ai" / "plugin.py"
    out: dict[str, Any] = {"path": str(path), "present": path.is_file(), "sha256": sha256_file(path)}
    if path.is_file():
        try:
            mod = load_module(path, "eira2_orin_bridge_watcher")
            out["version"] = getattr(mod, "VERSION", None)
            inspect_once = getattr(mod, "inspect_once", None)
            if callable(inspect_once):
                result = inspect_once()
                out["inspect_ok"] = bool(isinstance(result, dict) and result.get("ok") is True)
                out["inspect_result"] = result
        except Exception as exc:
            out["inspect_error"] = f"{type(exc).__name__}:{exc}"[:2000]
    return out


def telemetry(root: Path, runtime: Path, control_ref: str) -> dict[str, Any]:
    probe = root / "eira_probe"
    files = {
        "superprobe": probe / "eira2_superprobe_report.json",
        "builder_receipt": probe / "eira2_builder_receipt.json",
        "transport_v6_heartbeat": probe / "transport_runtime_v6" / "heartbeat.json",
        "transport_v8_owner": probe / "transport_runtime_v8" / "owner.lock",
    }
    rows = {}
    for name, path in files.items():
        rows[name] = {"path": str(path), "present": path.exists(), "sha256": sha256_file(path)}
        if path.is_file() and path.suffix == ".json":
            try:
                rows[name]["json"] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                rows[name]["json_error"] = f"{type(exc).__name__}:{exc}"[:1000]
    return {
        "schema": BRIDGE_SCHEMA,
        "kind": "live_telemetry",
        "control_ref": control_ref,
        "root": str(root),
        "bridge_pid": os.getpid(),
        "generated_unix": time.time(),
        "watcher": watcher_snapshot(root),
        "evidence": rows,
        "runtime": str(runtime),
    }


def exact_request(repo: Path, root: Path, runtime: Path, control_ref: str, request_id: str) -> dict[str, Any]:
    source = repo / REQUEST_ROOT / f"{request_id}.json"
    if not source.is_file():
        matches = sorted((repo / REQUEST_ROOT).glob(f"*{request_id}*.json"))
        if len(matches) != 1:
            raise RuntimeError(f"exact_request_not_resolved:{request_id}:{len(matches)}")
        source = matches[0]
    request = json.loads(source.read_text(encoding="utf-8"))
    rid = str(request.get("request_id") or "")
    if rid != request_id:
        raise RuntimeError(f"request_id_mismatch:{rid}:{request_id}")
    transport = load_transport(repo)
    watcher = load_module(root / "extensions" / "repair_watcher_ai" / "plugin.py", "eira2_orin_bridge_auth_watcher")
    auth_fn = getattr(watcher, "authorize_transport_request", None)
    if callable(auth_fn):
        auth = auth_fn(request)
        if not isinstance(auth, dict) or auth.get("authorized") is not True:
            raise RuntimeError("watcher_rejected:" + json.dumps(auth, sort_keys=True)[-1600:])
    elif str(request.get("operation") or "").casefold() == "inspect":
        inspect_once = getattr(watcher, "inspect_once", None)
        result = inspect_once() if callable(inspect_once) else None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("watcher_read_only_authority_unavailable")
        auth = {"authorized": True, "authorized_by": "repair_watcher_ai", "legacy_read_only_authorization": True}
    else:
        raise RuntimeError("watcher_transport_authority_unavailable")
    op = str(request.get("operation") or "").casefold()
    if op == "inspect":
        evidence = transport.inspect_request(root, request, auth)
        result = {"status": "INSPECTION_COMPLETE", "ok": True, "operation": op, "evidence": evidence}
    elif op == "deploy":
        evidence = transport.deploy_request(root, repo, request, auth)
        result = {"status": "DEPLOYED_SUCCESSFULLY", "ok": True, "operation": op, "deployment": evidence}
    else:
        raise RuntimeError("unsupported_request_operation:" + op)
    receipt = {
        "schema": BRIDGE_SCHEMA,
        "kind": "exact_request_receipt",
        "request_id": request_id,
        "source_file": source.name,
        "source_sha256": sha256_file(source),
        "control_ref": control_ref,
        "watcher_authorization": auth,
        "result": result,
        "completed_unix": time.time(),
    }
    atomic_json(runtime / "local_receipts" / f"{request_id}.json", receipt)
    return receipt


def exact_blueprint(repo: Path, root: Path, runtime: Path, control_ref: str, blueprint_id: str) -> dict[str, Any]:
    source = repo / BLUEPRINT_ROOT / f"{blueprint_id}.json"
    if not source.is_file():
        matches = sorted((repo / BLUEPRINT_ROOT).glob(f"*{blueprint_id}*.json"))
        if len(matches) != 1:
            raise RuntimeError(f"exact_blueprint_not_resolved:{blueprint_id}:{len(matches)}")
        source = matches[0]
    blueprint_mod = load_blueprint(repo)
    state = runtime / "blueprint_state"
    state.mkdir(parents=True, exist_ok=True)
    result = blueprint_mod.process_blueprint(root, repo, source, state)
    receipt = {
        "schema": BRIDGE_SCHEMA,
        "kind": "exact_blueprint_receipt",
        "blueprint_id": blueprint_id,
        "source_file": source.name,
        "source_sha256": sha256_file(source),
        "control_ref": control_ref,
        "result": result,
        "completed_unix": time.time(),
    }
    atomic_json(runtime / "local_receipts" / f"blueprint__{blueprint_id}.json", receipt)
    return receipt


def publish_receipt(repo: Path, control_ref: str, receipt: dict[str, Any], key: str) -> str:
    rel = OUT_ROOT / "bridge_receipts" / f"{key}__receipt.json"
    return publish(repo, control_ref, rel, receipt, f"Return Orin bridge receipt {key}")


def publish_telemetry(repo: Path, root: Path, runtime: Path, control_ref: str) -> str:
    payload = telemetry(root, runtime, control_ref)
    rel = OUT_ROOT / "telemetry" / "orin_eira_live_latest.json"
    commit = publish(repo, control_ref, rel, payload, "Return EIRA LIVE telemetry through Orin bridge")
    atomic_json(runtime / "telemetry_latest.json", {**payload, "return_transport_commit": commit})
    return commit


def process_command(repo: Path, root: Path, runtime: Path, control_ref: str, command: dict[str, Any]) -> dict[str, Any]:
    kind = str(command.get("kind") or "")
    if kind == "request":
        request_id = str(command.get("request_id") or "")
        if not valid_id(request_id):
            raise RuntimeError("invalid_request_id")
        receipt = exact_request(repo, root, runtime, control_ref, request_id)
        receipt["return_transport_commit"] = publish_receipt(repo, control_ref, receipt, request_id)
        return receipt
    if kind == "blueprint":
        blueprint_id = str(command.get("blueprint_id") or "")
        if not valid_id(blueprint_id):
            raise RuntimeError("invalid_blueprint_id")
        receipt = exact_blueprint(repo, root, runtime, control_ref, blueprint_id)
        receipt["return_transport_commit"] = publish_receipt(repo, control_ref, receipt, "blueprint__" + blueprint_id)
        return receipt
    if kind == "telemetry":
        commit = publish_telemetry(repo, root, runtime, control_ref)
        return {"schema": BRIDGE_SCHEMA, "kind": "telemetry_receipt", "ok": True, "return_transport_commit": commit}
    raise RuntimeError("unsupported_command_kind:" + kind)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--work", default="/tmp/eira2_orin_full_duplex_bridge_v1")
    ap.add_argument("--control-ref", default=DEFAULT_CONTROL_REF)
    ap.add_argument("--request-id")
    ap.add_argument("--blueprint-id")
    ap.add_argument("--telemetry", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit("EIRA_ROOT_MISSING")
    runtime = root / "eira_probe" / "orin_full_duplex_bridge_v1"
    repo = Path(args.work).expanduser().resolve() / "repo"
    runtime.mkdir(parents=True, exist_ok=True)
    owner = owner_lock(runtime)
    try:
        sync_repo(repo, args.control_ref)
        if args.request_id:
            result = process_command(repo, root, runtime, args.control_ref, {"kind": "request", "request_id": args.request_id})
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.blueprint_id:
            result = process_command(repo, root, runtime, args.control_ref, {"kind": "blueprint", "blueprint_id": args.blueprint_id})
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.telemetry:
            result = process_command(repo, root, runtime, args.control_ref, {"kind": "telemetry"})
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if not args.daemon:
            raise SystemExit("CHOOSE --request-id, --blueprint-id, --telemetry, OR --daemon")

        commands_rel = Path("eira2_transport_bus/to_superprobe/bridge_commands")
        state = runtime / "command_state"
        state.mkdir(parents=True, exist_ok=True)
        last_telemetry = 0.0
        while True:
            sync_repo(repo, args.control_ref)
            for source in sorted((repo / commands_rel).glob("*.json")):
                raw = source.read_bytes()
                digest = sha256_bytes(raw)
                done = state / f"{digest}.json"
                if done.exists():
                    continue
                try:
                    command = json.loads(raw.decode("utf-8"))
                    result = process_command(repo, root, runtime, args.control_ref, command)
                    atomic_json(done, {"ok": True, "source": source.name, "result": result, "completed_unix": time.time()})
                except Exception as exc:
                    atomic_json(done, {"ok": False, "source": source.name, "error": f"{type(exc).__name__}:{exc}"[:4000], "completed_unix": time.time()})
                sync_repo(repo, args.control_ref)
            if time.time() - last_telemetry >= 60:
                try:
                    publish_telemetry(repo, root, runtime, args.control_ref)
                except Exception as exc:
                    atomic_json(runtime / "telemetry_error.json", {"error": f"{type(exc).__name__}:{exc}"[:4000], "unix": time.time()})
                last_telemetry = time.time()
            atomic_json(runtime / "heartbeat.json", {"schema": BRIDGE_SCHEMA, "pid": os.getpid(), "control_ref": args.control_ref, "unix": time.time(), "stage": "alive"})
            time.sleep(max(1.0, args.interval))
    finally:
        try:
            fcntl.flock(owner.fileno(), fcntl.LOCK_UN)
        finally:
            owner.close()


if __name__ == "__main__":
    raise SystemExit(main())
