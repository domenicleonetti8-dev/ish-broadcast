#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_builder_blueprint_v2"
PACKET_ID = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run(cmd: list[str], cwd: Path, timeout: int = 1200) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }


def safe_rel(value: str) -> str:
    path = Path(str(value or ""))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise RuntimeError(f"unsafe_relative_path:{value}")
    return path.as_posix()


def load_packet(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise RuntimeError("blueprint_schema_mismatch")
    packet_id = str(payload.get("packet_id") or "")
    if not PACKET_ID.fullmatch(packet_id):
        raise RuntimeError("invalid_packet_id")
    if payload.get("apply") is not True:
        raise RuntimeError("blueprint_apply_not_true")
    if not isinstance(payload.get("payloads"), list) or not payload["payloads"]:
        raise RuntimeError("payloads_missing")
    source_commit = str(payload.get("source_commit") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_commit):
        raise RuntimeError("source_commit_invalid")
    return payload


def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    rel = safe_rel(repo_path)
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{rel}"],
        capture_output=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"source_blob_missing:{rel}:{proc.stderr[-500:].decode('utf-8', errors='replace')}")
    return proc.stdout


def materialize(root: Path, packet: dict[str, Any], repo: Path) -> tuple[Path, list[dict[str, Any]]]:
    stage = Path("/tmp/eira2_blueprint_staging") / str(packet["packet_id"])
    if stage.exists():
        shutil.rmtree(stage)
    payload_root = stage / "payloads"
    payload_root.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(packet["payloads"]):
        if not isinstance(item, dict):
            raise RuntimeError("payload_row_invalid")
        repo_path = safe_rel(str(item.get("repo_path") or ""))
        target_path = safe_rel(str(item.get("target_path") or ""))
        before_expected = str(item.get("before_sha256") or "").strip().lower()
        target = (root / target_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"target_outside_live:{target_path}") from exc
        if before_expected:
            if len(before_expected) != 64:
                raise RuntimeError(f"before_sha256_invalid:{target_path}")
            if not target.is_file() or sha256_file(target) != before_expected:
                raise RuntimeError(f"live_before_hash_mismatch:{target_path}")
        data = git_blob(repo, str(packet["source_commit"]), repo_path)
        staged_rel = f"payloads/{index:03d}_{Path(target_path).name}"
        staged = stage / staged_rel
        staged.write_bytes(data)
        if staged.suffix == ".py":
            check = subprocess.run([sys.executable, "-m", "py_compile", str(staged)], capture_output=True, text=True, timeout=60)
            if check.returncode != 0:
                raise RuntimeError(f"payload_python_compile_failed:{target_path}:{check.stderr[-800:]}")
        rows.append({
            "repo_path": repo_path,
            "target_path": target_path,
            "staged_path": staged_rel,
            "staged_absolute_path": str(staged),
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "before_sha256": before_expected or None,
        })
    return stage, rows


def superprobe(root: Path) -> dict[str, Any]:
    cmd = [sys.executable, str(root / "tools" / "eira2_superprobe_engine.py"), "--root", str(root)]
    result = run(cmd, root)
    report_path = root / "eira_probe" / "eira2_superprobe_report.json"
    report: dict[str, Any] = {}
    if report_path.is_file():
        try:
            raw = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                report = raw
        except Exception:
            pass
    result["report"] = report
    return result


def load_watcher(root: Path):
    path = root / "extensions" / "repair_watcher_ai" / "plugin.py"
    if not path.is_file():
        raise RuntimeError("repair_watcher_plugin_missing")
    spec = importlib.util.spec_from_file_location("eira2_live_repair_watcher", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("repair_watcher_import_spec_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def watcher_contract(path: Path) -> tuple[str, str | None, set[str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    verify = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_verify_package"), None)
    build = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_build_plan"), None)
    if verify is None:
        raise RuntimeError("watcher_verify_package_function_missing")

    filenames: list[str] = []
    required_schema: str | None = None
    keys: set[str] = set()
    for node in ast.walk(verify):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            left = node.left
            if isinstance(left, ast.Call) and isinstance(left.func, ast.Name) and left.func.id == "_inbox":
                filenames.append(node.right.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "package" and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.add(node.args[0].value)
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Attribute):
            call = node.left
            if isinstance(call.func.value, ast.Name) and call.func.value.id == "package" and call.func.attr == "get" and call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value == "schema":
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        required_schema = comp.value
    if build is not None:
        for node in ast.walk(build):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "package" and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    keys.add(node.args[0].value)
    preferred = [name for name in filenames if any(token in name.casefold() for token in ("package", "builder", "repair", "request", "blueprint"))]
    selected = (preferred or filenames)
    if not selected:
        raise RuntimeError("watcher_package_filename_not_discoverable")
    if len(set(selected)) != 1:
        raise RuntimeError("watcher_package_filename_ambiguous:" + ",".join(sorted(set(selected))))
    return selected[0], required_schema, keys


def package_value(key: str, *, packet: dict[str, Any], stage: Path, rows: list[dict[str, Any]], pre_report: dict[str, Any], schema: str | None) -> Any:
    low = key.casefold()
    if key in packet:
        return packet[key]
    if low == "schema":
        return schema or "eira2_watcher_repair_package_v1"
    if "files" in low or low in {"payloads", "replacements"}:
        return rows
    if "stage" in low and "root" in low:
        return str(stage)
    if "offsystem" in low and "root" in low:
        return str(stage)
    if "tree" in low and "sha" in low:
        return pre_report.get("package_tree_sha256")
    if "evidence" in low and "fingerprint" in low:
        return pre_report.get("evidence_fingerprint") or pre_report.get("shared_evidence_fingerprint")
    if low in {"package_id", "packet_id", "request_id", "id"}:
        return packet["packet_id"]
    if low in {"apply", "eira2_only", "superprobe_evidence_verified"}:
        return True
    if "bridge" in low:
        return list(packet.get("bridges") or [])
    if "bash" in low:
        return list(packet.get("bash_blocks") or [])
    if "retire" in low:
        return list(packet.get("retire_after_acceptance") or [])
    if "source" in low and "commit" in low:
        return packet.get("source_commit")
    return None


def build_watcher_package(packet: dict[str, Any], stage: Path, rows: list[dict[str, Any]], pre_report: dict[str, Any], required_schema: str | None, keys: set[str]) -> dict[str, Any]:
    package: dict[str, Any] = {
        "schema": required_schema or "eira2_watcher_repair_package_v1",
        "packet_id": packet["packet_id"],
        "package_id": packet["packet_id"],
        "request_id": packet["packet_id"],
        "eira2_only": True,
        "apply": True,
        "offsystem_stage_root": str(stage),
        "stage_root": str(stage),
        "staging_root": str(stage),
        "source_commit": packet["source_commit"],
        "files": rows,
        "payloads": rows,
        "bridges": list(packet.get("bridges") or []),
        "bash_blocks": list(packet.get("bash_blocks") or []),
        "retire_after_acceptance": list(packet.get("retire_after_acceptance") or []),
        "superprobe_evidence_verified": True,
        "evidence_fingerprint": pre_report.get("evidence_fingerprint") or pre_report.get("shared_evidence_fingerprint"),
        "package_tree_sha256": pre_report.get("package_tree_sha256"),
    }
    for key in keys:
        if key not in package:
            value = package_value(key, packet=packet, stage=stage, rows=rows, pre_report=pre_report, schema=required_schema)
            if value is not None:
                package[key] = value
    return package


def call_watcher_deploy(watcher: Any, package: dict[str, Any], package_path: Path) -> Any:
    deploy = getattr(watcher, "deploy_builder_probe", None)
    if not callable(deploy):
        raise RuntimeError("watcher_deploy_builder_probe_missing")
    signature = inspect.signature(deploy)
    required = [p for p in signature.parameters.values() if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if not required:
        return deploy()
    if len(required) == 1:
        name = required[0].name.casefold()
        if "path" in name or "file" in name:
            return deploy(package_path)
        return deploy(package)
    raise RuntimeError("watcher_deploy_signature_unsupported:" + str(signature))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--source-repo-root", required=True)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    packet_path = Path(args.packet).expanduser().resolve()
    source_repo = Path(args.source_repo_root).expanduser().resolve()
    receipts = root / "eira_probe" / "blueprint_receipts"
    receipts.mkdir(parents=True, exist_ok=True)

    packet = load_packet(packet_path)
    packet_id = str(packet["packet_id"])
    lane_receipt = receipts / f"{packet_id}.lane_v2.json"
    stage: Path | None = None
    package_path: Path | None = None
    try:
        if not root.is_dir():
            raise RuntimeError("eira_root_missing")
        if not (root / "tools" / "eira2_superprobe_engine.py").is_file():
            raise RuntimeError("superprobe_engine_missing")
        if not (root / "tools" / "eira2_builder_probe.py").is_file():
            raise RuntimeError("builder_probe_missing")

        stage, rows = materialize(root, packet, source_repo)
        pre = superprobe(root)
        if pre["returncode"] != 0 or pre["report"].get("ok") is not True:
            raise RuntimeError("superprobe_preflight_failed")

        watcher, watcher_path = load_watcher(root)
        inbox_func = getattr(watcher, "_inbox", None)
        if not callable(inbox_func):
            raise RuntimeError("watcher_inbox_authority_missing")
        inbox = Path(inbox_func()).expanduser().resolve()
        inbox.mkdir(parents=True, exist_ok=True)
        filename, required_schema, keys = watcher_contract(watcher_path)
        package_path = inbox / filename
        if package_path.exists():
            raise RuntimeError(f"watcher_inbox_busy:{package_path}")
        package = build_watcher_package(packet, stage, rows, pre["report"], required_schema, keys)
        atomic_json(package_path, package)

        watcher_result = call_watcher_deploy(watcher, package, package_path)
        post = superprobe(root)
        builder_receipt_path = root / "eira_probe" / "eira2_builder_receipt.json"
        builder_receipt: dict[str, Any] = {}
        if builder_receipt_path.is_file():
            try:
                raw = json.loads(builder_receipt_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    builder_receipt = raw
            except Exception:
                pass
        accepted = bool(post["returncode"] == 0 and post["report"].get("ok") is True and builder_receipt.get("ok") is True)
        result = {
            "schema": "eira2_blueprint_lane_v2_receipt",
            "packet_id": packet_id,
            "status": "accepted" if accepted else "failed_postflight",
            "watcher_delegated": True,
            "watcher_plugin": str(watcher_path),
            "watcher_package": str(package_path),
            "watcher_result": watcher_result if isinstance(watcher_result, (dict, list, str, int, float, bool, type(None))) else repr(watcher_result),
            "payloads": rows,
            "preflight": pre,
            "builder_receipt": builder_receipt,
            "postflight": post,
            "generated_unix": time.time(),
        }
        atomic_json(lane_receipt, result)
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V2": "PASS" if accepted else "FAIL", "packet_id": packet_id, "receipt": str(lane_receipt)}, indent=2))
        return 0 if accepted else 3
    except Exception as exc:
        atomic_json(lane_receipt, {
            "schema": "eira2_blueprint_lane_v2_receipt",
            "packet_id": packet_id,
            "status": "rejected_or_failed",
            "error": f"{type(exc).__name__}:{exc}"[:1600],
            "watcher_delegated": True,
            "live_write_authority_used": False,
            "generated_unix": time.time(),
        })
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V2": "FAIL", "packet_id": packet_id, "error": f"{type(exc).__name__}:{exc}"[:1200]}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
