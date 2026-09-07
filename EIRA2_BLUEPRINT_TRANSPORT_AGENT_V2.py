#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
REMOTE_DIR = Path("eira2_transport_bus/to_superprobe/blueprints")
RECEIPT_DIR = Path("eira2_transport_bus/receipts/blueprints")
SCHEMA = "eira2_builder_blueprint_v2"


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, check=False)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clone_repo(work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
    proc = run(["git", "clone", "--quiet", REPO_URL, str(work)], timeout=300)
    if proc.returncode:
        raise RuntimeError(f"git_clone_failed:{proc.stderr[-1000:]}")
    proc = run(["git", "checkout", "--quiet", "master"], cwd=work)
    if proc.returncode:
        raise RuntimeError(f"git_checkout_failed:{proc.stderr[-1000:]}")


def publish(work: Path, packet_id: str) -> None:
    rel = RECEIPT_DIR / packet_id
    proc = run(["git", "add", str(rel)], cwd=work)
    if proc.returncode:
        raise RuntimeError(f"git_add_failed:{proc.stderr[-1000:]}")
    status = run(["git", "diff", "--cached", "--quiet"], cwd=work)
    if status.returncode == 0:
        return
    proc = run([
        "git", "-c", "user.name=EIRA Blueprint Bridge",
        "-c", "user.email=eira-blueprint@localhost",
        "commit", "--quiet", "-m", f"Publish Watcher Builder receipt {packet_id}",
    ], cwd=work)
    if proc.returncode:
        raise RuntimeError(f"git_commit_failed:{proc.stderr[-1000:]}")
    proc = run(["git", "push", "--quiet", "origin", "master"], cwd=work, timeout=300)
    if proc.returncode:
        raise RuntimeError(f"git_push_failed:{proc.stderr[-1000:]}")


def process_once(root: Path, work: Path) -> dict[str, Any]:
    clone_repo(work)
    remote = work / REMOTE_DIR
    remote.mkdir(parents=True, exist_ok=True)
    local_inbox = root / "eira_probe" / "transport_inbox" / "blueprints"
    done_dir = root / "eira_probe" / "blueprint_transport_done_v2"
    runtime = root / "eira_probe" / "transport_runtime"
    lane = runtime / "eira2_blueprint_deployment_lane_v2.py"
    if not lane.is_file():
        raise RuntimeError("blueprint_deployment_lane_v2_missing")
    local_inbox.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)

    handled: list[dict[str, Any]] = []
    for src in sorted(remote.glob("*.json")):
        try:
            packet = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
            continue
        digest = sha256(src)
        done = done_dir / f"{digest}.json"
        if done.exists():
            continue
        packet_id = str(packet.get("packet_id") or src.stem)
        local = local_inbox / src.name
        shutil.copy2(src, local)
        proc = run([
            sys.executable,
            str(lane),
            "--root", str(root),
            "--packet", str(local),
            "--source-repo-root", str(work),
        ], cwd=root)

        dest = work / RECEIPT_DIR / packet_id
        dest.mkdir(parents=True, exist_ok=True)
        lane_receipt = root / "eira_probe" / "blueprint_receipts" / f"{packet_id}.lane_v2.json"
        builder_receipt = root / "eira_probe" / "eira2_builder_receipt.json"
        if lane_receipt.is_file():
            shutil.copy2(lane_receipt, dest / "lane_receipt.json")
        if builder_receipt.is_file():
            shutil.copy2(builder_receipt, dest / "builder_receipt.json")
        transport_receipt = {
            "schema": "eira2_blueprint_transport_receipt_v2",
            "packet_id": packet_id,
            "packet_sha256": digest,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "watcher_routed": True,
            "processed_unix": time.time(),
        }
        (dest / "transport_receipt.json").write_text(json.dumps(transport_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        publish(work, packet_id)
        if proc.returncode == 0:
            done.write_text(json.dumps(transport_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        handled.append({"packet_id": packet_id, "returncode": proc.returncode})
    return {"handled": handled, "count": len(handled)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/media/domenicleonetti/easystore/EIRA/LIVE")
    parser.add_argument("--work", default="/tmp/eira2_blueprint_transport_v2")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit("EIRA_ROOT_MISSING")
    while True:
        try:
            result = process_once(root, work)
            print(json.dumps({"EIRA2_BLUEPRINT_TRANSPORT_V2": "PASS", **result}, indent=2), flush=True)
        except Exception as exc:
            print(json.dumps({"EIRA2_BLUEPRINT_TRANSPORT_V2": "FAIL", "error": f"{type(exc).__name__}:{exc}"}, indent=2), file=sys.stderr, flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
