#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_builder_blueprint_v2"
PACKET_ID = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
PACKAGE_SCHEMA = "eira2_offsystem_surgery_package_v2"
INDEX_SCHEMA = "eira2_offsystem_file_index_v2"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError(f"unsafe_relative_path:{value}")
    return p.as_posix()


def load_packet(path: Path) -> dict[str, Any]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise RuntimeError("blueprint_schema_mismatch")
    pid = str(packet.get("packet_id") or "")
    if not PACKET_ID.fullmatch(pid):
        raise RuntimeError("invalid_packet_id")
    if packet.get("apply") is not True:
        raise RuntimeError("blueprint_apply_not_true")
    if not isinstance(packet.get("payloads"), list) or not packet["payloads"]:
        raise RuntimeError("payloads_missing")
    commit = str(packet.get("source_commit") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("source_commit_invalid")
    return packet


def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    rel = safe_rel(repo_path)
    p = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{rel}"], capture_output=True, timeout=120, check=False)
    if p.returncode:
        raise RuntimeError(f"source_blob_missing:{rel}:{p.stderr[-500:].decode(errors='replace')}")
    return p.stdout


def load_watcher(root: Path):
    path = root / "extensions" / "repair_watcher_ai" / "plugin.py"
    spec = importlib.util.spec_from_file_location("eira2_live_repair_watcher_v4", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("repair_watcher_import_failed")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def prepare_native_watcher_inbox(root: Path, repo: Path, packet: dict[str, Any], watcher: Any) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    inbox_fn = getattr(watcher, "_inbox", None)
    if not callable(inbox_fn):
        raise RuntimeError("watcher_inbox_missing")
    inbox = Path(inbox_fn()).expanduser().resolve()
    stage = inbox / "stage"
    inbox.mkdir(parents=True, exist_ok=True)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=False)

    rows = []
    targets = []
    for i, item in enumerate(packet["payloads"]):
        repo_path = safe_rel(str(item.get("repo_path") or ""))
        target_path = safe_rel(str(item.get("target_path") or ""))
        before = str(item.get("before_sha256") or "").strip().lower()
        target = (root / target_path).resolve()
        target.relative_to(root)
        if before:
            if not target.is_file() or sha256_file(target) != before:
                raise RuntimeError(f"live_before_hash_mismatch:{target_path}")
        data = git_blob(repo, str(packet["source_commit"]), repo_path)
        staged_rel = f"{i:03d}_{Path(target_path).name}"
        staged = stage / staged_rel
        staged.write_bytes(data)
        if target_path.endswith(".py"):
            q = subprocess.run([sys.executable, "-m", "py_compile", str(staged)], capture_output=True, text=True, timeout=60)
            if q.returncode:
                raise RuntimeError(f"payload_python_compile_failed:{target_path}:{q.stderr[-800:]}")
        digest = sha256_bytes(data)
        rows.append({"target_path": target_path, "staged_path": staged_rel, "sha256": digest})
        targets.append(target_path)

    index = {"schema": INDEX_SCHEMA, "files": rows}
    index_path = inbox / "file_index.json"
    atomic_json(index_path, index)
    index_sha = sha256_file(index_path)

    package_core = {
        "schema": PACKAGE_SCHEMA,
        "built_off_live": True,
        "writes_live": False,
        "eira2_only": True,
        "targets": targets,
        "file_index_sha256": index_sha,
        "source_commit_sha": str(packet["source_commit"]),
    }
    package_fp = sha256_bytes(json.dumps(package_core, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    package = dict(package_core)
    package["package_fingerprint_sha256"] = package_fp
    atomic_json(inbox / "surgery_package.json", package)
    return inbox, package, index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--source-repo-root", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve(); packet_path = Path(a.packet).resolve(); repo = Path(a.source_repo_root).resolve()
    packet = load_packet(packet_path); pid = str(packet["packet_id"])
    receipt_path = root / "eira_probe" / "blueprint_receipts" / f"{pid}.lane_v4.json"
    try:
        watcher, watcher_path = load_watcher(root)
        inbox, package, index = prepare_native_watcher_inbox(root, repo, packet, watcher)
        inspect = watcher.inspect_once()
        if not isinstance(inspect, dict) or inspect.get("ok") is not True:
            raise RuntimeError("watcher_plan_rejected:" + json.dumps(inspect, sort_keys=True)[-1200:])
        result = watcher.deploy_builder_probe()
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("watcher_transaction_failed:" + json.dumps(result, sort_keys=True)[-1600:])
        atomic_json(receipt_path, {
            "schema": "eira2_blueprint_lane_v4_receipt",
            "packet_id": pid,
            "status": "accepted",
            "watcher_native_contract_used": True,
            "watcher_plugin": str(watcher_path),
            "watcher_inbox": str(inbox),
            "package_fingerprint_sha256": package["package_fingerprint_sha256"],
            "planned_files": len(index["files"]),
            "watcher_result": result,
            "generated_unix": time.time(),
        })
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"PASS","packet_id":pid,"status":result.get("status")}, indent=2))
        return 0
    except Exception as exc:
        atomic_json(receipt_path, {"schema":"eira2_blueprint_lane_v4_receipt","packet_id":pid,"status":"rejected_or_failed","error":f"{type(exc).__name__}:{exc}"[:2000],"generated_unix":time.time()})
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"FAIL","packet_id":pid,"error":f"{type(exc).__name__}:{exc}"}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
