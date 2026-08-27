from __future__ import annotations
import json, time
from . import plugin
from .engineering3d_bridge import invoke, provider_contract

def next_jobs():
    plugin._init()
    for p in sorted(plugin.JOBS_ROOT.glob("render_*.json")):
        if p.name.endswith("_engineering3d_receipt.json"):
            continue
        try:
            obj=json.loads(p.read_text())
            if obj.get("status")=="queued": yield p,obj
        except Exception: continue

def mark(path,obj,status,**extra):
    obj.update(extra); obj["status"]=status; obj["updated"]=time.time()
    path.write_text(json.dumps(obj,indent=2,default=str),encoding="utf-8")

def run_once():
    jobs=list(next_jobs())
    if not jobs: return {"ok":True,"processed":0,"provider":provider_contract()}
    p,j=jobs[0]
    mark(p,j,"engineering3d_dispatched")
    try:
        result=invoke(j)
    except Exception as exc:
        mark(p,j,"engineering3d_failed",error=f"{type(exc).__name__}:{str(exc)[:800]}")
        return {"ok":False,"processed":1,"job":j["job_id"],"error":j["error"]}
    mark(p,j,"engineering3d_completed",engineering3d=result)
    return {"ok":True,"processed":1,"job":j["job_id"],"status":"engineering3d_completed","result":result}

if __name__=="__main__": print(json.dumps(run_once(),indent=2,default=str))
