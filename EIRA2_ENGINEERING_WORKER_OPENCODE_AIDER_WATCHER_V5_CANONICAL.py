#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/plugin.py"
NEW = r'''from __future__ import annotations

import hashlib, importlib.util, json, os, shutil, signal, subprocess, tempfile, time
from pathlib import Path
from typing import Any

SCHEMA="eira2_engineering_worker_opencode_aider_watcher_v5_canonical"
EXTENSION_ID="eira.engineering.worker"
OPENCODE_MODEL="ollama/qwen2.5-coder:3b"
AIDER_MODEL="ollama_chat/qwen2.5-coder:3b"
LIVE_ROOT_DEFAULT="/media/domenicleonetti/easystore/EIRA/LIVE"
PROTECTED=("watcher","builder","truth","rollback","owner")


def _sha(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def _load(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError("module_load_failed:"+str(path))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def _bin(name:str)->str:
    p=shutil.which(name)
    if p: return p
    home=Path.home(); c={"opencode":[home/".opencode/bin/opencode",home/".local/bin/opencode"],"aider":[home/".local/bin/aider"]}.get(name,[])
    for x in c:
        if x.is_file() and os.access(x,os.X_OK): return str(x)
    raise RuntimeError(name+"_not_executable")

def _env()->dict[str,str]:
    e=dict(os.environ); e.update({"EIRA_ENGINEERING_SANDBOX":"1","EIRA_ENGINEERING_LIVE_WRITE":"0","AIDER_YES_ALWAYS":"true","AIDER_AUTO_COMMITS":"false"}); return e

def _run(argv:list[str],cwd:Path,timeout:int)->dict[str,Any]:
    started=time.time(); p=subprocess.Popen(argv,cwd=str(cwd),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=_env(),start_new_session=True)
    try:
        out,err=p.communicate(timeout=max(1,min(int(timeout),900)))
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid,signal.SIGTERM)
        except Exception: pass
        try: out,err=p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid,signal.SIGKILL)
            except Exception: pass
            out,err=p.communicate()
        return {"argv":argv,"returncode":124,"stdout":out or "","stderr":(err or "")+"\nTIMEOUT","timed_out":True,"elapsed_seconds":round(time.time()-started,3)}
    return {"argv":argv,"returncode":p.returncode,"stdout":out or "","stderr":err or "","timed_out":False,"elapsed_seconds":round(time.time()-started,3)}

def _tracked(root:Path)->list[str]:
    p=subprocess.run(["git","-C",str(root),"ls-files","-z"],capture_output=True,check=False)
    if p.returncode==0: return [x.decode() for x in p.stdout.split(b"\0") if x]
    manifest=root/"eira2-package-manifest.json"
    if not manifest.is_file(): raise RuntimeError("canonical_package_manifest_unavailable")
    rows=json.loads(manifest.read_text()).get("files") or []
    out=[]
    for r in rows:
        if isinstance(r,dict) and r.get("path"):
            rel=str(r["path"]); pth=root/rel
            if pth.is_file(): out.append(rel)
    if not out: raise RuntimeError("canonical_package_manifest_empty")
    return out

def _snapshot(root:Path,dst:Path)->None:
    for rel in _tracked(root):
        src=root/rel
        if src.is_file():
            out=dst/rel; out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,out)
    for argv in (["git","init","-q"],["git","config","user.name","EIRA Engineering Sandbox"],["git","config","user.email","eira@localhost"],["git","add","-A"],["git","commit","-qm","baseline"]):
        r=subprocess.run(argv,cwd=str(dst),text=True,capture_output=True,check=False)
        if r.returncode: raise RuntimeError("sandbox_git_setup_failed:"+(r.stderr or "")[-1000:])

def _workspace(root:Path)->dict[str,Path]:
    if not root.is_dir(): raise RuntimeError("eira_root_unavailable")
    s=Path(tempfile.mkdtemp(prefix="eira_engineering_v5_",dir="/tmp")); oc=s/"opencode"; ad=s/"aider"; rv=s/"review"; sh=s/"shared"
    for p in (oc,ad,rv,sh): p.mkdir(parents=True,exist_ok=True)
    _snapshot(root,oc); _snapshot(root,ad)
    return {"session":s,"opencode":oc,"aider":ad,"review":rv,"shared":sh}

def _inv(box:Path)->dict[str,str]:
    o={}
    for p in box.rglob("*"):
        if p.is_file() and ".git" not in p.parts: o[p.relative_to(box).as_posix()]=_sha(p.read_bytes())
    return o

def _changed(a:dict[str,str],b:dict[str,str])->list[str]: return sorted(x for x in set(a)|set(b) if a.get(x)!=b.get(x))
def _log(shared:Path,role:str,phase:str,payload:Any)->None:
    with (shared/"exchange.jsonl").open("a",encoding="utf-8") as f: f.write(json.dumps({"unix":time.time(),"role":role,"phase":phase,"payload":payload},sort_keys=True)+"\n")

def _tests(box:Path,changed:list[str],req:dict[str,Any])->list[dict[str,Any]]:
    out=[]; d=_run(["git","diff","--check"],box,60); out.append({"name":"git_diff_check","ok":d["returncode"]==0,"stderr":d["stderr"][-1200:]})
    for rel in changed:
        p=box/rel
        if rel.endswith(".py") and p.is_file():
            r=_run(["python3","-m","py_compile",rel],box,60); out.append({"name":"py_compile:"+rel,"ok":r["returncode"]==0,"stderr":r["stderr"][-1200:]})
    v=req.get("verification_argv")
    if not isinstance(v,list) or not v: out.append({"name":"verification","ok":False,"stderr":"verification_argv_required"})
    else:
        r=_run([str(x) for x in v],box,int(req.get("test_timeout_seconds") or 120)); out.append({"name":"verification","ok":r["returncode"]==0,"returncode":r["returncode"],"stdout_tail":r["stdout"][-3000:],"stderr_tail":r["stderr"][-2000:]})
    return out

def _structural(box:Path,changed:list[str])->dict[str,Any]:
    protected=[x for x in changed if any(k in x.lower() for k in PROTECTED)]
    suspicious=[x for x in changed if any(k in x.lower() for k in ("_new.","_v2.","_v3.","duplicate","parallel","backup"))]
    return {"ok":not protected and not suspicious,"protected_paths_touched":protected,"suspicious_parallel_names":suspicious}

def _transport_repo(root:Path)->Path:
    for p in sorted((root/"eira_probe").glob("transport_runtime_*/repo"),reverse=True):
        if (p/"EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py").is_file() and (p/"EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py").is_file() and (p/".git").is_dir(): return p
    td=Path(tempfile.mkdtemp(prefix="eira_v5_transport_",dir="/tmp"))/"repo"
    r=subprocess.run(["git","clone","--quiet","https://github.com/domenicleonetti8-dev/ish-broadcast.git",str(td)],text=True,capture_output=True,timeout=300,check=False)
    if r.returncode: raise RuntimeError("transport_repo_unavailable:"+(r.stderr or "")[-1200:])
    return td

def _deploy(root:Path,changed:list[str],candidates:dict[str,Any],evidence:dict[str,Any])->dict[str,Any]:
    if len(changed)!=1: raise RuntimeError("live_deploy_requires_single_canonical_target")
    rel=changed[0]; row=candidates[rel]
    if row.get("exists") is not True or not isinstance(row.get("content"),str): raise RuntimeError("deploy_candidate_missing")
    payload=row["content"].encode(); live=root/rel; before=live.read_bytes() if live.is_file() else None; before_sha=_sha(before) if before is not None else None
    watcher=_load(root/"extensions/repair_watcher_ai/plugin.py","eira_v5_watcher"); authfn=getattr(watcher,"authorize_transport_request",None)
    if not callable(authfn): raise RuntimeError("watcher_transport_authority_unavailable")
    rid="engineering_v5_"+str(int(time.time()*1000))
    req={"schema":"eira2_transport_request_v1","request_id":rid,"operation":"deploy","autonomous_engineering":True,"sandbox_evidence":evidence,"deployment":{"target":{"path":rel,"expected_before_sha256":before_sha}}}
    auth=authfn(req)
    if not isinstance(auth,dict) or auth.get("authorized") is not True: raise RuntimeError("watcher_rejected:"+json.dumps(auth,sort_keys=True)[-1600:])
    repo=_transport_repo(root); consumer=_load(repo/"EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py","eira_v5_transport")
    lane=consumer._run_lane(root,repo,rid,rel,payload,before_sha)
    after=live.read_bytes() if live.is_file() else None
    if after!=payload:
        current=consumer.sha256_file(live) if live.is_file() else None; rollback=consumer._rollback(root,repo,rid+"_rollback",rel,before,current)
        raise RuntimeError("post_deploy_hash_mismatch;rollback="+json.dumps(rollback,sort_keys=True)[-1600:])
    return {"ok":True,"request_id":rid,"watcher_authorized":True,"builder_lane_invoked":True,"target_path":rel,"before_sha256":before_sha,"after_sha256":_sha(after),"candidate_sha256":_sha(payload),"live_bytes_match_candidate":True,"lane_receipt":lane.get("lane_receipt") or {}}

def status(root:str|Path|None=None)->dict[str,Any]:
    r=Path(root or os.environ.get("EIRA_ROOT") or LIVE_ROOT_DEFAULT).resolve()
    return {"schema":SCHEMA,"extension_id":EXTENSION_ID,"root":str(r),"opencode":_bin("opencode"),"aider":_bin("aider"),"opencode_model":OPENCODE_MODEL,"aider_model":AIDER_MODEL,"canonical_write_path":"OpenCode -> Aider -> tests -> OpenCode review -> truth gate -> Watcher -> Builder lane -> LIVE","direct_coder_live_write":False}

def inspect(req:dict[str,Any])->dict[str,Any]:
    root=Path(req.get("root") or LIVE_ROOT_DEFAULT).resolve(); ws=_workspace(root); before=_inv(ws["opencode"])
    prompt="Inspect EIRA as one canonical organism. Do not edit. Return only reproducible defects, exact evidence, canonical owner, reproduction and action. If healthy say CHILL_AND_MOVE_ON.\nOBJECTIVE:\n"+str(req.get("objective") or "full canonical inspection")
    oc=_run([_bin("opencode"),"run","--model",str(req.get("opencode_model") or OPENCODE_MODEL),prompt],ws["opencode"],int(req.get("opencode_timeout_seconds") or 180)); muts=_changed(before,_inv(ws["opencode"])); _log(ws["shared"],"opencode","inspection",oc)
    return {"schema":SCHEMA,"mode":"inspect","ok":oc["returncode"]==0 and not muts,"workspace":str(ws["session"]),"opencode":oc,"sandbox_mutations":muts,"live_mutated":False}

def build(req:dict[str,Any])->dict[str,Any]:
    root=Path(req.get("root") or LIVE_ROOT_DEFAULT).resolve(); objective=str(req.get("objective") or "").strip()
    if not objective: raise RuntimeError("objective_required")
    evidence=req.get("failure_evidence") or []; interference=req.get("organism_interference") or []
    if not evidence and not interference: return {"schema":SCHEMA,"ok":False,"stage":"issue_gate","decision":"INSPECT_MORE","live_mutated":False}
    ws=_workspace(root); oc_before=_inv(ws["opencode"])
    plan_prompt="You are OpenCode. Produce a precise repair plan for Aider. Do not edit. No duplicate authority, no cosmetic churn.\nOBJECTIVE:\n"+objective+"\nEVIDENCE:\n"+json.dumps(evidence)+"\nINTERFERENCE:\n"+json.dumps(interference)
    oc=_run([_bin("opencode"),"run","--model",str(req.get("opencode_model") or OPENCODE_MODEL),plan_prompt],ws["opencode"],int(req.get("opencode_timeout_seconds") or 180)); _log(ws["shared"],"opencode","plan",oc)
    if oc["returncode"]!=0: return {"schema":SCHEMA,"ok":False,"stage":"opencode_plan","opencode":oc,"live_mutated":False}
    if _changed(oc_before,_inv(ws["opencode"])): raise RuntimeError("opencode_plan_mutated_sandbox")
    baseline=_inv(ws["aider"]); prompt="Implement this verified repair in this disposable sandbox only. Preserve working behavior. No parallel system.\nPLAN:\n"+oc["stdout"]+"\nOBJECTIVE:\n"+objective
    ad=_run([_bin("aider"),"--yes-always","--no-auto-commits","--no-dirty-commits","--model",str(req.get("aider_model") or AIDER_MODEL),"--message",prompt],ws["aider"],int(req.get("aider_timeout_seconds") or 300)); _log(ws["shared"],"aider","implementation",ad)
    if ad["returncode"]!=0: return {"schema":SCHEMA,"ok":False,"stage":"aider","aider":ad,"live_mutated":False,"workspace":str(ws["session"])}
    changed=_changed(baseline,_inv(ws["aider"]));
    if not changed: return {"schema":SCHEMA,"ok":False,"stage":"no_change","live_mutated":False,"workspace":str(ws["session"])}
    structural=_structural(ws["aider"],changed); tests=_tests(ws["aider"],changed,req)
    if not structural["ok"] or any(x.get("ok") is not True for x in tests): return {"schema":SCHEMA,"ok":False,"stage":"qualification","changed_paths":changed,"tests":tests,"structural_scan":structural,"live_mutated":False,"workspace":str(ws["session"])}
    shutil.copytree(ws["aider"],ws["review"],dirs_exist_ok=True,ignore=shutil.ignore_patterns(".git"))
    review_prompt="Adversarially review Aider's candidate. Do not edit. Reject regression, duplicate authority, weakened gates, unproven fix. End exactly REVIEW=PASS or REVIEW=FAIL.\nOBJECTIVE:\n"+objective+"\nCHANGED:\n"+json.dumps(changed)
    rv=_run([_bin("opencode"),"run","--model",str(req.get("opencode_model") or OPENCODE_MODEL),review_prompt],ws["review"],int(req.get("review_timeout_seconds") or 180)); _log(ws["shared"],"opencode","review",rv); review_ok=rv["returncode"]==0 and rv["stdout"].rstrip().endswith("REVIEW=PASS")
    gate={"ok":review_ok and structural["ok"] and all(x.get("ok") is True for x in tests),"review_passed":review_ok,"tests_passed":all(x.get("ok") is True for x in tests),"structural_passed":structural["ok"]}
    if not gate["ok"]: return {"schema":SCHEMA,"ok":False,"stage":"truth_honesty_gate","changed_paths":changed,"tests":tests,"review":rv,"truth_honesty_gate":gate,"live_mutated":False,"workspace":str(ws["session"])}
    candidates={}
    for rel in changed:
        p=ws["aider"]/rel; candidates[rel]={"exists":p.is_file(),"sha256":_sha(p.read_bytes()) if p.is_file() else None,"content":p.read_text() if p.is_file() else None}
    base={"schema":SCHEMA,"mode":"build","ok":True,"changed_paths":changed,"candidates":candidates,"tests":tests,"review_passed":True,"truth_honesty_gate":gate,"workspace":str(ws["session"]),"live_mutated":False}
    if req.get("deploy_live") is True:
        ev={"schema":SCHEMA,"objective":objective,"changed_paths":changed,"tests":tests,"review_passed":True,"truth_honesty_gate":gate,"candidate_sha256":candidates[changed[0]]["sha256"] if len(changed)==1 else None,"live_mutated_during_creation":False}
        dep=_deploy(root,changed,candidates,ev); base["deployment"]=dep; base["live_mutated"]=True
    return base

def ask(request:dict[str,Any]|str)->dict[str,Any]:
    if isinstance(request,str): request=json.loads(request)
    if not isinstance(request,dict): raise TypeError("engineering_worker_request_must_be_dict")
    mode=str(request.get("mode") or "status")
    if mode=="status": return status(request.get("root"))
    if mode=="inspect": return inspect(request)
    if mode in {"build","repair","self_repair"}: return build(request)
    raise RuntimeError("unsupported_mode:"+mode)

def register(context=None): return {"node":EXTENSION_ID,"ask":ask,"status":status,"inspect":inspect,"build":build}
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print("EIRA2_ENGINEERING_WORKER_V5_CANONICAL=PASS")
