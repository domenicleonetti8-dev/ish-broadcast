#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = "eira2_omnidirectional_superprobe_transport_v1"
PACKET_SCHEMA = "eira2_superprobe_transport_packet_v1"
ROOT_DEFAULT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
REPORT_REL = Path("eira_probe/eira2_superprobe_report.json")
EVIDENCE_REL = Path("eira_probe/eira2_superprobe_evidence")
BUS_REL = Path("eira_probe/omnidirectional_transport")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_root(root: Path) -> Path:
    root = root.expanduser().resolve()
    if not (root / "eira2").is_dir():
        raise RuntimeError(f"eira2_root_missing:{root}")
    if not (root / REPORT_REL).is_file():
        raise RuntimeError("superprobe_report_missing")
    return root


def require_clean_superprobe(root: Path) -> dict[str, Any]:
    report = read_json(root / REPORT_REL)
    if report.get("schema") != "eira2_superprobe_forensic_v4":
        raise RuntimeError(f"unsupported_superprobe_schema:{report.get('schema')}")
    if report.get("ok") is not True:
        raise RuntimeError("superprobe_not_clean")
    fingerprint = str(report.get("evidence_fingerprint") or "")
    shared = str(report.get("shared_evidence_fingerprint") or "")
    if not fingerprint or fingerprint != shared:
        raise RuntimeError("superprobe_fingerprint_mismatch")
    return report


def paths(root: Path) -> dict[str, Path]:
    base = root / BUS_REL
    return {
        "base": base,
        "outbox": base / "outbox",
        "inbox": base / "inbox",
        "accepted": base / "accepted",
        "rejected": base / "rejected",
        "receipts": base / "receipts",
        "watcher": base / "watcher_handoff",
        "state": base / "state.json",
    }


def ensure_bus(root: Path) -> dict[str, Path]:
    p = paths(root)
    for key, value in p.items():
        if key != "state":
            value.mkdir(parents=True, exist_ok=True)
    if not p["state"].exists():
        atomic_write(p["state"], pretty_bytes({
            "schema": SCHEMA,
            "last_outbound_packet": None,
            "last_inbound_packet": None,
        }))
    return p


def payload_sha(payload: Any) -> str:
    return sha256_bytes(canonical_bytes(payload))


def seal_packet(packet: dict[str, Any]) -> dict[str, Any]:
    packet = dict(packet)
    packet.pop("packet_sha256", None)
    packet["packet_sha256"] = sha256_bytes(canonical_bytes(packet))
    return packet


def verify_packet(packet: dict[str, Any]) -> None:
    if packet.get("schema") != PACKET_SCHEMA:
        raise RuntimeError("packet_schema_invalid")
    expected = str(packet.get("packet_sha256") or "")
    body = dict(packet)
    body.pop("packet_sha256", None)
    if expected != sha256_bytes(canonical_bytes(body)):
        raise RuntimeError("packet_sha256_invalid")
    if str(packet.get("payload_sha256") or "") != payload_sha(packet.get("payload")):
        raise RuntimeError("payload_sha256_invalid")
    if packet.get("direction") not in {"outbound", "inbound"}:
        raise RuntimeError("packet_direction_invalid")


def new_packet(*, direction: str, kind: str, source: str, destination: str,
               payload: Any, fingerprint: str | None, package_tree: str | None = None) -> dict[str, Any]:
    packet = {
        "schema": PACKET_SCHEMA,
        "packet_id": uuid.uuid4().hex,
        "created_unix": time.time(),
        "direction": direction,
        "kind": kind,
        "source": source,
        "destination": destination,
        "superprobe_evidence_fingerprint": fingerprint,
        "package_tree_sha256": package_tree,
        "payload": payload,
        "payload_sha256": payload_sha(payload),
        "transport_boundary": "eira_probe_only",
        "direct_eira2_mutation": False,
    }
    return seal_packet(packet)


def export_probe(root: Path) -> Path:
    p = ensure_bus(root)
    report = require_clean_superprobe(root)
    evidence_dir = root / EVIDENCE_REL
    manifest = []
    if evidence_dir.is_dir():
        for item in sorted(evidence_dir.glob("*.json")):
            data = item.read_bytes()
            manifest.append({"name": item.name, "bytes": len(data), "sha256": sha256_bytes(data)})
    payload = {"report": report, "evidence_manifest": manifest}
    packet = new_packet(
        direction="outbound",
        kind="superprobe_evidence_snapshot",
        source="eira2.superprobe",
        destination="github.omnidirectional_probe",
        payload=payload,
        fingerprint=report.get("evidence_fingerprint"),
        package_tree=report.get("package_identity", {}).get("package_tree_sha256"),
    )
    out = p["outbox"] / f"{packet['packet_id']}.json"
    atomic_write(out, pretty_bytes(packet))
    state = read_json(p["state"])
    state["last_outbound_packet"] = packet["packet_id"]
    atomic_write(p["state"], pretty_bytes(state))
    return out


def export_blueprint(root: Path, blueprint: Path) -> Path:
    p = ensure_bus(root)
    report = require_clean_superprobe(root)
    raw = blueprint.read_bytes()
    try:
        content: Any = json.loads(raw.decode("utf-8"))
        fmt = "json"
    except Exception:
        content = raw.decode("utf-8", errors="replace")
        fmt = "text"
    payload = {"name": blueprint.name, "format": fmt, "content": content}
    packet = new_packet(
        direction="outbound",
        kind="blueprint",
        source="eira2.superprobe",
        destination="github.omnidirectional_probe",
        payload=payload,
        fingerprint=report.get("evidence_fingerprint"),
        package_tree=report.get("package_identity", {}).get("package_tree_sha256"),
    )
    out = p["outbox"] / f"{packet['packet_id']}.json"
    atomic_write(out, pretty_bytes(packet))
    return out


def create_inbound(kind: str, payload_file: Path, output: Path,
                   fingerprint: str | None = None, source: str = "github.omnidirectional_probe") -> Path:
    raw = payload_file.read_bytes()
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
    except Exception:
        payload = {"name": payload_file.name, "format": "text", "content": raw.decode("utf-8", errors="replace")}
    packet = new_packet(
        direction="inbound",
        kind=kind,
        source=source,
        destination="eira2.superprobe",
        payload=payload,
        fingerprint=fingerprint,
    )
    atomic_write(output, pretty_bytes(packet))
    return output


def accept_inbound(root: Path, packet_file: Path) -> Path:
    p = ensure_bus(root)
    current = require_clean_superprobe(root)
    packet = read_json(packet_file)
    verify_packet(packet)
    if packet.get("direction") != "inbound":
        raise RuntimeError("expected_inbound_packet")
    claimed = packet.get("superprobe_evidence_fingerprint")
    if claimed not in {None, "", current.get("evidence_fingerprint")}:
        raise RuntimeError("inbound_packet_stale_superprobe_fingerprint")

    accepted = p["accepted"] / packet_file.name
    atomic_write(accepted, pretty_bytes(packet))
    handoff = {
        "schema": "eira2_watcher_handoff_v1",
        "packet_id": packet["packet_id"],
        "accepted_unix": time.time(),
        "kind": packet.get("kind"),
        "source": packet.get("source"),
        "packet_sha256": packet.get("packet_sha256"),
        "payload_sha256": packet.get("payload_sha256"),
        "superprobe_evidence_fingerprint": current.get("evidence_fingerprint"),
        "payload": packet.get("payload"),
        "authority": "watcher_evaluate_and_route",
        "direct_eira2_mutation": False,
    }
    handoff_path = p["watcher"] / f"{packet['packet_id']}.json"
    atomic_write(handoff_path, pretty_bytes(handoff))
    receipt = {
        "schema": "eira2_omnidirectional_accept_receipt_v1",
        "packet_id": packet["packet_id"],
        "accepted": True,
        "watcher_handoff": str(handoff_path),
        "packet_sha256": packet.get("packet_sha256"),
    }
    atomic_write(p["receipts"] / f"{packet['packet_id']}.accepted.json", pretty_bytes(receipt))
    state = read_json(p["state"])
    state["last_inbound_packet"] = packet["packet_id"]
    atomic_write(p["state"], pretty_bytes(state))
    return handoff_path


def status(root: Path) -> dict[str, Any]:
    p = ensure_bus(root)
    report = require_clean_superprobe(root)
    return {
        "schema": SCHEMA,
        "ok": True,
        "superprobe_ok": True,
        "superprobe_fingerprint": report.get("evidence_fingerprint"),
        "package_identity_ok": report.get("package_identity_ok"),
        "organism_ok": report.get("organism_ok"),
        "unresolved_internal_imports": report.get("unresolved_internal_imports"),
        "outbox_packets": len(list(p["outbox"].glob("*.json"))),
        "accepted_packets": len(list(p["accepted"].glob("*.json"))),
        "watcher_handoffs": len(list(p["watcher"].glob("*.json"))),
        "state": read_json(p["state"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EIRA2 omnidirectional packet transport through the Superprobe boundary")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("export-probe")

    bp = sub.add_parser("export-blueprint")
    bp.add_argument("path", type=Path)

    inbound = sub.add_parser("create-inbound")
    inbound.add_argument("kind")
    inbound.add_argument("payload", type=Path)
    inbound.add_argument("--output", type=Path, required=True)
    inbound.add_argument("--fingerprint")

    accept = sub.add_parser("accept-inbound")
    accept.add_argument("packet", type=Path)

    args = parser.parse_args()
    if args.command == "create-inbound":
        out = create_inbound(args.kind, args.payload, args.output, args.fingerprint)
        print(json.dumps({"ok": True, "output": str(out)}, indent=2))
        return 0

    root = ensure_root(args.root)
    if args.command == "status":
        result = status(root)
    elif args.command == "export-probe":
        result = {"ok": True, "output": str(export_probe(root))}
    elif args.command == "export-blueprint":
        result = {"ok": True, "output": str(export_blueprint(root, args.path))}
    elif args.command == "accept-inbound":
        result = {"ok": True, "watcher_handoff": str(accept_inbound(root, args.packet))}
    else:
        raise RuntimeError("unsupported_command")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
