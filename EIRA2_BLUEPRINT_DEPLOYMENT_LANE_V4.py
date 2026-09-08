#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from typing import Any

CORE_COMMIT = "f61240000d4fd3eb8ddab7ff6800c5555f501490"
CORE_PATH = "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
INSPECTION_PREFIX = "inspect_revamp_mic_lifecycle_v1"
FRONTEND_PROBE_PATH = "EIRA2_REVAMP2_FRONTEND_ACCEPTANCE_PROBE_V1.py"
SIGNATURES = ["/v1/listen", "getUserMedia", "packPCM16", "state.active", "transcribing", "inactive"]


def run(cmd:list[str],*,cwd:Path,timeout:int=2400)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=str(cwd),text=True,capture_output=True,timeout=timeout,check=False)


def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def atomic_json(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,path)


def publish(repo:Path,rel:Path,payload:dict[str,Any])->str:
    run(["git","fetch","--quiet","origin","master"],cwd=repo,timeout=300)
    reset=run(["git","reset","--hard","origin/master"],cwd=repo,timeout=300)
    if reset.returncode: raise RuntimeError("inspection_reset_failed:"+reset.stderr[-800:])
    atomic_json(repo/rel,payload); add=run(["git","add",rel.as_posix()],cwd=repo,timeout=120)
    if add.returncode: raise RuntimeError("inspection_git_add_failed:"+add.stderr[-800:])
    if run(["git","diff","--cached","--quiet"],cwd=repo,timeout=120).returncode!=0:
        c=run(["git","-c","user.name=EIRA Read Only Probe","-c","user.email=eira-probe@localhost","commit","--quiet","-m","Return read-only revamp mic inspection"],cwd=repo,timeout=120)
        if c.returncode: raise RuntimeError("inspection_commit_failed:"+c.stderr[-800:])
        p=run(["git","pull","--rebase","--quiet","origin","master"],cwd=repo,timeout=300)
        if p.returncode: raise RuntimeError("inspection_rebase_failed:"+p.stderr[-1000:])
        p=run(["git","push","--quiet","origin","master"],cwd=repo,timeout=300)
        if p.returncode: raise RuntimeError("inspection_push_failed:"+p.stderr[-1000:])
    return run(["git","rev-parse","HEAD"],cwd=repo,timeout=120).stdout.strip()


def inspect_filesystem(root:Path)->dict[str,Any]:
    rows=[]; candidates=[]
    for base in (root/"eira2",root/"extensions"):
        if not base.is_dir(): continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".js",".html"}: candidates.append(p)
    for p in sorted(set(candidates)):
        try: text=p.read_text(encoding="utf-8",errors="replace")
        except OSError: continue
        matched=[s for s in SIGNATURES if s in text]
        if matched:
            try: rel=p.resolve().relative_to(root.resolve()).as_posix()
            except Exception: rel=str(p)
            rows.append({"path":rel,"sha256":sha256_file(p),"bytes":p.stat().st_size,"matched_signatures":matched})
    return {"candidate_files_scanned":len(candidates),"matching_files":rows[:20],"best_match":rows[0] if rows else None}


def inspect_served(root:Path,repo:Path)->dict[str,Any]:
    probe=Path("/tmp")/f"eira2_readonly_revamp_probe_{os.getpid()}.py"; out=root/"eira_probe"/"revamp2_readonly_mic_inspection.json"
    show=subprocess.run(["git","-C",str(repo),"show",f"origin/master:{FRONTEND_PROBE_PATH}"],capture_output=True,timeout=120,check=False)
    if show.returncode: return {"ok":False,"error":"frontend_probe_fetch_failed:"+show.stderr[-800:].decode(errors="replace")}
    probe.write_bytes(show.stdout)
    try: proc=run([sys.executable,str(probe),"--base","http://127.0.0.1:8782/","--out",str(out)],cwd=root,timeout=180)
    finally:
        try: probe.unlink()
        except OSError: pass
    payload={}
    if out.is_file():
        try:
            value=json.loads(out.read_text(encoding="utf-8")); payload=value if isinstance(value,dict) else {}
        except Exception: payload={}
    return {"probe_returncode":proc.returncode,"stdout":proc.stdout[-1200:],"stderr":proc.stderr[-1200:],**payload}


def inspect_live(root:Path,repo:Path,packet_id:str)->dict[str,Any]:
    return {"schema":"eira2_read_only_revamp_mic_inspection_v3","packet_id":packet_id,"mode":"read_only","mutates_live":False,"root":str(root),"signatures":SIGNATURES,"filesystem":inspect_filesystem(root),"served_revamp2":inspect_served(root,repo),"generated_unix":time.time()}


def delegate_core(root:Path,repo:Path,packet:Path)->int:
    core=Path("/tmp")/f"eira2_lane_v4_core_{os.getpid()}.py"
    show=subprocess.run(["git","-C",str(repo),"show",f"{CORE_COMMIT}:{CORE_PATH}"],capture_output=True,timeout=120,check=False)
    if show.returncode:
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"FAIL","error":"core_fetch_failed"}),file=sys.stderr); return 2
    core.write_bytes(show.stdout)
    try: proc=run([sys.executable,str(core),"--root",str(root),"--packet",str(packet),"--source-repo-root",str(repo)],cwd=root,timeout=3600)
    finally:
        try: core.unlink()
        except OSError: pass
    sys.stdout.write(proc.stdout or ""); sys.stderr.write(proc.stderr or ""); return proc.returncode


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); ap.add_argument("--packet",required=True); ap.add_argument("--source-repo-root",required=True); a=ap.parse_args()
    root=Path(a.root).resolve(); packet=Path(a.packet).resolve(); repo=Path(a.source_repo_root).resolve(); data=json.loads(packet.read_text(encoding="utf-8")); packet_id=str(data.get("packet_id") or "")
    if packet_id.startswith(INSPECTION_PREFIX):
        payload=inspect_live(root,repo,packet_id); rel=Path("eira2_transport_bus/from_superprobe/inspections")/"inspect_revamp_mic_lifecycle_v1__result.json"; commit=publish(repo,rel,payload)
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4":"PASS","inspection_only":True,"mutates_live":False,"packet_id":packet_id,"return_transport_commit":commit},indent=2)); return 0
    return delegate_core(root,repo,packet)


if __name__=="__main__": raise SystemExit(main())
