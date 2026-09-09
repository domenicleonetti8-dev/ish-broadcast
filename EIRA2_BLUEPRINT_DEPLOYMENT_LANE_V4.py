#!/usr/bin/env python3
from __future__ import annotations

import argparse, ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

SCHEMA="eira2_builder_blueprint_v2"
PACKET_ID=re.compile(r"^[A-Za-z0-9._-]{1,96}$")
PACKAGE_SCHEMA="eira2_offsystem_surgery_package_v2"
INDEX_SCHEMA="eira2_offsystem_file_index_v2"
SUPERPROBE_SCHEMA="eira2_superprobe_forensic_v4"


def sha256_bytes(data:bytes)->str: return hashlib.sha256(data).hexdigest()
def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def atomic_json(path:Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def safe_rel(value:str)->str:
    p=Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts: raise RuntimeError(f"unsafe_relative_path:{value}")
    return p.as_posix()

def load_packet(path:Path)->dict[str,Any]:
    packet=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(packet,dict) or packet.get("schema")!=SCHEMA: raise RuntimeError("blueprint_schema_mismatch")
    pid=str(packet.get("packet_id") or "")
    if not PACKET_ID.fullmatch(pid): raise RuntimeError("invalid_packet_id")
    if packet.get("apply") is not True: raise RuntimeError("blueprint_apply_not_true")
    if not isinstance(packet.get("payloads"),list) or not packet["payloads"]: raise RuntimeError("payloads_missing")
    commit=str(packet.get("source_commit") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}",commit): raise RuntimeError("source_commit_invalid")
    return packet

def git_blob(repo:Path,commit:str,repo_path:str)->bytes:
    rel=safe_rel(repo_path)
    p=subprocess.run(["git","-C",str(repo),"show",f"{commit}:{rel}"],capture_output=True,timeout=120,check=False)
    if p.returncode: raise RuntimeError(f"source_blob_missing:{rel}:{p.stderr[-500:].decode(errors='replace')}")
    return p.stdout

def load_watcher(root:Path):
    path=root/"extensions"/"repair_watcher_ai"/"plugin.py"
    spec=importlib.util.spec_from_file_location("eira2_live_repair_watcher_v5",path)
    if spec is None or spec.loader is None: raise RuntimeError("repair_watcher_import_failed")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod,path

def prepare_watcher_inbox(root:Path,repo:Path,packet:dict[str,Any],watcher:Any):
    inbox_fn=getattr(watcher,"_inbox",None)
    if not callable(inbox_fn): raise RuntimeError("watcher_inbox_missing")
    inbox=Path(inbox_fn()).expanduser().resolve(); stage=inbox/"stage"; inbox.mkdir(parents=True,exist_ok=True)
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(parents=True,exist_ok=False); rows=[]; targets=[]
    for i,item in enumerate(packet["payloads"]):
        repo_path=safe_rel(str(item.get("repo_path") or "")); target_path=safe_rel(str(item.get("target_path") or "")); before=str(item.get("before_sha256") or "").strip().lower()
        target=(root/target_path).resolve(); target.relative_to(root)
        if before and (not target.is_file() or sha256_file(target)!=before): raise RuntimeError(f"live_before_hash_mismatch:{target_path}")
        data=git_blob(repo,str(packet["source_commit"]),repo_path); staged_rel=f"{i:03d}_{Path(target_path).name}"; staged=stage/staged_rel; staged.write_bytes(data)
        if target_path.endswith(".py"):
            q=subprocess.run([sys.executable,"-m","py_compile",str(staged)],capture_output=True,text=True,timeout=60)
            if q.returncode: raise RuntimeError(f"payload_python_compile_failed:{target_path}:{q.stderr[-800:]}")
        rows.append({"target_path":target_path,"staged_path":staged_rel,"sha256":sha256_bytes(data)}); targets.append(target_path)
    index={"schema":INDEX_SCHEMA,"files":rows}; index_path=inbox/"file_index.json"; atomic_json(index_path,index)
    core={"schema":PACKAGE_SCHEMA,"built_off_live":True,"writes_live":False,"eira2_only":True,"targets":targets,"file_index_sha256":sha256_file(index_path),"source_commit_sha":str(packet["source_commit"])}
    package=dict(core); package["package_fingerprint_sha256"]=sha256_bytes(json.dumps(core,sort_keys=True,separators=(",",":")).encode()); atomic_json(inbox/"surgery_package.json",package)
    return inbox,package,index

def discover_builder_schema(root:Path)->str:
    path=root/"tools"/"eira2_builder_probe.py"; tree=ast.parse(path.read_text(encoding="utf-8")); constants={}
    for node in tree.body:
        if isinstance(node,(ast.Assign,ast.AnnAssign)) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t,ast.Name): constants[t.id]=node.value.value
    def resolve(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,str): return node.value
        if isinstance(node,ast.Name): return constants.get(node.id)
    for node in ast.walk(tree):
        if not isinstance(node,ast.Compare): continue
        parts=[node.left,*node.comparators]
        for i,part in enumerate(parts):
            if isinstance(part,ast.Call) and isinstance(part.func,ast.Attribute) and part.func.attr=="get" and isinstance(part.func.value,ast.Name) and part.func.value.id=="plan" and part.args and isinstance(part.args[0],ast.Constant) and part.args[0].value=="schema":
                for j,other in enumerate(parts):
                    if j!=i:
                        value=resolve(other)
                        if value: return value
    raise RuntimeError("builder_plan_schema_not_discoverable")

def adapt_plan(root:Path,inspect_result:dict[str,Any],inbox:Path,packet_id:str):
    if inspect_result.get("ok") is not True: raise RuntimeError("watcher_plan_rejected:"+json.dumps(inspect_result,sort_keys=True)[-1200:])
    plan_path=Path(str(inspect_result.get("builder_plan") or root/"eira_probe"/"eira2_builder_plan.json")).resolve(); plan=json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("authorized_by")!="repair_watcher_ai": raise RuntimeError("watcher_authorization_missing")
    before=str(plan.get("schema") or ""); accepted=discover_builder_schema(root); live_stage=(inbox/"stage").resolve(); off_stage=Path("/tmp/eira2_builder_stage")/packet_id
    if off_stage.exists(): shutil.rmtree(off_stage)
    shutil.copytree(live_stage,off_stage)
    for row in plan.get("files") or []:
        rel=safe_rel(str(row.get("staged_path") or "")); expected=str(row.get("sha256") or ""); copied=(off_stage/rel).resolve(); copied.relative_to(off_stage.resolve())
        if not copied.is_file() or sha256_file(copied)!=expected: raise RuntimeError(f"off_live_stage_hash_mismatch:{rel}")
    plan["schema"]=accepted; plan["offsystem_stage_root"]=str(off_stage.resolve()); atomic_json(plan_path,plan)
    return plan_path,before,accepted,str(off_stage.resolve())

def run_builder(root:Path,plan_path:Path)->dict[str,Any]:
    receipt=root/"eira_probe"/"eira2_builder_receipt.json"
    p=subprocess.run([sys.executable,str(root/"tools"/"eira2_builder_probe.py"),"--root",str(root),"--plan",str(plan_path),"--receipt",str(receipt)],cwd=str(root),capture_output=True,text=True,timeout=600)
    combo=(p.stdout or "")+"\n"+(p.stderr or ""); payload=json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else {}
    if p.returncode or "EIRA2_BUILDER_PROBE=PASS" not in combo or payload.get("ok") is not True: raise RuntimeError("builder_failed:"+combo[-1800:])
    return payload

def exact_verify(root:Path,index:dict[str,Any])->dict[str,Any]:
    rows=[]
    for row in index["files"]:
        target=(root/row["target_path"]).resolve(); target.relative_to(root); actual=sha256_file(target) if target.is_file() else ""; ok=actual==row["sha256"]
        rows.append({"target_path":row["target_path"],"expected_sha256":row["sha256"],"actual_sha256":actual,"ok":ok})
    return {"ok":all(r["ok"] for r in rows),"files":rows}

def run_superprobe_bounded(root:Path)->dict[str,Any]:
    try:
        p=subprocess.run([sys.executable,str(root/"tools"/"eira2_superprobe_engine.py"),"--root",str(root),"--json"],cwd=str(root),capture_output=True,text=True,timeout=120)
        report_path=root/"eira_probe"/"eira2_superprobe_report.json"; report=json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        return {"completed":True,"returncode":p.returncode,"pass_marker":"EIRA2_SUPERPROBE=PASS" in ((p.stdout or "")+(p.stderr or "")),"schema":report.get("schema"),"ok":report.get("ok"),"tail":((p.stdout or "")+(p.stderr or ""))[-1200:]}
    except subprocess.TimeoutExpired:
        return {"completed":False,"timeout_seconds":120,"ok":False,"degraded":True,"reason":"superprobe_timeout_exact_target_verification_preserved"}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); ap.add_argument("--packet",required=True); ap.add_argument("--source-repo-root",required=True); a=ap.parse_args()
    root=Path(a.root).resolve(); packet_path=Path(a.packet).resolve(); repo=Path(a.source_repo_root).resolve(); packet=load_packet(packet_path); pid=str(packet["packet_id"])
    receipt_path=root/"eira_probe"/"blueprint_receipts"/f"{pid}.lane_v4.json"; backup_root=root/"eira_probe"/"transport_lane_backups"/pid; backup_root.mkdir(parents=True,exist_ok=True); backups=[]
    try:
        watcher,watcher_path=load_watcher(root); inbox,package,index=prepare_watcher_inbox(root,repo,packet,watcher)
        for row in index["files"]:
            target=(root/row["target_path"]).resolve(); backup=backup_root/row["target_path"]; backup.parent.mkdir(parents=True,exist_ok=True)
            if target.is_file(): shutil.copy2(target,backup); backups.append((target,backup))
        inspect=watcher.inspect_once(); plan_path,watcher_schema,builder_schema,off_stage=adapt_plan(root,inspect,inbox,pid); builder_receipt=run_builder(root,plan_path); verification=exact_verify(root,index)
        if not verification["ok"]: raise RuntimeError("exact_target_verification_failed:"+json.dumps(verification)[-1200:])
        probe=run_superprobe_bounded(root)
        receipt={"schema":"eira2_blueprint_lane_v4_receipt","packet_id":pid,"status":"accepted","watcher_authorized":True,"watcher_plugin":str(watcher_path),"watcher_plan_schema_original":watcher_schema,"builder_plan_schema_accepted":builder_schema,"builder_direct":True,"off_live_builder_stage":off_stage,"builder_receipt":builder_receipt,"exact_target_verification":verification,"superprobe_bounded":probe,"superprobe_required_for_write":False,"package_fingerprint_sha256":package["package_fingerprint_sha256"],"generated_unix":time.time()}
        atomic_json(receipt_path,receipt); print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"PASS","packet_id":pid,"status":"accepted","exact_target_verification":True,"superprobe":probe},indent=2)); return 0
    except Exception as exc:
        rolled=False
        for target,backup in backups:
            if backup.is_file(): target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(backup,target); rolled=True
        error=f"{type(exc).__name__}:{exc}"[:3600]; atomic_json(receipt_path,{"schema":"eira2_blueprint_lane_v4_receipt","packet_id":pid,"status":"rejected_or_failed","rollback_performed":rolled,"error":error,"generated_unix":time.time()}); print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"FAIL","packet_id":pid,"rollback_performed":rolled,"error":error},indent=2),file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
