#!/usr/bin/env python3
from __future__ import annotations

import hashlib, importlib.util, json, os, py_compile, subprocess, tempfile, time
from pathlib import Path
from typing import Any

SCHEMA="eira2_autonomous_engineering_loop_v2"
DENIED_PREFIXES=("main.py","engine/","brain/","council/","routers/","voice/","identity/","memory/","reasoning/","speech/")
MAX_ATTEMPTS_HARD=5

def sha256_bytes(data:bytes)->str: return hashlib.sha256(data).hexdigest()

def safe_rel(value:str)->str:
    p=Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts: raise RuntimeError("unsafe_relative_path:"+str(value))
    return p.as_posix()

def core_denied(target:str)->bool:
    t=safe_rel(target); return t=="main.py" or any(t.startswith(x) for x in DENIED_PREFIXES if x!="main.py")

def atomic_json(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,path)

def load_module(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError("module_load_failed:"+str(path))
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def find_verified_engineering(root:Path):
    candidates=[root/"extensions"/"verified_engineering_ai"/"plugin.py",root/"extensions"/"verified_engineering_ai"/"verified_engineering_ai.py",root/"extensions"/"verified_engineering_ai"/"__init__.py"]
    errors=[]
    for path in candidates:
        if not path.is_file(): continue
        try:
            mod=load_module(path,"eira2_autonomous_verified_engineering"); fn=getattr(mod,"ask",None)
            if callable(fn): return fn,path
        except Exception as exc: errors.append(f"{path}:{type(exc).__name__}:{exc}")
    raise RuntimeError("verified_engineering_ask_unavailable:"+" | ".join(errors[-3:]))

def extract_candidate(value:Any)->bytes:
    if isinstance(value,bytes): return value
    if isinstance(value,str): return value.encode()
    if isinstance(value,dict):
        for key in ("candidate_bytes","candidate","content","code","text","output","replacement"):
            v=value.get(key)
            if isinstance(v,bytes): return v
            if isinstance(v,str): return v.encode()
    raise RuntimeError("verified_engineering_result_has_no_candidate")

def generate_candidate(root:Path,sandbox:Path,job:dict[str,Any],before:bytes|None,prior_failures:list[dict[str,Any]])->tuple[bytes,dict[str,Any]]:
    objective=str(job.get("objective") or "").strip(); target=safe_rel(str(job.get("target_path") or ""))
    if not objective: raise RuntimeError("autonomous_objective_required")
    if job.get("qualification_canary") is True:
        value=job.get("canary_candidate_text")
        if not isinstance(value,str) or not value: raise RuntimeError("qualification_canary_text_required")
        candidate=value.encode("utf-8")
        return candidate,{"provider":"deterministic_control_loop_canary","qualification_only":True,"candidate_sha256":sha256_bytes(candidate),"candidate_bytes":len(candidate)}
    ask,provider_path=find_verified_engineering(root)
    req={
        "schema":"eira2_verified_engineering_autonomous_candidate_v2",
        "objective":objective,
        "target_path":target,
        "sandbox_root":str(sandbox),
        "existing_source":before.decode("utf-8",errors="replace") if before is not None else None,
        "requirements":job.get("requirements") or [],
        "prior_failed_attempts":prior_failures[-3:],
        "constraints":[
            "Return a complete replacement candidate only; never mutate LIVE.",
            "Preserve compatible interfaces unless the objective explicitly requires a change.",
            "Use prior_failed_attempts as repair evidence and correct the observed failure.",
            "Do not claim verification; verification is performed by the autonomous sandbox loop."
        ]
    }
    try: result=ask(req)
    except TypeError: result=ask(json.dumps(req,sort_keys=True))
    candidate=extract_candidate(result)
    if not candidate: raise RuntimeError("empty_candidate")
    return candidate,{"provider":str(provider_path.resolve().relative_to(root.resolve())),"candidate_sha256":sha256_bytes(candidate),"candidate_bytes":len(candidate)}

def run_checks(sandbox:Path,candidate_path:Path,job:dict[str,Any])->dict[str,Any]:
    checks=[]; suffix=candidate_path.suffix.lower()
    checks.append({"name":"candidate_nonempty","ok":candidate_path.is_file() and candidate_path.stat().st_size>0})
    if suffix==".py":
        try: py_compile.compile(str(candidate_path),doraise=True); checks.append({"name":"python_compile","ok":True})
        except Exception as exc: checks.append({"name":"python_compile","ok":False,"error":f"{type(exc).__name__}:{exc}"})
    elif suffix==".json":
        try: json.loads(candidate_path.read_text(encoding="utf-8")); checks.append({"name":"json_parse","ok":True})
        except Exception as exc: checks.append({"name":"json_parse","ok":False,"error":f"{type(exc).__name__}:{exc}"})
    argv=job.get("test_argv")
    if argv is not None:
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv): raise RuntimeError("test_argv_must_be_nonempty_string_list")
        timeout=max(1,min(int(job.get("test_timeout_seconds") or 300),1800))
        env={"PATH":os.environ.get("PATH",""),"PYTHONPATH":str(sandbox),"HOME":str(sandbox),"EIRA_AUTONOMOUS_SANDBOX":"1","EIRA2_CANDIDATE_PATH":str(candidate_path)}
        p=subprocess.run(argv,cwd=str(sandbox),text=True,capture_output=True,timeout=timeout,check=False,env=env)
        checks.append({"name":"requested_tests","ok":p.returncode==0,"returncode":p.returncode,"stdout_tail":(p.stdout or "")[-12000:],"stderr_tail":(p.stderr or "")[-6000:]})
    return {"checks":checks,"ok":all(x.get("ok") is True for x in checks),"evaluated_unix":time.time()}

def watcher_approve(root:Path,outer_request:dict[str,Any],evidence:dict[str,Any])->dict[str,Any]:
    path=root/"extensions"/"repair_watcher_ai"/"plugin.py"
    if not path.is_file(): raise RuntimeError("repair_watcher_missing")
    watcher=load_module(path,"eira2_autonomous_repair_watcher"); fn=getattr(watcher,"authorize_transport_request",None)
    if not callable(fn): raise RuntimeError("watcher_transport_authority_unavailable")
    approval_request={"schema":"eira2_transport_request_v1","request_id":str(outer_request.get("request_id") or "")+".sandbox_approval","operation":"deploy","autonomous_engineering":True,"sandbox_evidence":evidence,"deployment":outer_request.get("deployment") or {}}
    out=fn(approval_request)
    if not isinstance(out,dict) or out.get("authorized") is not True: raise RuntimeError("watcher_rejected_autonomous_candidate:"+json.dumps(out,sort_keys=True)[-1800:])
    return out

def prepare_candidate(root:Path,request:dict[str,Any])->dict[str,Any]:
    dep=request.get("deployment") or {}; job=dep.get("autonomous_job") or {}; target=safe_rel(str(job.get("target_path") or (dep.get("target") or {}).get("path") or ""))
    if core_denied(target) and job.get("explicit_core_authorization") is not True: raise RuntimeError("autonomous_core_boundary_denied:"+target)
    job_id=str(request.get("request_id") or "autonomous"); sandbox_root=root/"eira_probe"/"autonomous_engineering"/"sandboxes"; sandbox_root.mkdir(parents=True,exist_ok=True); sandbox=Path(tempfile.mkdtemp(prefix=job_id[:48]+"_",dir=str(sandbox_root)))
    live=root/target; before=live.read_bytes() if live.is_file() else None; before_sha=sha256_bytes(before) if before is not None else None; candidate_path=sandbox/Path(target).name; started=time.time()
    max_attempts=max(1,min(int(job.get("max_sandbox_attempts") or 3),MAX_ATTEMPTS_HARD)); attempts=[]; prior_failures=[]
    try:
        final_candidate=None; final_producer=None; final_tests=None
        for attempt in range(1,max_attempts+1):
            candidate,producer=generate_candidate(root,sandbox,{**job,"target_path":target},before,prior_failures)
            candidate_path.write_bytes(candidate); tests=run_checks(sandbox,candidate_path,job)
            row={"attempt":attempt,"candidate_sha256":sha256_bytes(candidate),"candidate_bytes":len(candidate),"producer":producer,"tests":tests}
            attempts.append(row)
            if tests.get("ok") is True:
                final_candidate=candidate; final_producer=producer; final_tests=tests; break
            prior_failures.append({"attempt":attempt,"tests":tests,"candidate_sha256":sha256_bytes(candidate)})
        evidence={
            "schema":SCHEMA,"request_id":job_id,"target_path":target,"sandbox":str(sandbox),"sandbox_isolated":True,"live_mutated_during_creation":False,
            "before_exists":before is not None,"before_sha256":before_sha,"before_bytes":len(before) if before is not None else 0,
            "objective":str(job.get("objective") or ""),"attempts":attempts,"max_sandbox_attempts":max_attempts,"started_unix":started,"evaluated_unix":time.time()
        }
        if final_candidate is None or final_tests is None or final_tests.get("ok") is not True:
            evidence["approved"]=False; evidence["failure"]="sandbox_attempts_exhausted"
            atomic_json(root/"eira_probe"/"autonomous_engineering"/"evidence"/f"{job_id}.failed.json",evidence)
            raise RuntimeError("autonomous_sandbox_tests_failed:"+json.dumps(evidence,sort_keys=True)[-3200:])
        evidence.update({"candidate_sha256":sha256_bytes(final_candidate),"candidate_bytes":len(final_candidate),"producer":final_producer,"tests":final_tests,"sandbox_tests_passed":True})
        approval=watcher_approve(root,request,evidence); evidence["watcher_approval"]=approval; evidence["approved"]=True; evidence["approval_unix"]=time.time()
        receipt=root/"eira_probe"/"autonomous_engineering"/"evidence"/f"{job_id}.json"; atomic_json(receipt,evidence)
        return {"payload":final_candidate,"target_path":target,"before_sha256":before_sha,"evidence":evidence,"evidence_path":str(receipt)}
    except Exception:
        fail=root/"eira_probe"/"autonomous_engineering"/"evidence"/f"{job_id}.failed.json"
        if not fail.exists(): atomic_json(fail,{"schema":SCHEMA,"request_id":job_id,"target_path":target,"sandbox":str(sandbox),"sandbox_isolated":True,"live_mutated_during_creation":False,"before_sha256":before_sha,"approved":False,"attempts":attempts,"failed_unix":time.time()})
        raise
