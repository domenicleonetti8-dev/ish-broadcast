#!/usr/bin/env python3
# Audit-only draft. NOT DEPLOYED.
# Bidirectional command/evidence bridge design: GitHub bus <-> Pi ext4 control plane <-> LIVE gated executor.

from __future__ import annotations
import hashlib,json,os,re,subprocess,time
from pathlib import Path

SCHEMA='eira2_orin_bridge_v1'
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
STATE=Path.home()/'.local/state/eira2-orin-bridge'
ALLOWED_OPS={'inspect','deploy','fetch','status'}
SAFE_ID=re.compile(r'^[A-Za-z0-9._-]{1,128}$')

def atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(tmp,path)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def safe_rel(v):
    p=Path(str(v or ''))
    if p.is_absolute() or '..' in p.parts or not p.parts: raise ValueError('unsafe_path')
    return p

def admission():
    mounts=Path('/proc/self/mountinfo').read_text(errors='replace')
    mounted=str(ROOT) in mounts or '/media/domenicleonetti/easystore' in mounts
    p=subprocess.run(['ps','-eo','pid=,stat=,comm=,wchan='],text=True,capture_output=True,timeout=10)
    blocked=[x for x in p.stdout.splitlines() if len(x.split())>1 and x.split()[1].startswith('D') and 'ntfs' in x.lower()]
    return mounted and not blocked,{'mounted':mounted,'ntfs_d_state':blocked}

def validate(job):
    if job.get('schema')!=SCHEMA: raise ValueError('schema')
    jid=str(job.get('job_id') or '')
    if not SAFE_ID.fullmatch(jid): raise ValueError('job_id')
    op=str(job.get('operation') or '')
    if op not in ALLOWED_OPS: raise ValueError('operation')
    return jid,op

def execute(job):
    jid,op=validate(job); ok,storage=admission()
    receipt={'schema':SCHEMA+'_receipt','job_id':jid,'operation':op,'storage':storage,'started':time.time()}
    if op=='status': receipt['ok']=True
    elif op in {'inspect','fetch'}:
        rel=safe_rel(job['path']); p=(ROOT/rel).resolve(); p.relative_to(ROOT)
        if not p.is_file(): raise FileNotFoundError(str(rel))
        receipt.update(ok=True,path=rel.as_posix(),sha256=sha(p),bytes=p.stat().st_size)
    elif op=='deploy':
        if not ok: raise RuntimeError('storage_not_admitted')
        # Deliberately no direct write authority here. Deployment MUST hand off to the
        # existing exact-inbox blueprint lane -> Watcher -> Builder -> post-Superprobe.
        receipt.update(ok=True,handoff='exact_inbox_blueprint_lane',direct_live_write=False)
    receipt['completed']=time.time(); return receipt

if __name__=='__main__':
    STATE.mkdir(parents=True,exist_ok=True)
    print(json.dumps({'schema':SCHEMA,'state':str(STATE),'root':str(ROOT),'direct_live_write':False},indent=2))
