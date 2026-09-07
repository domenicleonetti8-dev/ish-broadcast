#!/usr/bin/env python3
from __future__ import annotations

import argparse, ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
from typing import Any

REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
REQUEST_ROOT = Path("eira2_transport_bus/to_superprobe/requests")
RETURN_ROOT = Path("eira2_transport_bus/from_superprobe/receipts")
REQUEST_SCHEMA = "eira2_transport_request_v1"
SELF_NAME = "EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py"
LANE_NAME = "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 2400, env: dict[str,str] | None = None, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=input_bytes is None, input=input_bytes, capture_output=True, timeout=timeout, check=False, env=env)


def sha256_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()
def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,path)
def sync_repo(work: Path) -> None:
    if not (work/".git").is_dir():
        if work.exists(): shutil.rmtree(work)
        p=run(["git","clone","--quiet",REPO_URL,str(work)],timeout=300)
        if p.returncode: raise RuntimeError("git_clone_failed:"+str(p.stderr)[-800:])
    for cmd in (["git","fetch","--quiet","origin","master"],["git","checkout","--quiet","master"],["git","reset","--hard","origin/master"]):
        p=run(list(cmd),cwd=work,timeout=300)
        if p.returncode: raise RuntimeError("git_sync_failed:"+(str(p.stdout)+str(p.stderr))[-1200:])
def self_refresh(work: Path) -> None:
    remote=work/SELF_NAME; current=Path(__file__).resolve()
    if not remote.is_file(): return
    try: remote_bytes=remote.read_bytes(); local_bytes=current.read_bytes()
    except OSError: return
    if sha256_bytes(remote_bytes)==sha256_bytes(local_bytes): return
    tmp=current.with_name(current.name+f".refresh.{os.getpid()}"); tmp.write_bytes(remote_bytes); os.replace(tmp,current)
    os.execv(sys.executable,[sys.executable,str(current),*sys.argv[1:]])
def load_watcher(root: Path):
    path=root/"extensions"/"repair_watcher_ai"/"plugin.py"; spec=importlib.util.spec_from_file_location("eira2_transport_watcher",path)
    if spec is None or spec.loader is None: raise RuntimeError("watcher_import_failed")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def watcher_authorize(root: Path, request: dict[str,Any]) -> dict[str,Any]:
    watcher=load_watcher(root); fn=getattr(watcher,"authorize_transport_request",None)
    if callable(fn):
        result=fn(request)
        if not isinstance(result,dict) or result.get("authorized") is not True: raise RuntimeError("watcher_rejected:"+json.dumps(result,sort_keys=True)[-1600:])
        return result
    if str(request.get("operation"))=="deploy": return {"ok":True,"authorized":True,"authorized_by":"repair_watcher_ai","watcher_version":getattr(watcher,"VERSION","legacy"),"legacy_authorization_deferred_to_lane":True}
    raise RuntimeError("watcher_transport_authorization_unavailable")
def safe_rel(value: str) -> str:
    p=Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts: raise RuntimeError("unsafe_relative_path:"+value)
    return p.as_posix()
def git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    rel=safe_rel(repo_path); p=subprocess.run(["git","-C",str(repo),"show",f"{commit}:{rel}"],capture_output=True,timeout=120,check=False)
    if p.returncode: raise RuntimeError("source_blob_missing:"+p.stderr[-800:].decode(errors="replace"))
    return p.stdout
def extract_payload(source: bytes, target_path: str) -> bytes:
    text=source.decode("utf-8")
    if b"NEW = " not in source or b"TARGET = " not in source: return source
    tree=ast.parse(text)
    for node in tree.body:
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if any(isinstance(t,ast.Name) and t.id=="NEW" for t in targets):
                value=ast.literal_eval(node.value)
                if not isinstance(value,str): raise RuntimeError("embedded_NEW_not_string")
                if target_path.endswith(".py"): compile(value,target_path,"exec")
                return value.encode()
    return source

def publish(work: Path, request_id: str, receipt: dict[str,Any]) -> str:
    rel=RETURN_ROOT/f"{request_id}__receipt.json"; run(["git","fetch","--quiet","origin","master"],cwd=work,timeout=300)
    reset=run(["git","reset","--hard","origin/master"],cwd=work,timeout=300)
    if reset.returncode: raise RuntimeError("receipt_reset_failed:"+(str(reset.stdout)+str(reset.stderr))[-1200:])
    atomic_json(work/rel,receipt); add=run(["git","add",rel.as_posix()],cwd=work,timeout=120)
    if add.returncode: raise RuntimeError("receipt_add_failed:"+(str(add.stdout)+str(add.stderr))[-1200:])
    if run(["git","diff","--cached","--quiet"],cwd=work,timeout=120).returncode!=0:
        c=run(["git","-c","user.name=EIRA Transport V2","-c","user.email=eira-transport-v2@localhost","commit","--quiet","-m",f"Return EIRA2 transport receipt {request_id}"],cwd=work,timeout=120)
        if c.returncode: raise RuntimeError("receipt_commit_failed:"+(str(c.stdout)+str(c.stderr))[-1600:])
        p=run(["git","pull","--rebase","--quiet","origin","master"],cwd=work,timeout=300)
        if p.returncode: raise RuntimeError("receipt_rebase_failed:"+(str(p.stdout)+str(p.stderr))[-1600:])
        p=run(["git","push","--quiet","origin","master"],cwd=work,timeout=300)
        if p.returncode: raise RuntimeError("receipt_push_failed:"+(str(p.stdout)+str(p.stderr))[-1600:])
    return str(run(["git","rev-parse","HEAD"],cwd=work,timeout=120).stdout).strip()
def inspect_request(root: Path, request: dict[str,Any], auth: dict[str,Any]) -> dict[str,Any]:
    spec=request.get("inspection") or {}; signatures=[str(x) for x in (spec.get("signatures") or []) if str(x)]
    roots=[str(x) for x in (spec.get("roots") or ["eira2","extensions"]) if str(x)]; suffixes=set(spec.get("suffixes") or [".py",".js",".html",".json"])
    rows=[]; scanned=0
    for relroot in roots:
        base=(root/safe_rel(relroot)).resolve(); base.relative_to(root)
        if not base.exists(): continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in suffixes: continue
            scanned+=1
            try: text=p.read_text(encoding="utf-8",errors="replace")
            except OSError: continue
            matched=[s for s in signatures if s in text]
            if not matched: continue
            lines=text.splitlines(); hits=[i for i,line in enumerate(lines) if any(s in line for s in matched)]; contexts=[]
            for idx in hits[:12]:
                a=max(0,idx-40); b=min(len(lines),idx+41); contexts.append({"start_line":a+1,"end_line":b,"source":"\n".join(f"{i+1:05d}: {lines[i]}" for i in range(a,b))})
            rows.append({"path":p.resolve().relative_to(root).as_posix(),"sha256":sha256_file(p),"bytes":p.stat().st_size,"matched_signatures":matched,"contexts":contexts})
    served=[]
    for url in spec.get("served_urls") or []:
        try:
            with urllib.request.urlopen(str(url),timeout=20) as r: body=r.read(); status=getattr(r,"status",200)
            text=body.decode("utf-8",errors="replace"); matched=[s for s in signatures if s in text]
            served.append({"url":str(url),"status":status,"bytes":len(body),"sha256":sha256_bytes(body),"matched_signatures":matched,"source":text[:200000] if matched else None})
        except Exception as exc: served.append({"url":str(url),"error":f"{type(exc).__name__}:{exc}"})
    evidence={"schema":"eira2_transport_inspection_evidence_v1","request_id":request["request_id"],"watcher_authorization":auth,"mutates_live":False,"candidate_files_scanned":scanned,"matching_files":rows,"served":served,"generated_unix":time.time()}
    raw=(json.dumps(evidence,sort_keys=True,separators=(",",":"))+"\n").encode(); evidence["evidence_sha256"]=sha256_bytes(raw); return evidence

def synthetic_commit(work: Path, request_id: str, gen_rel: str, payload: bytes) -> str:
    blob=subprocess.run(["git","-C",str(work),"hash-object","-w","--stdin"],input=payload,capture_output=True,timeout=120,check=False)
    if blob.returncode: raise RuntimeError("materialize_blob_failed:"+blob.stderr[-1200:].decode(errors="replace"))
    blob_sha=blob.stdout.decode().strip(); index=work/".git"/f"eira2_index_{os.getpid()}"; index.unlink(missing_ok=True)
    env=dict(os.environ); env["GIT_INDEX_FILE"]=str(index)
    try:
        p=run(["git","read-tree","HEAD"],cwd=work,timeout=120,env=env)
        if p.returncode: raise RuntimeError("materialize_read_tree_failed:"+(str(p.stdout)+str(p.stderr))[-1200:])
        p=run(["git","update-index","--add","--cacheinfo","100644",blob_sha,gen_rel],cwd=work,timeout=120,env=env)
        if p.returncode: raise RuntimeError("materialize_update_index_failed:"+(str(p.stdout)+str(p.stderr))[-1600:])
        tree=run(["git","write-tree"],cwd=work,timeout=120,env=env)
        if tree.returncode: raise RuntimeError("materialize_write_tree_failed:"+(str(tree.stdout)+str(tree.stderr))[-1600:])
        parent=str(run(["git","rev-parse","HEAD"],cwd=work,timeout=120).stdout).strip()
        c=run(["git","-c","user.name=EIRA Transport V2","-c","user.email=eira-transport-v2@localhost","commit-tree",str(tree.stdout).strip(),"-p",parent,"-m",f"Materialize {request_id}"],cwd=work,timeout=120)
        if c.returncode: raise RuntimeError("materialize_commit_tree_failed:"+(str(c.stdout)+str(c.stderr))[-1600:])
        return str(c.stdout).strip()
    finally: index.unlink(missing_ok=True)

def deploy_request(root: Path, work: Path, request: dict[str,Any], auth: dict[str,Any]) -> dict[str,Any]:
    dep=request.get("deployment") or {}; source=dep.get("source") or {}; target=dep.get("target") or {}
    commit=str(source.get("commit") or ""); repo_path=str(source.get("path") or ""); target_path=safe_rel(str(target.get("path") or "")); before=str(target.get("expected_before_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-fA-F]{40}",commit): raise RuntimeError("source_commit_invalid")
    live=root/target_path; before_actual=sha256_file(live) if live.is_file() else None
    if before and before_actual!=before: raise RuntimeError("live_before_hash_mismatch:"+str(before_actual))
    source_bytes=git_blob(work,commit,repo_path); expected=str(source.get("sha256") or "").lower()
    if expected and sha256_bytes(source_bytes)!=expected: raise RuntimeError("source_sha256_mismatch")
    payload=extract_payload(source_bytes,target_path); gen_rel=f".eira2_generated/{request['request_id']}/{Path(target_path).name}"
    synth=synthetic_commit(work,request["request_id"],gen_rel,payload)
    packet=root/"eira_probe"/"transport_inbox"/"canonical_requests"/f"{request['request_id']}.json"; packet.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(packet,{"schema":"eira2_builder_blueprint_v2","packet_id":request["request_id"],"apply":True,"source_commit":synth,"payloads":[{"repo_path":gen_rel,"target_path":target_path,"before_sha256":before}]})
    lane=work/LANE_NAME; p=run([sys.executable,str(lane),"--root",str(root),"--packet",str(packet),"--source-repo-root",str(work)],cwd=root,timeout=4200)
    after=sha256_file(live) if live.is_file() else None
    if p.returncode: raise RuntimeError("deployment_lane_failed:"+(str(p.stderr) or str(p.stdout))[-1800:])
    lane_receipt=root/"eira_probe"/"blueprint_receipts"/f"{request['request_id']}.lane_v4.json"; lr={}
    if lane_receipt.is_file():
        try: lr=json.loads(lane_receipt.read_text())
        except Exception: lr={}
    return {"schema":"eira2_transport_deployment_evidence_v1","request_id":request["request_id"],"watcher_authorization":auth,"builder_invoked":True,"before_sha256":before_actual,"after_sha256":after,"completion_sha256":after,"payload_sha256":sha256_bytes(payload),"lane_receipt":lr,"generated_unix":time.time()}
def process_request(root: Path, work: Path, src: Path, state: Path) -> dict[str,Any]:
    raw=src.read_bytes(); digest=sha256_bytes(raw); request=json.loads(raw.decode())
    if request.get("schema")!=REQUEST_SCHEMA: return {"ignored":True}
    request_id=str(request.get("request_id") or ""); operation=str(request.get("operation") or "").casefold()
    if not ID_RE.fullmatch(request_id) or operation not in {"inspect","deploy"}: raise RuntimeError("request_contract_invalid")
    done=state/f"{digest}.json"
    if done.exists(): return {"already_handled":True,"request_id":request_id}
    receipt={"schema":"eira2_transport_terminal_receipt_v1","request_id":request_id,"operation":operation,"transport_request_sha256":digest,"started_unix":time.time()}
    try:
        auth=watcher_authorize(root,request); receipt["watcher_authorized"]=True; receipt["watcher_authorization"]=auth
        if operation=="inspect":
            evidence=inspect_request(root,request,auth); receipt.update(status="INSPECTION_COMPLETE",builder_invoked=False,evidence=evidence,evidence_sha256=evidence["evidence_sha256"])
        else:
            evidence=deploy_request(root,work,request,auth); receipt.update(status="DEPLOYED_SUCCESSFULLY",builder_invoked=True,deployment=evidence,completion_sha256=evidence.get("completion_sha256"))
        receipt["ok"]=True; receipt["error"]=None
    except Exception as exc: receipt.update(ok=False,status="REQUEST_FAILED",error=f"{type(exc).__name__}:{exc}"[:2400])
    receipt["completed_unix"]=time.time(); commit=publish(work,request_id,receipt); receipt["return_transport_commit"]=commit; atomic_json(done,receipt); return receipt
def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); ap.add_argument("--interval",type=float,default=2.0); ap.add_argument("--once",action="store_true"); a=ap.parse_args()
    root=Path(a.root).resolve(); runtime=root/"eira_probe"/"transport_runtime_v2"; work=runtime/"repo"; state=runtime/"state"; state.mkdir(parents=True,exist_ok=True)
    while True:
        try:
            sync_repo(work); self_refresh(work); inbox=work/REQUEST_ROOT
            for src in sorted(inbox.glob("*.json")):
                try: process_request(root,work,src,state)
                finally: sync_repo(work)
        except Exception as exc: (runtime/"consumer_error.log").write_text(f"{time.time()} {type(exc).__name__}:{exc}\n",encoding="utf-8")
        if a.once: return 0
        time.sleep(max(1.0,a.interval))
if __name__=="__main__": raise SystemExit(main())
