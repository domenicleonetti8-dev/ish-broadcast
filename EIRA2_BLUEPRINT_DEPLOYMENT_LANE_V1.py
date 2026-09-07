#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_builder_blueprint_v1"
PACKET_ID = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def safe_rel(value: str) -> Path:
    p = Path(value)
    if p.is_absolute() or ".." in p.parts:
        raise RuntimeError(f"unsafe_relative_path:{value}")
    return p


def run(cmd: list[str], cwd: Path, timeout: int = 900) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
    return {
        "cmd": cmd,
        "returncode": p.returncode,
        "stdout": p.stdout[-12000:],
        "stderr": p.stderr[-12000:],
    }


def load_packet(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise RuntimeError("blueprint_schema_mismatch")
    packet_id = str(payload.get("packet_id") or "")
    if not PACKET_ID.fullmatch(packet_id):
        raise RuntimeError("invalid_packet_id")
    if payload.get("apply") is not True:
        raise RuntimeError("blueprint_apply_not_true")
    if not isinstance(payload.get("builder_plan"), dict):
        raise RuntimeError("builder_plan_missing")
    if not isinstance(payload.get("payloads"), list):
        raise RuntimeError("payloads_missing")
    return payload


def materialize(packet: dict[str, Any], stage: Path) -> list[dict[str, Any]]:
    rows = []
    stage.mkdir(parents=True, exist_ok=False)
    payload_root = stage / "payloads"
    for row in packet["payloads"]:
        if not isinstance(row, dict):
            raise RuntimeError("payload_row_invalid")
        rel = safe_rel(str(row.get("path") or ""))
        encoded = str(row.get("content_b64") or "")
        expected = str(row.get("sha256") or "").lower()
        data = base64.b64decode(encoded, validate=True)
        actual = sha256_bytes(data)
        if expected != actual:
            raise RuntimeError(f"payload_sha256_mismatch:{rel}")
        target = payload_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append({"path": rel.as_posix(), "bytes": len(data), "sha256": actual})
    return rows


def builder_command(root: Path, plan: Path, receipt: Path) -> list[str]:
    return [sys.executable, str(root / "tools" / "eira2_builder_probe.py"), "--root", str(root), "--plan", str(plan), "--receipt", str(receipt)]


def superprobe_command(root: Path) -> list[str]:
    return [sys.executable, str(root / "tools" / "eira2_superprobe_engine.py"), "--root", str(root)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--packet", required=True)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    packet_path = Path(args.packet).expanduser().resolve()
    if not root.is_dir() or not (root / "tools" / "eira2_builder_probe.py").is_file():
        raise SystemExit("builder_probe_missing")
    if not (root / "tools" / "eira2_superprobe_engine.py").is_file():
        raise SystemExit("superprobe_engine_missing")

    packet = load_packet(packet_path)
    packet_id = packet["packet_id"]
    runtime = root / "eira_probe"
    stage = runtime / "blueprint_staging" / packet_id
    receipts = runtime / "blueprint_receipts"
    if stage.exists():
        raise SystemExit("packet_already_staged")

    payload_rows = materialize(packet, stage)
    plan = dict(packet["builder_plan"])
    plan.setdefault("work_root", str(stage))
    plan_path = stage / "builder_plan.json"
    builder_receipt = receipts / f"{packet_id}.builder.json"
    lane_receipt = receipts / f"{packet_id}.lane.json"
    atomic_json(plan_path, plan)

    pre = run(superprobe_command(root), root)
    if pre["returncode"] != 0:
        atomic_json(lane_receipt, {
            "schema": "eira2_blueprint_lane_receipt_v1",
            "packet_id": packet_id,
            "status": "rejected_preflight",
            "preflight": pre,
            "payloads": payload_rows,
            "live_modified": False,
            "generated_unix": time.time(),
        })
        print("EIRA2_BLUEPRINT=REJECTED_PREFLIGHT")
        return 2

    build = run(builder_command(root, plan_path, builder_receipt), root)
    post = run(superprobe_command(root), root) if build["returncode"] == 0 else None
    accepted = bool(build["returncode"] == 0 and post and post["returncode"] == 0)
    result = {
        "schema": "eira2_blueprint_lane_receipt_v1",
        "packet_id": packet_id,
        "status": "accepted" if accepted else "failed",
        "packet_sha256": sha256_bytes(packet_path.read_bytes()),
        "payloads": payload_rows,
        "builder_plan_sha256": sha256_bytes(plan_path.read_bytes()),
        "builder_receipt": str(builder_receipt),
        "preflight": pre,
        "builder": build,
        "postflight": post,
        "accepted_only_after_postflight_superprobe": True,
        "generated_unix": time.time(),
    }
    atomic_json(lane_receipt, result)
    print(json.dumps({
        "EIRA2_BLUEPRINT_DEPLOYMENT": "PASS" if accepted else "FAIL",
        "packet_id": packet_id,
        "builder_receipt": str(builder_receipt),
        "lane_receipt": str(lane_receipt),
    }, indent=2))
    return 0 if accepted else 3


if __name__ == "__main__":
    raise SystemExit(main())
