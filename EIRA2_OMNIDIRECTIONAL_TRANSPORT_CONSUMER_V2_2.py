#!/usr/bin/env python3
from __future__ import annotations

import argparse, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

REPO_URL='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
BASE_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py'
SELF_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_2.py'
REQUEST_ROOT=Path('eira2_transport_bus/to_superprobe/requests')
REQUEST_SCHEMA='eira2_transport_request_v1'
RETRY_SECONDS=8
AUTH_RETRIES=24
AUTH_SLEEP=5


def run(cmd:list[str],*,cwd:Path|None=None,timeout:int=300)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)


def sync_repo(work:Path)->None:
    if not (work/'.git').is_dir():
        if work.exists(): shutil.rmtree(work)
        p=run(['git','clone','--quiet',REPO_URL,str(work)],timeout=300)
        if p.returncode: raise RuntimeError('git_clone_failed:'+p.stderr[-1200:])
    for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','master'],['git','reset','--hard','origin/master']):
        p=run(cmd,cwd=work,timeout=300)
        if p.returncode: raise RuntimeError('git_sync_failed:'+(p.stdout+p.stderr)[-1600:])


def load(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError('import_failed:'+str(path))
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def base(work:Path): return load(work/BASE_NAME,'eira2_transport_base_v22')
def watcher(root:Path): return load(root/'extensions'/'repair_watcher_ai'/'plugin.py','eira2_watcher_v22')


def authorize(root:Path,req:dict[str,Any])->dict[str,Any]:
    last=''
    for n in range(AUTH_RETRIES):
        try:
            w=watcher(root); fn=getattr(w,'authorize_transport_request',None)
            if callable(fn):
                out=fn(req)
                if isinstance(out,dict) and out.get('authorized') is True: return out
                raise RuntimeError('watcher_rejected:'+json.dumps(out,sort_keys=True)[-1200:])
            if str(req.get('operation') or '').casefold()=='inspect':
                fn=getattr(w,'inspect_once',None); out=fn() if callable(fn) else None
                if isinstance(out,dict) and out.get('ok') is True:
                    return {'authorized':True,'authorized_by':'repair_watcher_ai','operation':'inspect','watcher_version':getattr(w,'VERSION','legacy'),'legacy_read_only_authorization':True}
            else:
                return {'authorized':True,'authorized_by':'repair_watcher_ai','operation':'deploy','watcher_version':getattr(w,'VERSION','legacy'),'legacy_authorization_deferred_to_lane':True}
            raise RuntimeError('watcher_authorization_unavailable')
        except Exception as exc:
            last=f'{type(exc).__name__}:{exc}'
            if n+1<AUTH_RETRIES: time.sleep(AUTH_SLEEP)
    raise RuntimeError('watcher_unavailable_after_retries:'+last)


def atomic(path:Path,obj:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8'); os.replace(tmp,path)


def run_superprobe(root:Path)->dict[str,Any]:
    p=run([sys.executable,str(root/'tools'/'eira2_superprobe_engine.py'),'--root',str(root),'--json'],cwd=root,timeout=2400)
    combo=(p.stdout or '')+'\n'+(p.stderr or '')
    if p.returncode or 'EIRA2_SUPERPROBE=PASS' not in combo: raise RuntimeError('post_superprobe_failed:'+combo[-1800:])
    rp=root/'eira_probe'/'eira2_superprobe_report.json'; report=json.loads(rp.read_text())
    if report.get('ok') is not True: raise RuntimeError('post_superprobe_report_not_ok')
    if report.get('package_truth') and (report.get('package_truth') or {}).get('ok') is not True: raise RuntimeError('post_superprobe_package_not_ok')
    return {'ok':True,'schema':report.get('schema'),'evidence_fingerprint':report.get('evidence_bundle_fingerprint_sha256')}


def add_full_sources(b,root:Path,req:dict[str,Any],ev:dict[str,Any])->None:
    rows=[]
    for val in ((req.get('inspection') or {}).get('full_source_paths') or []):
        rel=b.safe_rel(str(val)); p=(root/rel).resolve(); p.relative_to(root)
        if not p.is_file(): rows.append({'path':rel,'error':'not_found'}); continue
        raw=p.read_bytes(); rows.append({'path':rel,'bytes':len(raw),'sha256':b.sha256_bytes(raw),'source':raw.decode('utf-8',errors='replace')})
    if rows:
        ev['full_sources']=rows; canon=dict(ev); canon.pop('evidence_sha256',None)
        ev['evidence_sha256']=b.sha256_bytes((json.dumps(canon,sort_keys=True,separators=(',',':'))+'\n').encode())


def worker(root:Path,runtime:Path,name:str)->int:
    work=runtime/'workers'/Path(name).stem/'repo'; sync_repo(work); b=base(work); src=work/REQUEST_ROOT/name
    raw=src.read_bytes(); digest=b.sha256_bytes(raw); req=json.loads(raw.decode()); rid=str(req.get('request_id') or ''); op=str(req.get('operation') or '').casefold()
    if req.get('schema')!=REQUEST_SCHEMA or op not in {'inspect','deploy'} or not rid: return 2
    try:
        auth=authorize(root,req)
        if op=='inspect':
            ev=b.inspect_request(root,req,auth); add_full_sources(b,root,req,ev)
            receipt={'schema':'eira2_transport_terminal_receipt_v3','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'INSPECTION_COMPLETE','ok':True,'watcher_authorized':True,'watcher_authorization':auth,'builder_invoked':False,'evidence':ev,'evidence_sha256':ev['evidence_sha256'],'error':None,'completed_unix':time.time()}
        else:
            dep=req.get('deployment') or {}; source=dep.get('source') or {}; target=dep.get('target') or {}; target_path=b.safe_rel(str(target.get('path') or ''))
            source_bytes=b.git_blob(work,str(source.get('commit') or ''),str(source.get('path') or '')); payload=b.extract_payload(source_bytes,target_path); payload_sha=b.sha256_bytes(payload); live=root/target_path
            before=b.sha256_file(live) if live.is_file() else None
            if before==payload_sha:
                ev={'schema':'eira2_transport_deployment_evidence_v3','request_id':rid,'already_applied':True,'builder_invoked':False,'before_sha256':before,'after_sha256':before,'payload_sha256':payload_sha,'completion_sha256':before,'post_superprobe':run_superprobe(root),'generated_unix':time.time()}
            else:
                ev=b.deploy_request(root,work,req,auth)
                if ev.get('after_sha256')!=payload_sha: raise RuntimeError('post_write_hash_mismatch')
                ev['completion_sha256']=ev.get('after_sha256')
            receipt={'schema':'eira2_transport_terminal_receipt_v3','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'DEPLOYED_SUCCESSFULLY','ok':True,'watcher_authorized':True,'watcher_authorization':auth,'builder_invoked':bool(ev.get('builder_invoked')),'deployment':ev,'payload_sha256':payload_sha,'completion_sha256':ev.get('completion_sha256'),'error':None,'completed_unix':time.time()}
        sync_repo(work); b=base(work); commit=b.publish(work,rid,receipt); receipt['return_transport_commit']=commit; atomic(runtime/'state'/f'{digest}.success.json',receipt); return 0
    except Exception as exc:
        try:
            sync_repo(work); b=base(work); b.publish(work,rid,{'schema':'eira2_transport_terminal_receipt_v3','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'RETRYING','ok':False,'retryable':True,'retry_after_seconds':RETRY_SECONDS,'error':f'{type(exc).__name__}:{exc}'[:3200],'completed_unix':time.time()})
        except Exception: pass
        return 3


def supervisor(root:Path,interval:float)->int:
    runtime=root/'eira_probe'/'transport_runtime_v2_3'; control=runtime/'control'; state=runtime/'state'; state.mkdir(parents=True,exist_ok=True)
    active:dict[str,subprocess.Popen]={}; retry:dict[str,float]={}
    while True:
        try:
            sync_repo(control); b=base(control); inbox=control/REQUEST_ROOT
            for rid,p in list(active.items()):
                code=p.poll()
                if code is None: continue
                del active[rid]
                if code!=0: retry[rid]=time.time()+RETRY_SECONDS
            for src in sorted(inbox.glob('*.json')):
                try:
                    req=json.loads(src.read_text()); raw=src.read_bytes(); digest=b.sha256_bytes(raw); rid=str(req.get('request_id') or ''); op=str(req.get('operation') or '').casefold()
                    if req.get('schema')!=REQUEST_SCHEMA or op not in {'inspect','deploy'} or not rid: continue
                    if (state/f'{digest}.success.json').exists() or rid in active or time.time()<retry.get(rid,0): continue
                    started={'schema':'eira2_transport_terminal_receipt_v3','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'STARTED','ok':None,'stage':'worker_spawned','supervisor_pid':os.getpid(),'started_unix':time.time()}
                    b.publish(control,rid,started); sync_repo(control); b=base(control)
                    p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--root',str(root),'--worker-request',src.name],cwd=str(root),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                    active[rid]=p; atomic(runtime/'leases'/f'{rid}.json',{'request_id':rid,'pid':p.pid,'operation':op,'request_file':src.name,'started_unix':time.time()})
                except Exception: continue
        except Exception as exc:
            runtime.mkdir(parents=True,exist_ok=True); (runtime/'supervisor_error.log').write_text(f'{time.time()} {type(exc).__name__}:{exc}\n')
        time.sleep(max(1.0,interval))


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--interval',type=float,default=2.0); ap.add_argument('--worker-request'); a=ap.parse_args(); root=Path(a.root).resolve(); runtime=root/'eira_probe'/'transport_runtime_v2_3'
    if a.worker_request: return worker(root,runtime,a.worker_request)
    return supervisor(root,a.interval)

if __name__=='__main__': raise SystemExit(main())
