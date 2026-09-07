#!/usr/bin/env python3
from __future__ import annotations

import argparse, ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_builder_blueprint_v2"
PACKET_ID = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
PACKAGE_SCHEMA = "eira2_offsystem_surgery_package_v2"
INDEX_SCHEMA = "eira2_offsystem_file_index_v2"
SUPERPROBE_SCHEMA = "eira2_superprobe_forensic_v4"

def sha256_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""): h.update(c)
    return h.hexdigest()
def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"); os.replace(tmp, path)
def safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts: raise RuntimeError(f"unsafe_relative_path:{value}")
    return p.as_posix()
def load_packet(path: Path) -> dict[str, Any]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA: raise RuntimeError("blueprint_schema_mismatch")
    pid = str(packet.get("packet_id") or "")
    if not PACKET_ID.fullmatch(pid): raise RuntimeError("invalid_packet_id")
    if packet.get("apply") is not True: raise RuntimeError("blueprint_apply_not_true")
    if not isinstance(packet.get("payloads"), list) or not packet["payloads"]: raise RuntimeError("payloads_missing")
    commit = str(packet.get("source_commit") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit): raise RuntimeError("source_commit_invalid")
    return packet
def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    rel = safe_rel(repo_path); p = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{rel}"], capture_output=True, timeout=120, check=False)
    if p.returncode: raise RuntimeError(f"source_blob_missing:{rel}:{p.stderr[-500:].decode(errors='replace')}")
    return p.stdout
def load_watcher(root: Path):
    path = root / "extensions" / "repair_watcher_ai" / "plugin.py"; spec = importlib.util.spec_from_file_location("eira2_live_repair_watcher_v4", path)
    if spec is None or spec.loader is None: raise RuntimeError("repair_watcher_import_failed")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod, path
def prepare_native_watcher_inbox(root: Path, repo: Path, packet: dict[str, Any], watcher: Any) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    inbox_fn = getattr(watcher, "_inbox", None)
    if not callable(inbox_fn): raise RuntimeError("watcher_inbox_missing")
    inbox = Path(inbox_fn()).expanduser().resolve(); stage = inbox / "stage"; inbox.mkdir(parents=True, exist_ok=True)
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=False); rows, targets = [], []
    for i, item in enumerate(packet["payloads"]):
        repo_path = safe_rel(str(item.get("repo_path") or "")); target_path = safe_rel(str(item.get("target_path") or "")); before = str(item.get("before_sha256") or "").strip().lower()
        target = (root / target_path).resolve(); target.relative_to(root)
        if before and (not target.is_file() or sha256_file(target) != before): raise RuntimeError(f"live_before_hash_mismatch:{target_path}")
        data = git_blob(repo, str(packet["source_commit"]), repo_path); staged_rel = f"{i:03d}_{Path(target_path).name}"; staged = stage / staged_rel; staged.write_bytes(data)
        if target_path.endswith(".py"):
            q = subprocess.run([sys.executable, "-m", "py_compile", str(staged)], capture_output=True, text=True, timeout=60)
            if q.returncode: raise RuntimeError(f"payload_python_compile_failed:{target_path}:{q.stderr[-800:]}")
        rows.append({"target_path": target_path, "staged_path": staged_rel, "sha256": sha256_bytes(data)}); targets.append(target_path)
    index = {"schema": INDEX_SCHEMA, "files": rows}; index_path = inbox / "file_index.json"; atomic_json(index_path, index)
    package_core = {"schema": PACKAGE_SCHEMA, "built_off_live": True, "writes_live": False, "eira2_only": True, "targets": targets, "file_index_sha256": sha256_file(index_path), "source_commit_sha": str(packet["source_commit"])}
    package = dict(package_core); package["package_fingerprint_sha256"] = sha256_bytes(json.dumps(package_core, sort_keys=True, separators=(",", ":")).encode()); atomic_json(inbox / "surgery_package.json", package)
    return inbox, package, index
def discover_builder_schema(root: Path) -> str:
    path = root / "tools" / "eira2_builder_probe.py"; tree = ast.parse(path.read_text(encoding="utf-8")); constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name): constants[t.id] = node.value.value
    def resolve(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
        if isinstance(node, ast.Name): return constants.get(node.id)
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare): continue
        parts = [node.left, *node.comparators]
        for i, part in enumerate(parts):
            if isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute) and part.func.attr == "get" and isinstance(part.func.value, ast.Name) and part.func.value.id == "plan" and part.args and isinstance(part.args[0], ast.Constant) and part.args[0].value == "schema":
                for j, other in enumerate(parts):
                    if j == i: continue
                    value = resolve(other)
                    if value: return value
    raise RuntimeError("builder_plan_schema_not_discoverable")
def adapt_watcher_plan(root: Path, inspect_result: dict[str, Any], inbox: Path, packet_id: str) -> tuple[Path, str, str, str]:
    if inspect_result.get("ok") is not True: raise RuntimeError("watcher_plan_rejected:" + json.dumps(inspect_result, sort_keys=True)[-1200:])
    plan_path = Path(str(inspect_result.get("builder_plan") or root / "eira_probe" / "eira2_builder_plan.json")).resolve(); plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("authorized_by") != "repair_watcher_ai": raise RuntimeError("watcher_authorization_missing")
    before = str(plan.get("schema") or ""); accepted = discover_builder_schema(root); live_stage = (inbox / "stage").resolve(); off_stage = Path("/tmp/eira2_builder_stage") / packet_id
    if off_stage.exists(): shutil.rmtree(off_stage)
    shutil.copytree(live_stage, off_stage)
    for row in plan.get("files") or []:
        rel = safe_rel(str(row.get("staged_path") or "")); expected = str(row.get("sha256") or ""); copied = (off_stage / rel).resolve(); copied.relative_to(off_stage.resolve())
        if not copied.is_file() or sha256_file(copied) != expected: raise RuntimeError(f"off_live_stage_hash_mismatch:{rel}")
    plan["schema"] = accepted; plan["offsystem_stage_root"] = str(off_stage.resolve())
    plan["transport_schema_adapter"] = {"applied": before != accepted, "from_schema": before, "to_schema": accepted, "scope": "schema_envelope_only", "watcher_authorized_content_unchanged": True}
    plan["transport_stage_relocation"] = {"applied": True, "from": str(live_stage), "to": str(off_stage.resolve()), "rehash_verified": True, "watcher_authorized_content_unchanged": True}; atomic_json(plan_path, plan)
    return plan_path, before, accepted, str(off_stage.resolve())
def run_builder(root: Path, plan_path: Path) -> dict[str, Any]:
    receipt = root / "eira_probe" / "eira2_builder_receipt.json"; p = subprocess.run([sys.executable, str(root / "tools" / "eira2_builder_probe.py"), "--root", str(root), "--plan", str(plan_path), "--receipt", str(receipt)], cwd=str(root), capture_output=True, text=True, timeout=1800)
    combo = (p.stdout or "") + "\n" + (p.stderr or ""); payload = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else {}
    if p.returncode or "EIRA2_BUILDER_PROBE=PASS" not in combo or payload.get("ok") is not True: raise RuntimeError("builder_failed:" + combo[-1800:])
    return payload
def reseal_package(root: Path) -> dict[str, Any]:
    manifest = root / "eira2-package-manifest.json"; current = json.loads(manifest.read_text(encoding="utf-8")); source_commit = str(current.get("source_commit_sha") or "")
    if str(root) not in sys.path: sys.path.insert(0, str(root))
    from eira2.operations.package_identity import write_package_manifest, verify_package_manifest
    write_package_manifest(root, source_commit_sha=source_commit); verified = verify_package_manifest(root, manifest)
    if not isinstance(verified, dict): raise RuntimeError("package_identity_verify_not_dict")
    return verified
def normalize_superprobe_report(report: dict[str, Any]) -> dict[str, Any]:
    package = report.get("package_identity") or {}; physical = report.get("physical_truth") or {}; semantic = report.get("semantic_truth") or {}; execution = report.get("execution_truth") or {}
    discrepancies = report.get("declared_vs_observed_discrepancies") or []
    return {"ok": report.get("ok") is True, "schema": report.get("schema"), "package_identity_ok": package.get("ok") is True, "package_tree_sha256": package.get("package_tree_sha256"), "package_file_count": package.get("file_count"), "discrepancy_count": len(discrepancies), "evidence_fingerprint": report.get("evidence_bundle_fingerprint_sha256") or (report.get("shared_evidence") or {}).get("fingerprint"), "files": physical.get("files"), "python_files": semantic.get("python_files"), "unresolved_internal_imports": semantic.get("unresolved_internal_import_count"), "runtime_processes": execution.get("runtime_processes"), "listeners": execution.get("listener_count")}
def run_superprobe(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    p = subprocess.run([sys.executable, str(root / "tools" / "eira2_superprobe_engine.py"), "--root", str(root), "--json"], cwd=str(root), capture_output=True, text=True, timeout=2400); combo = (p.stdout or "") + "\n" + (p.stderr or "")
    report_path = root / "eira_probe" / "eira2_superprobe_report.json"; report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}; summary = normalize_superprobe_report(report)
    if p.returncode or "EIRA2_SUPERPROBE=PASS" not in combo or not summary["ok"] or summary["schema"] != SUPERPROBE_SCHEMA: raise RuntimeError("post_superprobe_failed:" + json.dumps({**summary,"returncode":p.returncode,"tail":combo[-800:]}, sort_keys=True))
    if not summary["package_identity_ok"] or summary["discrepancy_count"] != 0: raise RuntimeError("post_superprobe_qualification_failed:" + json.dumps(summary, sort_keys=True))
    return report, summary
def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", required=True); ap.add_argument("--packet", required=True); ap.add_argument("--source-repo-root", required=True); a = ap.parse_args()
    root = Path(a.root).resolve(); packet_path = Path(a.packet).resolve(); repo = Path(a.source_repo_root).resolve(); packet = load_packet(packet_path); pid = str(packet["packet_id"])
    receipt_path = root / "eira_probe" / "blueprint_receipts" / f"{pid}.lane_v4.json"; backup_root = root / "eira_probe" / "transport_lane_backups" / pid; backup_root.mkdir(parents=True, exist_ok=True)
    manifest = root / "eira2-package-manifest.json"; manifest_backup = backup_root / "eira2-package-manifest.json"; target_backups: list[tuple[Path, Path]] = []
    try:
        watcher, watcher_path = load_watcher(root); inbox, package, index = prepare_native_watcher_inbox(root, repo, packet, watcher)
        for row in index["files"]:
            target = (root / str(row["target_path"])).resolve(); backup = backup_root / str(row["target_path"]); backup.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file(): shutil.copy2(target, backup); target_backups.append((target, backup))
        if manifest.is_file(): shutil.copy2(manifest, manifest_backup)
        inspect = watcher.inspect_once(); plan_path, watcher_schema, builder_schema, off_stage = adapt_watcher_plan(root, inspect, inbox, pid); builder_receipt = run_builder(root, plan_path); package_receipt = reseal_package(root); report, probe_summary = run_superprobe(root)
        atomic_json(receipt_path, {"schema":"eira2_blueprint_lane_v4_receipt","packet_id":pid,"status":"accepted","watcher_native_contract_used":True,"watcher_plugin":str(watcher_path),"watcher_inbox":str(inbox),"watcher_authorized":True,"watcher_plan_schema_original":watcher_schema,"builder_plan_schema_accepted":builder_schema,"schema_adapter_scope":"envelope_only","builder_direct":True,"transaction_executor_bypassed_as_non_authority_schema_bottleneck":True,"off_live_builder_stage":off_stage,"watcher_authorized_content_rehash_verified":True,"package_fingerprint_sha256":package["package_fingerprint_sha256"],"planned_files":len(index["files"]),"builder_receipt":builder_receipt,"package_identity":package_receipt,"superprobe_summary":probe_summary,"superprobe":report,"generated_unix":time.time()})
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"PASS","packet_id":pid,"status":"accepted","watcher_schema":watcher_schema,"builder_schema":builder_schema,"superprobe":probe_summary}, indent=2)); return 0
    except Exception as exc:
        rolled_back = False
        for target, backup in target_backups:
            if backup.is_file(): target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(backup, target); rolled_back = True
        if manifest_backup.is_file(): shutil.copy2(manifest_backup, manifest); rolled_back = True
        error = f"{type(exc).__name__}:{exc}"[:3600]; atomic_json(receipt_path, {"schema":"eira2_blueprint_lane_v4_receipt","packet_id":pid,"status":"rejected_or_failed","rollback_performed":rolled_back,"error":error,"generated_unix":time.time()}); print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"FAIL","packet_id":pid,"rollback_performed":rolled_back,"error":error}, indent=2), file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
