#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, socket, subprocess, sys, time
from pathlib import Path
from typing import Any

CORE_COMMIT="f61240000d4fd3eb8ddab7ff6800c5555f501490"
CORE_PATH="EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
FRONTEND_PROBE_PATH="EIRA2_REVAMP2_FRONTEND_ACCEPTANCE_PROBE_V1.py"

def run(cmd:list[str],*,cwd:Path,timeout:int=2400)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=str(cwd),text=True,capture_output=True,timeout=timeout,check=False)

def atomic_json(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,path)

def port_open(port:int=8782)->bool:
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=1): return True
    except OSError: return False

def launch_attempt(root:Path,name:str,cmd:list[str],port:int=8782,wait:int=30)->dict[str,Any]:
    log_path=root/"eira_probe"/f"canonical_live_restart_{name}.log"; log_path.parent.mkdir(parents=True,exist_ok=True)
    log=log_path.open("ab",buffering=0)
    try:
        child=subprocess.Popen(cmd,cwd=str(root),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    finally: log.close()
    deadline=time.time()+wait
    while time.time()<deadline:
        if port_open(port):
            tail=log_path.read_text(encoding="utf-8",errors="replace")[-2400:] if log_path.is_file() else ""
            return {"name":name,"cmd":cmd,"pid":child.pid,"bound":True,"exit_code":child.poll(),"log_path":str(log_path),"log_tail":tail}
        code=child.poll()
        if code is not None:
            tail=log_path.read_text(encoding="utf-8",errors="replace")[-2400:] if log_path.is_file() else ""
            return {"name":name,"cmd":cmd,"pid":child.pid,"bound":False,"exit_code":code,"log_path":str(log_path),"log_tail":tail}
        time.sleep(1)
    tail=log_path.read_text(encoding="utf-8",errors="replace")[-2400:] if log_path.is_file() else ""
    return {"name":name,"cmd":cmd,"pid":child.pid,"bound":port_open(port),"exit_code":child.poll(),"log_path":str(log_path),"log_tail":tail}

def ensure_runtime(root:Path,port:int=8782)->dict[str,Any]:
    if port_open(port): return {"schema":"eira2_canonical_runtime_ensure_v3","ok":True,"listener_before":True,"listener_after":True,"attempts":[]}
    attempts=[]
    candidates=[
        ("main_py",[sys.executable,str(root/"main.py")],20),
        ("module_live_root",[sys.executable,"-m","eira2","--live","--root",str(root)],30),
        ("module_live_cwd",[sys.executable,"-m","eira2","--live"],30),
    ]
    for name,cmd,wait in candidates:
        if name=="main_py" and not (root/"main.py").is_file():
            attempts.append({"name":name,"cmd":cmd,"bound":False,"error":"main_py_missing"}); continue
        row=launch_attempt(root,name,cmd,port,wait); attempts.append(row)
        if row.get("bound"):
            return {"schema":"eira2_canonical_runtime_ensure_v3","ok":True,"listener_before":False,"listener_after":True,"successful_attempt":name,"attempts":attempts}
    return {"schema":"eira2_canonical_runtime_ensure_v3","ok":False,"listener_before":False,"listener_after":False,"error":"all_canonical_launch_attempts_failed","attempts":attempts}

def post_json(url:str,payload:dict[str,Any],timeout:int=120)->dict[str,Any]:
    import urllib.request, urllib.error
    raw=json.dumps(payload).encode(); req=urllib.request.Request(url,data=raw,headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            body=r.read().decode("utf-8",errors="replace")
            try: parsed=json.loads(body)
            except Exception: parsed=body
            return {"ok":r.status==200,"status":int(r.status),"body":parsed}
    except Exception as exc: return {"ok":False,"error":f"{type(exc).__name__}:{exc}"[:1200]}

def live_acceptance(port:int=8782)->dict[str,Any]:
    text=post_json(f"http://127.0.0.1:{port}/v1/text",{"text":"How are you?","source":"deep_acceptance"}) if port_open(port) else {"ok":False,"error":"port_closed"}
    return {"schema":"eira2_live_http_acceptance_v3","text":text,"runtime_acceptance_ok":bool(text.get("ok"))}

def frontend_acceptance(root:Path,repo:Path,port:int=8782)->dict[str,Any]:
    probe=Path("/tmp")/f"eira2_revamp2_acceptance_{os.getpid()}.py"; out=root/"eira_probe"/"revamp2_frontend_acceptance.json"
    show=subprocess.run(["git","-C",str(repo),"show",f"origin/master:{FRONTEND_PROBE_PATH}"],capture_output=True,timeout=120,check=False)
    if show.returncode: return {"ok":False,"error":"frontend_probe_fetch_failed:"+show.stderr[-600:].decode(errors="replace")}
    probe.write_bytes(show.stdout)
    try: p=run([sys.executable,str(probe),"--base",f"http://127.0.0.1:{port}/","--out",str(out)],cwd=root,timeout=180)
    finally:
        try: probe.unlink()
        except OSError: pass
    payload={}
    if out.is_file():
        try: payload=json.loads(out.read_text(encoding="utf-8"))
        except Exception: payload={}
    return {"probe_returncode":p.returncode,"stdout":p.stdout[-1000:],"stderr":p.stderr[-1000:],**payload}

def publish_acceptance(repo:Path,packet_id:str,payload:dict[str,Any])->str:
    rel=Path("eira2_transport_bus/from_superprobe/acceptance")/f"{packet_id}.json"
    run(["git","reset","--hard","origin/master"],cwd=repo,timeout=300)
    atomic_json(repo/rel,payload); run(["git","add",rel.as_posix()],cwd=repo,timeout=120)
    if run(["git","diff","--cached","--quiet"],cwd=repo,timeout=120).returncode!=0:
        c=run(["git","-c","user.name=EIRA Acceptance Transport","-c","user.email=eira-acceptance@localhost","commit","--quiet","-m",f"Return EIRA2 acceptance {packet_id}"],cwd=repo,timeout=120)
        if c.returncode: raise RuntimeError("acceptance_commit_failed:"+c.stderr[-800:])
        p=run(["git","pull","--rebase","--quiet","origin","master"],cwd=repo,timeout=300)
        if p.returncode: raise RuntimeError("acceptance_rebase_failed:"+p.stderr[-800:])
        p=run(["git","push","--quiet","origin","master"],cwd=repo,timeout=300)
        if p.returncode: raise RuntimeError("acceptance_push_failed:"+p.stderr[-800:])
    return run(["git","rev-parse","HEAD"],cwd=repo,timeout=120).stdout.strip()

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); ap.add_argument("--packet",required=True); ap.add_argument("--source-repo-root",required=True); a=ap.parse_args()
    root=Path(a.root).resolve(); repo=Path(a.source_repo_root).resolve(); packet=Path(a.packet).resolve(); data=json.loads(packet.read_text(encoding="utf-8")); packet_id=str(data.get("packet_id") or "")
    core=Path("/tmp")/f"eira2_lane_core_{os.getpid()}.py"; show=subprocess.run(["git","-C",str(repo),"show",f"{CORE_COMMIT}:{CORE_PATH}"],capture_output=True,timeout=120,check=False)
    if show.returncode: print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"FAIL","error":"core_fetch_failed"}),file=sys.stderr); return 2
    core.write_bytes(show.stdout); proc=run([sys.executable,str(core),"--root",str(root),"--packet",str(packet),"--source-repo-root",str(repo)],cwd=root,timeout=3600)
    try: core.unlink()
    except OSError: pass
    combo=(proc.stdout or "")+"\n"+(proc.stderr or "")
    if proc.returncode or "PASS" not in combo: sys.stderr.write(proc.stderr or proc.stdout); return proc.returncode or 2
    runtime=ensure_runtime(root); live=live_acceptance(); frontend=frontend_acceptance(root,repo)
    payload={"schema":"eira2_live_acceptance_return_v3","packet_id":packet_id,"completed_unix":time.time(),"package_and_superprobe_qualified":True,"canonical_runtime_ensure":runtime,"live_http_acceptance":live,"revamp2_frontend_acceptance":frontend}
    commit=publish_acceptance(repo,packet_id,payload)
    print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"PASS","packet_id":packet_id,"acceptance_return_transport_commit":commit,**payload},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
