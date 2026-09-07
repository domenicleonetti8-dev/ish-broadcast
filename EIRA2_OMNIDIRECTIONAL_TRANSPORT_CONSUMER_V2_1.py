#!/usr/bin/env python3
from __future__ import annotations

import argparse, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

REPO_URL='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
BASE_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py'
SELF_NAME='EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_1.py'
REQUEST_ROOT=Path('eira2_transport_bus/to_superprobe/requests')


def run(cmd:list[str],*,cwd:Path|None=None,timeout:int=300)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)


def sync_repo(work:Path)->None:
    if not (work/'.git').is_dir():
        if work.exists(): shutil.rmtree(work)
        p=run(['git','clone','--quiet',REPO_URL,str(work)],timeout=300)
        if p.returncode: raise RuntimeError('git_clone_failed:'+p.stderr[-800:])
    for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','master'],['git','reset','--hard','origin/master']):
        p=run(cmd,cwd=work,timeout=300)
        if p.returncode: raise RuntimeError('git_sync_failed:'+p.stderr[-800:])


def sha256_bytes(data:bytes)->str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def self_refresh(work:Path)->None:
    remote=work/SELF_NAME; current=Path(__file__).resolve()
    if not remote.is_file(): return
    if sha256_bytes(remote.read_bytes())==sha256_bytes(current.read_bytes()): return
    tmp=current.with_name(current.name+f'.refresh.{os.getpid()}'); tmp.write_bytes(remote.read_bytes()); os.replace(tmp,current)
    os.execv(sys.executable,[sys.executable,str(current),*sys.argv[1:]])


def load_base(work:Path):
    path=work/BASE_NAME
    spec=importlib.util.spec_from_file_location('eira2_transport_v2_base',path)
    if spec is None or spec.loader is None: raise RuntimeError('base_consumer_import_failed')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def load_watcher(root:Path):
    path=root/'extensions'/'repair_watcher_ai'/'plugin.py'
    spec=importlib.util.spec_from_file_location('eira2_transport_watcher_v21',path)
    if spec is None or spec.loader is None: raise RuntimeError('watcher_import_failed')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def legacy_inspection_authorize(root:Path,request:dict[str,Any])->dict[str,Any]:
    watcher=load_watcher(root)
    fn=getattr(watcher,'authorize_transport_request',None)
    if callable(fn):
        result=fn(request)
        if not isinstance(result,dict) or result.get('authorized') is not True:
            raise RuntimeError('watcher_rejected:'+json.dumps(result,sort_keys=True)[-1200:])
        return result
    inspect_once=getattr(watcher,'inspect_once',None)
    if not callable(inspect_once): raise RuntimeError('watcher_inspection_authority_unavailable')
    result=inspect_once()
    if not isinstance(result,dict) or result.get('ok') is not True:
        raise RuntimeError('watcher_read_only_inspection_rejected:'+json.dumps(result,sort_keys=True)[-1200:])
    return {'authorized':True,'authorized_by':'repair_watcher_ai','watcher_version':getattr(watcher,'VERSION','legacy'),'operation':'inspect','legacy_read_only_authorization':True,'watcher_result':result}


def publish_started(base,work:Path,request:dict[str,Any],digest:str)->None:
    rid=str(request.get('request_id') or '')
    receipt={'schema':'eira2_transport_terminal_receipt_v1','request_id':rid,'operation':request.get('operation'),'transport_request_sha256':digest,'status':'STARTED','ok':None,'started_unix':time.time(),'stage':'watcher_authorization'}
    base.publish(work,rid,receipt)


def add_full_sources(base,root:Path,request:dict[str,Any],evidence:dict[str,Any])->None:
    spec=request.get('inspection') or {}
    rows=[]
    for value in spec.get('full_source_paths') or []:
        rel=base.safe_rel(str(value))
        path=(root/rel).resolve(); path.relative_to(root)
        if not path.is_file():
            rows.append({'path':rel,'error':'not_found'})
            continue
        raw=path.read_bytes()
        rows.append({'path':rel,'bytes':len(raw),'sha256':base.sha256_bytes(raw),'source':raw.decode('utf-8',errors='replace')})
    if rows:
        evidence['full_sources']=rows
        canonical=dict(evidence); canonical.pop('evidence_sha256',None)
        evidence['evidence_sha256']=base.sha256_bytes((json.dumps(canonical,sort_keys=True,separators=(',',':'))+'\n').encode())


def process_one(base,root:Path,work:Path,src:Path,state:Path)->dict[str,Any]:
    raw=src.read_bytes(); digest=base.sha256_bytes(raw); request=json.loads(raw.decode())
    rid=str(request.get('request_id') or ''); op=str(request.get('operation') or '').casefold()
    done=state/f'{digest}.json'
    if done.exists(): return {'already_handled':True,'request_id':rid}
    publish_started(base,work,request,digest)
    sync_repo(work); src=work/REQUEST_ROOT/src.name
    if op=='inspect':
        receipt={'schema':'eira2_transport_terminal_receipt_v1','request_id':rid,'operation':'inspect','transport_request_sha256':digest,'started_unix':time.time()}
        try:
            auth=legacy_inspection_authorize(root,request)
            receipt['watcher_authorized']=True; receipt['watcher_authorization']=auth; receipt['stage']='inspection'
            evidence=base.inspect_request(root,request,auth); add_full_sources(base,root,request,evidence)
            receipt.update(status='INSPECTION_COMPLETE',ok=True,builder_invoked=False,evidence=evidence,evidence_sha256=evidence['evidence_sha256'],error=None)
        except Exception as exc:
            receipt.update(status='REQUEST_FAILED',ok=False,builder_invoked=False,error=f'{type(exc).__name__}:{exc}'[:2400])
        receipt['completed_unix']=time.time(); commit=base.publish(work,rid,receipt); receipt['return_transport_commit']=commit; base.atomic_json(done,receipt); return receipt
    return base.process_request(root,work,src,state)


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--interval',type=float,default=2.0); ap.add_argument('--once',action='store_true'); a=ap.parse_args()
    root=Path(a.root).resolve(); runtime=root/'eira_probe'/'transport_runtime_v2_1'; work=runtime/'repo'; state=runtime/'state'; state.mkdir(parents=True,exist_ok=True)
    while True:
        try:
            sync_repo(work); self_refresh(work); base=load_base(work); inbox=work/REQUEST_ROOT
            rows=[]
            for src in inbox.glob('*.json'):
                try:
                    req=json.loads(src.read_text(encoding='utf-8')); priority=0 if str(req.get('operation') or '').casefold()=='inspect' else 1
                except Exception: priority=2
                rows.append((priority,src.name,src))
            for _,_,src in sorted(rows):
                try: process_one(base,root,work,src,state)
                finally: sync_repo(work); base=load_base(work)
        except Exception as exc:
            runtime.mkdir(parents=True,exist_ok=True); (runtime/'consumer_error.log').write_text(f'{time.time()} {type(exc).__name__}:{exc}\n',encoding='utf-8')
        if a.once: return 0
        time.sleep(max(1.0,a.interval))

if __name__=='__main__': raise SystemExit(main())
