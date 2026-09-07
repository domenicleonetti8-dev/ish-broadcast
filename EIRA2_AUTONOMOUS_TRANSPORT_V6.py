#!/usr/bin/env python3
from __future__ import annotations

import argparse, importlib.util, json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
from typing import Any

REPO_URL='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
REQUEST_ROOT=Path('eira2_transport_bus/to_superprobe/requests')
RETURN_ROOT=Path('eira2_transport_bus/from_superprobe/receipts')
REQUEST_SCHEMA='eira2_transport_request_v1'
BASE_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py'
HEARTBEAT_SECONDS=5
RETRY_SECONDS=8


def run(cmd:list[str],*,cwd:Path|None=None,timeout:int=600)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)


def atomic(path:Path,obj:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def heal_git_state(repo:Path)->None:
    git=repo/'.git'
    if not git.is_dir():
        return
    if (git/'rebase-merge').exists() or (git/'rebase-apply').exists():
        run(['git','rebase','--abort'],cwd=repo,timeout=120)
    merge_head=git/'MERGE_HEAD'
    if merge_head.exists():
        run(['git','merge','--abort'],cwd=repo,timeout=120)
    for p in (git/'CHERRY_PICK_HEAD',git/'REVERT_HEAD'):
        if p.exists():
            run(['git','reset','--merge'],cwd=repo,timeout=120)
            break
    lock=git/'index.lock'
    if lock.exists():
        try:
            age=time.time()-lock.stat().st_mtime
            if age>300:
                lock.unlink()
        except OSError:
            pass


def sync_repo(repo:Path)->None:
    if not (repo/'.git').is_dir():
        if repo.exists(): shutil.rmtree(repo)
        p=run(['git','clone','--quiet',REPO_URL,str(repo)],timeout=600)
        if p.returncode: raise RuntimeError('git_clone_failed:'+(p.stdout+p.stderr)[-1800:])
    heal_git_state(repo)
    for cmd in (
        ['git','fetch','--quiet','origin','master'],
        ['git','checkout','--quiet','master'],
        ['git','reset','--hard','origin/master'],
        ['git','clean','-fd'],
    ):
        p=run(cmd,cwd=repo,timeout=600)
        if p.returncode: raise RuntimeError('git_sync_failed:'+(p.stdout+p.stderr)[-1800:])


def load_module(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError('import_failed:'+str(path))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_base(repo:Path):
    return load_module(repo/BASE_NAME,'eira2_transport_v6_base')


def load_watcher(root:Path):
    return load_module(root/'extensions'/'repair_watcher_ai'/'plugin.py','eira2_transport_v6_watcher')


def authorize(root:Path,request:dict[str,Any])->dict[str,Any]:
    last=''
    for n in range(12):
        try:
            watcher=load_watcher(root)
            fn=getattr(watcher,'authorize_transport_request',None)
            if callable(fn):
                out=fn(request)
                if isinstance(out,dict) and out.get('authorized') is True:
                    return out
                raise RuntimeError('watcher_rejected:'+json.dumps(out,sort_keys=True)[-1600:])
            if str(request.get('operation') or '').casefold()=='inspect':
                fallback=getattr(watcher,'inspect_once',None)
                out=fallback() if callable(fallback) else None
                if isinstance(out,dict) and out.get('ok') is True:
                    return {'authorized':True,'authorized_by':'repair_watcher_ai','operation':'inspect','watcher_version':getattr(watcher,'VERSION','legacy'),'legacy_read_only_authorization':True}
            raise RuntimeError('watcher_transport_authority_unavailable')
        except Exception as exc:
            last=f'{type(exc).__name__}:{exc}'
            if n<11: time.sleep(5)
    raise RuntimeError('watcher_unavailable_after_retries:'+last)


def publish(repo:Path,request_id:str,receipt:dict[str,Any])->str:
    sync_repo(repo)
    rel=RETURN_ROOT/f'{request_id}__receipt.json'
    atomic(repo/rel,receipt)
    p=run(['git','add',rel.as_posix()],cwd=repo,timeout=120)
    if p.returncode: raise RuntimeError('receipt_add_failed:'+(p.stdout+p.stderr)[-1200:])
    if run(['git','diff','--cached','--quiet'],cwd=repo,timeout=120).returncode!=0:
        p=run(['git','-c','user.name=EIRA Transport V6','-c','user.email=eira-transport-v6@localhost','commit','--quiet','-m',f'Return EIRA2 transport V6 receipt {request_id}'],cwd=repo,timeout=120)
        if p.returncode: raise RuntimeError('receipt_commit_failed:'+(p.stdout+p.stderr)[-1600:])
        heal_git_state(repo)
        p=run(['git','pull','--rebase','--quiet','origin','master'],cwd=repo,timeout=600)
        if p.returncode:
            heal_git_state(repo)
            p2=run(['git','fetch','--quiet','origin','master'],cwd=repo,timeout=600)
            if p2.returncode: raise RuntimeError('receipt_fetch_recovery_failed:'+(p2.stdout+p2.stderr)[-1800:])
            p2=run(['git','rebase','origin/master'],cwd=repo,timeout=600)
            if p2.returncode:
                heal_git_state(repo)
                raise RuntimeError('receipt_rebase_failed:'+(p.stdout+p.stderr+p2.stdout+p2.stderr)[-2200:])
        p=run(['git','push','--quiet','origin','master'],cwd=repo,timeout=600)
        if p.returncode: raise RuntimeError('receipt_push_failed:'+(p.stdout+p.stderr)[-1800:])
    return run(['git','rev-parse','HEAD'],cwd=repo,timeout=120).stdout.strip()


def stage(repo:Path,rid:str,op:str,digest:str,name:str,**extra:Any)->str:
    payload={
        'schema':'eira2_transport_terminal_receipt_v6',
        'request_id':rid,
        'operation':op,
        'transport_request_sha256':digest,
        'status':'IN_PROGRESS',
        'ok':None,
        'stage':name,
        'supervisor_pid':os.getpid(),
        'updated_unix':time.time(),
        **extra,
    }
    return publish(repo,rid,payload)


def request_still_current(repo:Path,source_name:str,digest:str,base)->bool:
    sync_repo(repo)
    current=repo/REQUEST_ROOT/source_name
    if not current.is_file():
        return False
    try:
        return base.sha256_bytes(current.read_bytes())==digest
    except OSError:
        return False


def add_full_sources(base,root:Path,request:dict[str,Any],evidence:dict[str,Any])->None:
    rows=[]
    for value in ((request.get('inspection') or {}).get('full_source_paths') or []):
        rel=base.safe_rel(str(value))
        p=(root/rel).resolve(); p.relative_to(root)
        if not p.is_file():
            rows.append({'path':rel,'error':'not_found'}); continue
        raw=p.read_bytes()
        rows.append({'path':rel,'bytes':len(raw),'sha256':base.sha256_bytes(raw),'source':raw.decode('utf-8',errors='replace')})
    if rows: evidence['full_sources']=rows


def process_one(root:Path,runtime:Path,repo:Path,source:Path)->bool:
    base=load_base(repo)
    raw=source.read_bytes()
    digest=base.sha256_bytes(raw)
    request=json.loads(raw.decode('utf-8'))
    rid=str(request.get('request_id') or '')
    op=str(request.get('operation') or '').casefold()
    if request.get('schema')!=REQUEST_SCHEMA or op not in {'inspect','deploy'} or not rid:
        return False
    success=runtime/'state'/f'{digest}.success.json'
    if success.exists(): return False

    started={'schema':'eira2_transport_terminal_receipt_v6','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'STARTED','ok':None,'stage':'single_checkout_execution','supervisor_pid':os.getpid(),'started_unix':time.time()}
    commit=publish(repo,rid,started)
    atomic(runtime/'local_receipts'/f'{rid}.started.json',{**started,'return_transport_commit':commit})

    try:
        sync_repo(repo)
        base=load_base(repo)
        if not request_still_current(repo,source.name,digest,base):
            retired={'schema':'eira2_transport_terminal_receipt_v6','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'SUPERSEDED_ABORTED','ok':True,'superseded':True,'builder_invoked':False,'error':None,'completed_unix':time.time()}
            commit=publish(repo,rid,retired)
            retired['return_transport_commit']=commit
            atomic(success,retired)
            atomic(runtime/'local_receipts'/f'{rid}.terminal.json',retired)
            return True

        stage(repo,rid,op,digest,'WATCHER_AUTHORIZING')
        auth=authorize(root,request)
        stage(repo,rid,op,digest,'WATCHER_AUTHORIZED',watcher_authorized=True,watcher_authorization=auth)

        if op=='inspect':
            inspect_spec=request.get('inspection') or {}
            stage_name='QUALIFYING' if inspect_spec.get('execute_source') else 'INSPECTING'
            stage(repo,rid,op,digest,stage_name,watcher_authorized=True)
            evidence=base.inspect_request(root,request,auth)
            add_full_sources(base,root,request,evidence)
            receipt={'schema':'eira2_transport_terminal_receipt_v6','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'INSPECTION_COMPLETE','ok':True,'watcher_authorized':True,'watcher_authorization':auth,'builder_invoked':False,'evidence':evidence,'error':None,'completed_unix':time.time()}
        else:
            stage(repo,rid,op,digest,'DEPLOYING',watcher_authorized=True)
            evidence=base.deploy_request(root,repo,request,auth)
            receipt={'schema':'eira2_transport_terminal_receipt_v6','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'DEPLOYED_SUCCESSFULLY','ok':True,'watcher_authorized':True,'watcher_authorization':auth,'builder_invoked':bool(evidence.get('builder_invoked')),'deployment':evidence,'completion_sha256':evidence.get('completion_sha256') or evidence.get('after_sha256'),'error':None,'completed_unix':time.time()}
        commit=publish(repo,rid,receipt)
        receipt['return_transport_commit']=commit
        atomic(success,receipt)
        atomic(runtime/'local_receipts'/f'{rid}.terminal.json',receipt)
        return True
    except Exception as exc:
        failure={'schema':'eira2_transport_terminal_receipt_v6','request_id':rid,'operation':op,'transport_request_sha256':digest,'status':'RETRYING','ok':False,'retryable':True,'retry_after_seconds':RETRY_SECONDS,'error':f'{type(exc).__name__}:{exc}'[:5000],'completed_unix':time.time()}
        atomic(runtime/'local_receipts'/f'{rid}.failure.json',failure)
        try: publish(repo,rid,failure)
        except Exception as push_exc:
            failure['publish_error']=f'{type(push_exc).__name__}:{push_exc}'[:4000]
            atomic(runtime/'local_receipts'/f'{rid}.failure.json',failure)
        time.sleep(RETRY_SECONDS)
        return False


def heartbeat_loop(runtime:Path,stop:threading.Event)->None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try: atomic(runtime/'heartbeat.json',{'schema':'eira2_transport_v6_heartbeat','pid':os.getpid(),'unix':time.time(),'stage':'alive'})
        except Exception: pass


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--interval',type=float,default=2.0); args=ap.parse_args()
    root=Path(args.root).resolve()
    runtime=root/'eira_probe'/'transport_runtime_v6'
    repo=runtime/'repo'
    (runtime/'state').mkdir(parents=True,exist_ok=True)
    (runtime/'local_receipts').mkdir(parents=True,exist_ok=True)
    stop=threading.Event(); threading.Thread(target=heartbeat_loop,args=(runtime,stop),daemon=True).start()
    try:
        while True:
            try:
                atomic(runtime/'heartbeat.json',{'schema':'eira2_transport_v6_heartbeat','pid':os.getpid(),'unix':time.time(),'stage':'sync_repo'})
                sync_repo(repo)
                inbox=repo/REQUEST_ROOT
                for source in sorted(inbox.glob('*.json')):
                    atomic(runtime/'heartbeat.json',{'schema':'eira2_transport_v6_heartbeat','pid':os.getpid(),'unix':time.time(),'stage':'request','request_file':source.name})
                    process_one(root,runtime,repo,source)
                    sync_repo(repo)
            except Exception as exc:
                atomic(runtime/'supervisor_error.json',{'schema':'eira2_transport_v6_supervisor_error','pid':os.getpid(),'unix':time.time(),'error':f'{type(exc).__name__}:{exc}'[:5000]})
            time.sleep(max(1.0,args.interval))
    finally:
        stop.set()

if __name__=='__main__': raise SystemExit(main())