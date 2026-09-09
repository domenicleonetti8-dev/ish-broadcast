#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA='eira2_canonical_build_bridge_v1'
BLUEPRINT_SCHEMA='eira2_canonical_build_blueprint_v1'
RECEIPT_SCHEMA='eira2_canonical_build_receipt_v1'
REPO_URL='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
DEFAULT_ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
DEFAULT_STATE=Path.home()/'.local'/'state'/'eira2-canonical-build-bridge'
REMOTE_IN=Path('eira2_transport_bus/to_superprobe/blueprints')
REMOTE_OUT=Path('eira2_transport_bus/from_superprobe/receipts')

def utc(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def run(cmd,cwd=None,timeout=300): return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)
def atomic_json(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(tmp,path)
def sha256_bytes(data): return hashlib.sha256(data).hexdigest()
def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def safe_rel(value):
    p=PurePosixPath(str(value or '').strip())
    if not p.parts or p.is_absolute() or '..' in p.parts: raise RuntimeError(f'unsafe_path:{value}')
    return p.as_posix()
def sync_repo(state):
    repo=state/'repo'
    if not (repo/'.git').is_dir():
        if repo.exists(): shutil.rmtree(repo)
        p=run(['git','clone','--quiet',REPO_URL,str(repo)],timeout=600)
        if p.returncode: raise RuntimeError('git_clone_failed:'+p.stderr[-1000:])
    for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','master'],['git','reset','--hard','origin/master']):
        p=run(cmd,repo,300)
        if p.returncode: raise RuntimeError('git_sync_failed:'+p.stderr[-1000:])
    return repo

def load_json(path):
    obj=json.loads(Path(path).read_text())
    if not isinstance(obj,dict): raise RuntimeError('json_not_object')
    return obj

def load_component(root,rel,name):
    path=root/rel
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f'import_failed:{path}')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def validate_blueprint(bp):
    if bp.get('schema')!=BLUEPRINT_SCHEMA: raise RuntimeError('blueprint_schema_mismatch')
    bid=str(bp.get('blueprint_id') or '')
    if not bid: raise RuntimeError('blueprint_id_missing')
    src=bp.get('source') or {}; tgt=bp.get('target') or {}
    commit=str(src.get('commit') or '')
    if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise RuntimeError('source_commit_invalid')
    source_path=safe_rel(src.get('path')); target_path=safe_rel(tgt.get('path'))
    expected=str(src.get('sha256') or '').lower()
    if len(expected)!=64: raise RuntimeError('source_sha256_invalid')
    return bid,commit,source_path,target_path,expected

def git_blob(repo,commit,path):
    p=run(['git','show',f'{commit}:{path}'],repo,120)
    if p.returncode: raise RuntimeError('source_blob_missing:'+p.stderr[-800:])
    return p.stdout.encode()

def storage_admission(root):
    rows=[]
    for line in Path('/proc/self/mountinfo').read_text(errors='replace').splitlines():
        x=line.split()
        if len(x)>5 and str(root).startswith(x[4].replace('\\040',' ')): rows.append(line)
    p=run(['ps','-eo','pid=,stat=,comm=,wchan='],timeout=30); bad=[]
    for line in p.stdout.splitlines():
        x=line.split(None,3)
        if len(x)>=4 and x[1].startswith('D') and 'ntfs' in x[3].lower(): bad.append(line)
    if not rows or bad: raise RuntimeError('storage_not_admitted')

def process(root,state,bp_path):
    started=time.time(); storage_admission(root); repo=sync_repo(state); bp=load_json(bp_path)
    bid,commit,source_path,target_path,expected=validate_blueprint(bp)
    payload=git_blob(repo,commit,source_path)
    if sha256_bytes(payload)!=expected: raise RuntimeError('payload_sha256_mismatch')
    target=(root/target_path).resolve(); target.relative_to(root)
    stage=state/'stage'/bid; shutil.rmtree(stage,ignore_errors=True); stage.mkdir(parents=True)
    staged=stage/Path(target_path).name; staged.write_bytes(payload)
    if staged.suffix=='.py':
        q=run([sys.executable,'-m','py_compile',str(staged)],timeout=60)
        if q.returncode: raise RuntimeError('payload_compile_failed:'+q.stderr[-800:])
    watcher=load_component(root,Path('extensions/repair_watcher_ai/plugin.py'),'eira2_canonical_watcher')
    builder=load_component(root,Path('tools/eira2_builder_probe.py'),'eira2_canonical_builder')
    probe=load_component(root,Path('tools/eira2_superprobe_engine.py'),'eira2_canonical_superprobe')
    auth=watcher.authorize_build({'schema':'eira2_watcher_build_request_v1','blueprint_id':bid,'target_path':target_path,'payload_sha256':expected})
    if not isinstance(auth,dict) or auth.get('authorized') is not True: raise RuntimeError('watcher_denied:'+json.dumps(auth,sort_keys=True)[-1000:])
    before=sha256_file(target) if target.is_file() else None
    br=builder.apply_build(root=root,target_path=target_path,staged_path=str(staged),expected_before_sha256=str((bp.get('target') or {}).get('expected_before_sha256') or ''),expected_after_sha256=expected)
    if not isinstance(br,dict) or br.get('ok') is not True: raise RuntimeError('builder_failed:'+json.dumps(br,sort_keys=True)[-1200:])
    report=probe.run(root,root/'eira_probe'/'eira2_superprobe_report.json',root/'eira_probe'/'superprobe_evidence')
    if not isinstance(report,dict) or report.get('ok') is not True: raise RuntimeError('superprobe_failed:'+json.dumps(report,sort_keys=True)[-1200:])
    after=sha256_file(target) if target.is_file() else None
    if after!=expected: raise RuntimeError('post_build_hash_mismatch')
    receipt={'schema':RECEIPT_SCHEMA,'ok':True,'status':'DEPLOYED','blueprint_id':bid,'target_path':target_path,'before_sha256':before,'after_sha256':after,'watcher':auth,'builder':br,'superprobe':{'ok':report.get('ok'),'schema':report.get('schema'),'evidence_fingerprint':report.get('evidence_bundle_fingerprint_sha256')},'elapsed_seconds':round(time.time()-started,6),'utc':utc()}
    local=state/'receipts'/f'{bid}.json'; atomic_json(local,receipt); return local,receipt

def publish_receipt(state,local):
    repo=sync_repo(state); rel=REMOTE_OUT/local.name; dest=repo/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(local,dest)
    for cmd in (['git','add',rel.as_posix()],['git','-c','user.name=EIRA2 Canonical Bridge','-c','user.email=eira2-bridge@localhost','commit','--quiet','-m',f'Return canonical build receipt {local.stem}']):
        p=run(cmd,repo,120)
        if p.returncode and 'nothing to commit' not in (p.stdout+p.stderr): raise RuntimeError('receipt_commit_failed:'+p.stderr[-800:])
    p=run(['git','pull','--rebase','--quiet','origin','master'],repo,300)
    if p.returncode: raise RuntimeError('receipt_rebase_failed:'+p.stderr[-800:])
    p=run(['git','push','--quiet','origin','master'],repo,300)
    if p.returncode: raise RuntimeError('receipt_push_failed:'+p.stderr[-800:])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default=str(DEFAULT_ROOT)); ap.add_argument('--state',default=str(DEFAULT_STATE)); ap.add_argument('--blueprint',required=True); ap.add_argument('--publish',action='store_true'); a=ap.parse_args()
    root=Path(a.root).expanduser().resolve(); state=Path(a.state).expanduser().resolve(); state.mkdir(parents=True,exist_ok=True)
    try:
        local,receipt=process(root,state,Path(a.blueprint))
        if a.publish: publish_receipt(state,local)
        print(json.dumps(receipt,indent=2)); return 0
    except Exception as exc:
        err={'schema':RECEIPT_SCHEMA,'ok':False,'status':'FAILED','error':f'{type(exc).__name__}:{exc}','utc':utc()}; print(json.dumps(err,indent=2),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
