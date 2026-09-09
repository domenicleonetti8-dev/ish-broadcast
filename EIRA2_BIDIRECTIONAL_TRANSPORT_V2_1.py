#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "eira2_bidirectional_transport_v2_1"
REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
DEFAULT_ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
DEFAULT_STATE = Path.home()/".local"/"state"/"eira2-transport-v2"
IN_LANES = ("requests","blueprints","jobs","builds","artifacts")
OUT_LANES = ("receipts","jobs","builds","artifacts","diagnostics")
REMOTE_IN = Path("eira2_transport_bus/to_superprobe")
REMOTE_OUT = Path("eira2_transport_bus/from_superprobe")
CONSUMER = "EIRA2_BIDIRECTIONAL_BLUEPRINT_CONSUMER_V1.py"


def utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def sha(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def atomic(p:Path,obj:Any):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f".tmp.{os.getpid()}")
    t.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(t,p)

def run(cmd:list[str],cwd:Path|None=None,timeout:int=300):
    return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)

def dirs(state:Path):
    for lane in IN_LANES: (state/"inbox"/lane).mkdir(parents=True,exist_ok=True)
    for lane in OUT_LANES: (state/"outbox"/lane).mkdir(parents=True,exist_ok=True)
    for x in ("mirror-state","publish-state","blueprint-state","runtime"): (state/x).mkdir(parents=True,exist_ok=True)

def sync_repo(state:Path)->Path:
    repo=state/"repo"
    if not (repo/".git").is_dir():
        if repo.exists(): shutil.rmtree(repo)
        p=run(["git","clone","--quiet",REPO_URL,str(repo)],timeout=600)
        if p.returncode: raise RuntimeError("git_clone_failed:"+p.stderr[-1000:])
    for cmd in (["git","fetch","--quiet","origin","master"],["git","checkout","--quiet","master"],["git","reset","--hard","origin/master"]):
        p=run(list(cmd),repo,300)
        if p.returncode: raise RuntimeError("git_sync_failed:"+p.stderr[-1000:])
    return repo

def mirror_in(repo:Path,state:Path)->dict[str,int]:
    out={}
    for lane in IN_LANES:
        n=0; src=repo/REMOTE_IN/lane; dst=state/"inbox"/lane
        if src.is_dir():
            for p in sorted(src.iterdir()):
                if not p.is_file(): continue
                d=sha(p); marker=state/"mirror-state"/f"{lane}__{d}.json"
                if marker.exists(): continue
                q=dst/p.name
                if not q.exists() or sha(q)!=d: shutil.copy2(p,q)
                atomic(marker,{"schema":SCHEMA,"lane":lane,"name":p.name,"sha256":d,"utc":utc()}); n+=1
        out[lane]=n
    return out

def publish(repo:Path, rels:list[Path], message:str)->str:
    for cmd in (["git","fetch","--quiet","origin","master"],["git","reset","--hard","origin/master"]):
        p=run(list(cmd),repo,300)
        if p.returncode: raise RuntimeError("publish_sync_failed:"+p.stderr[-1000:])
    p=run(["git","add",*[x.as_posix() for x in rels]],repo,120)
    if p.returncode: raise RuntimeError("publish_add_failed:"+p.stderr[-800:])
    if run(["git","diff","--cached","--quiet"],repo,120).returncode!=0:
        p=run(["git","-c","user.name=EIRA2 Return Transport","-c","user.email=eira2-return@localhost","commit","--quiet","-m",message],repo,120)
        if p.returncode: raise RuntimeError("publish_commit_failed:"+p.stderr[-1000:])
        p=run(["git","pull","--rebase","--quiet","origin","master"],repo,300)
        if p.returncode: raise RuntimeError("publish_rebase_failed:"+p.stderr[-1200:])
        p=run(["git","push","--quiet","origin","master"],repo,300)
        if p.returncode: raise RuntimeError("publish_push_failed:"+p.stderr[-1200:])
    return run(["git","rev-parse","HEAD"],repo,60).stdout.strip()

def publish_out(repo:Path,state:Path)->dict[str,int]:
    staged:list[tuple[str,Path,Path,str]]=[]; counts={lane:0 for lane in OUT_LANES}; rels=[]
    for lane in OUT_LANES:
        for p in sorted((state/"outbox"/lane).iterdir()):
            if not p.is_file(): continue
            d=sha(p); marker=state/"publish-state"/f"{lane}__{d}.json"
            if marker.exists(): continue
            rel=REMOTE_OUT/lane/p.name; target=repo/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target)
            rels.append(rel); staged.append((lane,p,marker,d)); counts[lane]+=1
    if rels:
        commit=publish(repo,rels,"Return EIRA2 bidirectional jobs/builds/receipts")
        for lane,p,marker,d in staged:
            atomic(marker,{"schema":SCHEMA,"lane":lane,"name":p.name,"sha256":d,"commit":commit,"published_utc":utc()})
    return counts

def mount_snapshot(root:Path)->dict[str,Any]:
    rows=[]
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8",errors="replace").splitlines():
        parts=line.split()
        if len(parts)>5:
            mp=parts[4].replace("\\040"," ")
            if str(root).startswith(mp): rows.append(line)
    return {"ok":bool(rows),"rows":rows[-8:]}

def dstates()->list[dict[str,str]]:
    p=run(["ps","-eo","pid=,stat=,comm=,wchan="],timeout=30); rows=[]
    for line in p.stdout.splitlines():
        x=line.split(None,3)
        if len(x)>=3 and x[1].startswith("D"): rows.append({"pid":x[0],"stat":x[1],"comm":x[2],"wchan":x[3] if len(x)>3 else ""})
    return rows

def admission(root:Path):
    m=mount_snapshot(root); d=dstates(); bad=[r for r in d if "ntfs" in r["wchan"].lower()]
    return bool(m["ok"] and not bad),{"mount":m,"d_state":d,"ntfs_blocked":bad}

def pending_blueprints(state:Path)->int:
    n=0
    for p in (state/"inbox"/"blueprints").glob("*.json"):
        if not (state/"blueprint-state"/f"{sha(p)}.json").exists(): n+=1
    return n

def worker_tick(repo:Path,root:Path,state:Path)->dict[str,Any]:
    rt=state/"runtime"; pf=rt/"worker.pid"
    if pf.exists():
        try:
            pid=int(pf.read_text().strip()); os.kill(pid,0); return {"state":"RUNNING","pid":pid}
        except Exception: pf.unlink(missing_ok=True)
    if pending_blueprints(state)==0: return {"state":"IDLE"}
    ok,ev=admission(root)
    if not ok: return {"state":"STORAGE_BLOCKED","evidence":ev}
    log=(rt/"worker.log").open("ab")
    p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--root",str(root),"--state",str(state),"blueprint-once"],cwd=str(Path.home()),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    pf.write_text(str(p.pid)+"\n"); atomic(rt/"worker.json",{"schema":SCHEMA,"state":"STARTED","pid":p.pid,"utc":utc()})
    return {"state":"STARTED","pid":p.pid}

def blueprint_once(root:Path,state:Path)->int:
    repo=sync_repo(state); path=repo/CONSUMER
    spec=importlib.util.spec_from_file_location("eira2_bp_v1",path); mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
    before={sha(p):p for p in (state/"inbox"/"blueprints").glob("*.json") if not (state/"blueprint-state"/f"{sha(p)}.json").exists()}
    rows=mod.process_once(root,state/"blueprint-work",state/"blueprint-state")
    # V1 writes exact digest markers for successfully handled blueprints. Keep explicit result evidence on ext4 too.
    atomic(state/"runtime"/"last_blueprint_run.json",{"schema":SCHEMA,"utc":utc(),"candidate_digests":sorted(before),"results":rows})
    return 0

def emit(state:Path,lane:str,source:Path,name:str|None):
    if lane not in OUT_LANES: raise SystemExit("invalid lane")
    if not source.is_file(): raise SystemExit("source missing")
    dst=state/"outbox"/lane/(name or source.name); shutil.copy2(source,dst)
    return {"schema":SCHEMA,"queued":True,"lane":lane,"path":str(dst),"sha256":sha(dst)}

def status(state:Path,root:Path):
    ok,ev=admission(root)
    return {"schema":SCHEMA,"utc":utc(),"control_plane":str(state),"control_plane_on_live_drive":str(state).startswith(str(root)),"live_root":str(root),"storage_admitted":ok,"storage_evidence":ev,"pending_blueprints":pending_blueprints(state),"inbox":{x:len(list((state/"inbox"/x).glob("*"))) for x in IN_LANES},"outbox":{x:len(list((state/"outbox"/x).glob("*"))) for x in OUT_LANES}}

def once(root:Path,state:Path):
    dirs(state); repo=sync_repo(state); incoming=mirror_in(repo,state); worker=worker_tick(repo,root,state); repo=sync_repo(state); outgoing=publish_out(repo,state); s=status(state,root)
    h={"schema":SCHEMA,"utc":utc(),"incoming":incoming,"worker":worker,"outgoing":outgoing,"status":s}; atomic(state/"runtime"/"heartbeat.json",h); return h

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default=str(DEFAULT_ROOT)); ap.add_argument("--state",default=str(DEFAULT_STATE)); sp=ap.add_subparsers(dest="cmd",required=True)
    sp.add_parser("once"); d=sp.add_parser("daemon"); d.add_argument("--interval",type=float,default=3.0); sp.add_parser("status"); sp.add_parser("blueprint-once")
    e=sp.add_parser("emit"); e.add_argument("lane",choices=OUT_LANES); e.add_argument("source"); e.add_argument("--name")
    a=ap.parse_args(); root=Path(a.root).expanduser(); state=Path(a.state).expanduser(); dirs(state)
    if a.cmd=="status": print(json.dumps(status(state,root),indent=2)); return 0
    if a.cmd=="emit": print(json.dumps(emit(state,a.lane,Path(a.source).expanduser(),a.name),indent=2)); return 0
    if a.cmd=="blueprint-once": return blueprint_once(root,state)
    if a.cmd=="once": print(json.dumps(once(root,state),indent=2)); return 0
    while True:
        try: print(json.dumps(once(root,state),separators=(",",":")),flush=True)
        except Exception as exc:
            atomic(state/"runtime"/"last_error.json",{"schema":SCHEMA,"utc":utc(),"error":f"{type(exc).__name__}:{exc}"}); print(f"EIRA2_TRANSPORT_V2_1_FAIL={type(exc).__name__}:{exc}",file=sys.stderr,flush=True)
        time.sleep(max(1.0,a.interval))

if __name__=="__main__": raise SystemExit(main())
