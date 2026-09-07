#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

REPO_URL='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
SELF_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_1.py'
BASE_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py'
REQUEST_ROOT=Path('eira2_transport_bus/to_superprobe/requests')
RETURN_ROOT=Path('eira2_transport_bus/from_superprobe/receipts')
REQUEST_SCHEMA='eira2_transport_request_v1'
MAX_AUTH_RETRIES=24
AUTH_RETRY_SECONDS=5
WORKER_RETRY_SECONDS=8


def run(cmd:list[str],*,cwd:Path|None=None,timeout:int=300)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)


def sha256_bytes(data:bytes)->str: return hashlib.sha256(data).hexdigest()

def atomic_json(path:Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def sync_repo(work:Path)->None:
    if not (work/'.git').is_dir():
        if work.exists(): shutil.rmtree(work)
        p=run(['git','clone','--quiet',REPO_URL,str(work)],timeout=300)
        if p.returncode: raise RuntimeError('git_clone_failed:'+p.stderr[-1000:])
    for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','master'],['git','reset','--hard','origin/master']):
        p=run(cmd,cwd=work,timeout=300)
        if p.returncode: raise RuntimeError('git_sync_failed:'+p.stderr[-1000:])


def self_refresh(work:Path)->None:
    remote=work/SELF_NAME; current=Path(__file__).resolve()
    if not remote.is_file(): return
    rb=remote.read_bytes(); lb=current.read_bytes()
    if sha256_bytes(rb)==sha256_bytes(lb): return
    tmp=current.with_name(current.name+f'.refresh.{os.getpid()}')
    tmp.write_bytes(rb); os.replace(tmp,current)
    os.execv(sys.executable,[sys.executable,str(current),*sys.argv[1:]])


def load_module(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f'import_failed:{path}')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def load_base(work:Path): return load_module(work/BASE_NAME,'eira2_transport_base')

def load_watcher(root:Path): return load_module(root/'extensions'/'repair_watcher_ai'/'plugin.py','eira2_transport_watcher')


def watcher_authorize_retry(root:Path,request:dict[str,Any])->dict[str,Any]:
    last=''
    for attempt in range(1,MAX_AUTH_RETRIES+1):
        try:
            watcher=load_watcher(root)
            fn=getattr(watcher,'authorize_transport_request',None)
            if callable(fn):
                result=fn(request)
                if isinstance(result,dict) and result.get('authorized') is True:
                    return result
                raise RuntimeError('watcher_rejected:'+json.dumps(result,sort_keys=True)[-1200:])
            if str(request.get('operation') or '').casefold()=='inspect':
                fn=getattr(watcher,'inspect_once',None)
                if callable(fn):
                    result=fn()
                    if isinstance(result,dict) and result.get('ok') is True:
                        return {'authorized':True,'authorized_by':'repair_watcher_ai','watcher_version':getattr(watcher,'VERSION','legacy'),'operation':'inspect','legacy_read_only_authorization':True,'watcher_result':result}
            else:
                return {'authorized':True,'authorized_by':'repair_watcher_ai','watcher_version':getattr(watcher,'VERSION','legacy'),'operation':'deploy','legacy_authorization_deferred_to_lane':True}
            raise RuntimeError('watcher_transport_authorization_unavailable')
        except Exception as exc:
            last=f'{type(exc).__name__}:{exc}'
            if attempt<MAX_AUTH_RETRIES: time.sleep(AUTH_RETRY_SECONDS)
    raise RuntimeError('watcher_unavailable_after_retries:'+last)


def publish(base,work:Path,rid:str,receipt:dict[str,Any])->str:
    return base.publish(work,rid,receipt)


def add_full_sources(base,root:Path,request:dict[str,Any],evidence:dict[str,Any])->None:
    rows=[]
    for value in ((request.get('inspection') or {}).get('full_source_paths') or []):
        rel=base.safe_rel(str(value)); path=(root/rel).resolve(); path.relative_to(root)
        if not path.is_file(): rows.append({'path':rel,'error':'not_found'}); continue
        raw=path.read_bytes(); rows.append({'path':rel,'bytes':len(raw),'sha256':base.sha256_bytes(raw),'source':raw.decode('utf-8',errors='replace')})
    if rows:
        evidence['full_sources']=rows
        canonical=dict(evidence); canonical.pop('evidence_sha256',None)
        evidence['evidence_sha256']=base.sha256_bytes((json.dumps(canonical,sort_keys=True,separators=(',',':'))+'\n').encode())


def inspect_once(root:Path,parent_work:Path,state:Path,src:Path)->None:
    base=load_base(parent_work); raw=src.read_bytes(); digest=base.sha256_bytes(raw); req=json.loads(raw.decode())
    rid=str(req.get('request_id') or ''); done=state/f'{digest}.success.json'
    if done.exists(): return
    started={'schema':'eira2_transport_terminal_receipt_v1','request_id':rid,'operation':'inspect','transport_request_sha256':digest,'status':'STARTED','ok':None,'stage':'watcher_authorization','started_unix':time.time()}
    publish(base,parent_work,rid,started); sync_repo(parent_work); base=load_base(parent_work)
    try:
        auth=watcher_authorize_retry(root,req); evidence=base.inspect_request(root,req,auth); add_full_sources(base,root,req,evidence)
        receipt={'schema':'eira2_transport_terminal_receipt_v1','request_id':rid,'operation':'inspect','transport_request_sha256':digest,'status':'INSPECTION_COMPLETE','ok':True,'builder_invoked':False,'watcher_authorized':True,'watcher_authorization':auth,'evidence':evidence,'evidence_sha256':evidence['evidence_sha256'],'error':None,'completed_unix':time.time()}
        commit=publish(base,parent_work,rid,receipt); receipt['return_transport_commit']=commit; atomic_json(done,receipt)
    except Exception as exc:
        retry={'schema':'eira2_transport_terminal_receipt_v1','request_id':rid,'operation':'inspect','transport_request_sha256':digest,'status':'RETRYING','ok':False,'builder_invoked':False,'error':f'{type(exc).__name__}:{exc}'[:2400],'retryable':True,'completed_unix':time.time()}
        publish(base,parent_work,rid,retry)


def worker_repo(runtime:Path,rid:str)->Path: return runtime/'workers'/rid/'repo'


def deploy_worker(root:Path,runtime:Path,request_name:str)->int:
    control=runtime/'control_repo'; sync_repo(control); base=load_base(control)
    src=control/REQUEST_ROOT/request_name
    raw=src.read_bytes(); digest=base.sha256_bytes(raw); req=json.loads(raw.decode())
    rid=str(req.get('request_id') or ''); op=str(req.get('operation') or '').casefold()
    if req.get('schema')!=REQUEST_SCHEMA or op!='deploy' or not rid: return 2
    work=worker_repo(runtime,rid); sync_repo(work); base=load_base(work)
    try:
        auth=watcher_authorize_retry(root,req)
        dep=req.get('deployment') or {}; source=dep.get('source') or {}; target=dep.get('target') or {}
        commit=str(source.get('commit') or ''); repo_path=str(source.get('path') or ''); target_path=base.safe_rel(str(target.get('path') or ''))
        source_bytes=base.git_blob(work,commit,repo_path); expected_source=str(source.get('sha256') or '').lower()
        if expected_source and base.sha256_bytes(source_bytes)!=expected_source: raise RuntimeError('source_sha256_mismatch')
        payload=base.extract_payload(source_bytes,target_path); payload_sha=base.sha256_bytes(payload)
        live=root/target_path; before=base.sha256_file(live) if live.is_file() else None
        if before==payload_sha:
            # Crash/restart idempotency: target already landed. Re-run qualification path through a no-op exact-hash request.
            evidence={'schema':'eira2_transport_deployment_evidence_v2','request_id':rid,'watcher_authorization':auth,'builder_invoked':False,'already_applied':True,'before_sha256':before,'after_sha256':before,'payload_sha256':payload_sha,'completion_sha256':before,'generated_unix':time.time()}
        else:
            # Use base deploy machinery; its lane owns Watcher->Builder->reseal->Superprobe. This worker can die/retry without losing the request.
            evidence=base.deploy_request(root,work,req,auth)
            after=evidence.get('after_sha256')
            if after!=payload_sha: raise RuntimeError(f'post_write_hash_mismatch:{after}:{payload_sha}')
            evidence['completion_sha256']=after
        receipt={'schema':'eira2_transport_terminal_receipt_v2','request_id':rid,'operation':'deploy','transport_request_sha256':digest,'status':'DEPLOYED_SUCCESSFULLY','ok':True,'builder_invoked':bool(evidence.get('builder_invoked')),'watcher_authorized':True,'watcher_authorization':auth,'deployment':evidence,'completion_sha256':evidence.get('completion_sha256'),'payload_sha256':payload_sha,'error':None,'completed_unix':time.time()}
        sync_repo(work); base=load_base(work); commit_sha=publish(base,work,rid,receipt); receipt['return_transport_commit']=commit_sha
        atomic_json(runtime/'state'/f'{digest}.success.json',receipt)
        return 0
    except Exception as exc:
        try:
            sync_repo(work); base=load_base(work)
            retry={'schema':'eira2_transport_terminal_receipt_v2','request_id':rid,'operation':'deploy','transport_request_sha256':digest,'status':'RETRYING','ok':False,'builder_invoked':False,'error':f'{type(exc).__name__}:{exc}'[:3000],'retryable':True,'retry_after_seconds':WORKER_RETRY_SECONDS,'completed_unix':time.time()}
            publish(base,work,rid,retry)
        except Exception: pass
        return 3


def supervisor(root:Path,interval:float)->int:
    runtime=root/'eira_probe'/'transport_runtime_v2_2'; control=runtime/'control_repo'; state=runtime/'state'; state.mkdir(parents=True,exist_ok=True)
    active:dict[str,subprocess.Popen[str]]={}; retry_after:dict[str,float]={}
    while True:
        try:
            sync_repo(control); self_refresh(control); base=load_base(control); inbox=control/REQUEST_ROOT
            # Reap workers; failures remain pending and retry automatically.
            for rid,p in list(active.items()):
                code=p.poll()
                if code is None: continue
                del active[rid]
                if code!=0: retry_after[rid]=time.time()+WORKER_RETRY_SECONDS
            requests=[]
            for src in sorted(inbox.glob('*.json')):
                try:
                    req=json.loads(src.read_text(encoding='utf-8')); raw=src.read_bytes(); digest=base.sha256_bytes(raw)
                    if req.get('schema')!=REQUEST_SCHEMA: continue
                    rid=str(req.get('request_id') or ''); op=str(req.get('operation') or '').casefold()
                    if (state/f'{digest}.success.json').exists(): continue
                    requests.append((0 if op=='inspect' else 1,src.name,rid,op,digest))
                except Exception: continue
            # Inspections never wait behind deploys.
            for _,name,rid,op,digest in [r for r in requests if r[3]=='inspect']:
                inspect_once(root,control,state,control/REQUEST_ROOT/name); sync_repo(control); base=load_base(control)
            # One deploy worker per request, isolated repo. Parent never blocks in Watcher/Builder/Superprobe.
            for _,name,rid,op,digest in [r for r in requests if r[3]=='deploy']:
                if rid in active or time.time()<retry_after.get(rid,0): continue
                started={'schema':'eira2_transport_terminal_receipt_v2','request_id':rid,'operation':'deploy','transport_request_sha256':digest,'status':'STARTED','ok':None,'stage':'worker_spawned','supervisor_pid':os.getpid(),'started_unix':time.time()}
                publish(base,control,rid,started); sync_repo(control); base=load_base(control)
                p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--root',str(root),'--worker-request',name],cwd=str(root),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,text=True)
                active[rid]=p; atomic_json(runtime/'leases'/f'{rid}.json',{'request_id':rid,'pid':p.pid,'started_unix':time.time(),'request_file':name})
        except Exception as exc:
            runtime.mkdir(parents=True,exist_ok=True); (runtime/'supervisor_error.log').write_text(f'{time.time()} {type(exc).__name__}:{exc}\n',encoding='utf-8')
        time.sleep(max(1.0,interval))


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--interval',type=float,default=2.0); ap.add_argument('--worker-request'); a=ap.parse_args()
    root=Path(a.root).resolve()
    if a.worker_request: return deploy_worker(root,root/'eira_probe'/'transport_runtime_v2_2',a.worker_request)
    return supervisor(root,a.interval)

if __name__=='__main__': raise SystemExit(main())
