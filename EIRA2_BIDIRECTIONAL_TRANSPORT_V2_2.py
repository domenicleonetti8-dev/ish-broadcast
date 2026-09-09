#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA="eira2_bidirectional_transport_v2_2"
REPO_URL="https://github.com/domenicleonetti8-dev/ish-broadcast.git"
DEFAULT_ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
DEFAULT_STATE=Path.home()/'.local'/'state'/'eira2-transport-v2'
IN_LANES=('requests','blueprints','jobs','builds','artifacts')
OUT_LANES=('receipts','jobs','builds','artifacts','diagnostics')
REMOTE_IN=Path('eira2_transport_bus/to_superprobe')
REMOTE_OUT=Path('eira2_transport_bus/from_superprobe')
CONSUMER='EIRA2_BIDIRECTIONAL_BLUEPRINT_CONSUMER_V1.py'

def utc(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def run(cmd,cwd=None,timeout=300): return subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def atomic(p,obj):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}')
    t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def dirs(s):
    for x in IN_LANES: (s/'inbox'/x).mkdir(parents=True,exist_ok=True)
    for x in OUT_LANES: (s/'outbox'/x).mkdir(parents=True,exist_ok=True)
    for x in ('runtime','publish-state','blueprint-state','archive'): (s/x).mkdir(parents=True,exist_ok=True)
def sync_repo(s):
    r=s/'repo'
    if not (r/'.git').is_dir():
        if r.exists(): shutil.rmtree(r)
        p=run(['git','clone','--quiet',REPO_URL,str(r)],timeout=600)
        if p.returncode: raise RuntimeError('git_clone_failed:'+p.stderr[-1000:])
    for c in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','master'],['git','reset','--hard','origin/master']):
        p=run(c,r,300)
        if p.returncode: raise RuntimeError('git_sync_failed:'+p.stderr[-1000:])
    return r
def head(r): return run(['git','rev-parse','origin/master'],r,60).stdout.strip()
def cursor_path(s): return s/'runtime'/'inbound_cursor.txt'
def init_cursor(r,s):
    c=cursor_path(s)
    if not c.exists(): c.write_text(head(r)+'\n')
    return c.read_text().strip()
def changed_inbound(r,old,new):
    if not old or old==new: return []
    p=run(['git','diff','--name-only','--diff-filter=AM',old,new,'--','eira2_transport_bus/to_superprobe'],r,120)
    if p.returncode: raise RuntimeError('cursor_diff_failed:'+p.stderr[-800:])
    return [Path(x.strip()) for x in p.stdout.splitlines() if x.strip()]
def mirror_new(r,s):
    old=init_cursor(r,s); new=head(r); counts={x:0 for x in IN_LANES}
    for rel in changed_inbound(r,old,new):
        parts=rel.parts
        if len(parts)<4: continue
        lane=parts[2]
        if lane not in IN_LANES: continue
        src=r/rel
        if not src.is_file(): continue
        dst=s/'inbox'/lane/src.name
        shutil.copy2(src,dst); counts[lane]+=1
    cursor_path(s).write_text(new+'\n')
    atomic(s/'runtime'/'cursor.json',{'schema':SCHEMA,'from':old,'to':new,'mirrored':counts,'utc':utc()})
    return counts
def publish(r,rels,msg):
    if not rels: return None
    for c in (['git','fetch','--quiet','origin','master'],['git','reset','--hard','origin/master']):
        p=run(c,r,300)
        if p.returncode: raise RuntimeError('publish_sync_failed:'+p.stderr[-1000:])
    p=run(['git','add',*[x.as_posix() for x in rels]],r,120)
    if p.returncode: raise RuntimeError('publish_add_failed:'+p.stderr[-800:])
    if run(['git','diff','--cached','--quiet'],r,120).returncode!=0:
        p=run(['git','-c','user.name=EIRA2 Return Transport','-c','user.email=eira2-return@localhost','commit','--quiet','-m',msg],r,120)
        if p.returncode: raise RuntimeError('publish_commit_failed:'+p.stderr[-1000:])
        p=run(['git','pull','--rebase','--quiet','origin','master'],r,300)
        if p.returncode: raise RuntimeError('publish_rebase_failed:'+p.stderr[-1200:])
        p=run(['git','push','--quiet','origin','master'],r,300)
        if p.returncode: raise RuntimeError('publish_push_failed:'+p.stderr[-1200:])
    return run(['git','rev-parse','HEAD'],r,60).stdout.strip()
def publish_out(r,s):
    staged=[]; rels=[]; counts={x:0 for x in OUT_LANES}
    for lane in OUT_LANES:
        for p in sorted((s/'outbox'/lane).glob('*')):
            if not p.is_file(): continue
            d=sha(p); marker=s/'publish-state'/f'{lane}__{d}.json'
            if marker.exists(): continue
            rel=REMOTE_OUT/lane/p.name; target=r/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target)
            staged.append((lane,p,marker,d)); rels.append(rel); counts[lane]+=1
    if rels:
        commit=publish(r,rels,'Return EIRA2 bidirectional transport payloads')
        for lane,p,m,d in staged: atomic(m,{'schema':SCHEMA,'lane':lane,'name':p.name,'sha256':d,'commit':commit,'utc':utc()})
    return counts
def admission(root):
    rows=[]
    for line in Path('/proc/self/mountinfo').read_text(errors='replace').splitlines():
        x=line.split();
        if len(x)>5 and str(root).startswith(x[4].replace('\\040',' ')): rows.append(line)
    p=run(['ps','-eo','pid=,stat=,comm=,wchan='],timeout=30); ds=[]
    for line in p.stdout.splitlines():
        x=line.split(None,3)
        if len(x)>=3 and x[1].startswith('D'): ds.append({'pid':x[0],'stat':x[1],'comm':x[2],'wchan':x[3] if len(x)>3 else ''})
    bad=[x for x in ds if 'ntfs' in x['wchan'].lower()]
    return bool(rows and not bad),{'mount_rows':rows[-8:],'d_state':ds,'ntfs_blocked':bad}
def pending(s): return len(list((s/'inbox'/'blueprints').glob('*.json')))
def worker_tick(r,root,s):
    pf=s/'runtime'/'worker.pid'
    if pf.exists():
        try:
            pid=int(pf.read_text().strip()); os.kill(pid,0); return {'state':'RUNNING','pid':pid}
        except Exception: pf.unlink(missing_ok=True)
    if pending(s)==0: return {'state':'IDLE'}
    ok,ev=admission(root)
    if not ok: return {'state':'STORAGE_BLOCKED','evidence':ev}
    log=(s/'runtime'/'worker.log').open('ab')
    p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--root',str(root),'--state',str(s),'blueprint-once'],cwd=str(Path.home()),stdout=log,stderr=subprocess.STDOUT,start_new_session=False)
    pf.write_text(str(p.pid)+'\n'); atomic(s/'runtime'/'worker.json',{'schema':SCHEMA,'state':'STARTED','pid':p.pid,'utc':utc()}); return {'state':'STARTED','pid':p.pid}
def blueprint_once(root,s):
    r=sync_repo(s); path=r/CONSUMER
    spec=importlib.util.spec_from_file_location('eira2_bp',path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rows=mod.process_once(root,s/'blueprint-work',s/'blueprint-state')
    for p in list((s/'inbox'/'blueprints').glob('*.json')):
        try: p.rename(s/'archive'/p.name)
        except OSError: pass
    atomic(s/'runtime'/'last_blueprint_run.json',{'schema':SCHEMA,'utc':utc(),'results':rows}); return 0
def status(s,root):
    ok,ev=admission(root); c=cursor_path(s).read_text().strip() if cursor_path(s).exists() else None
    return {'schema':SCHEMA,'utc':utc(),'control_plane':str(s),'control_plane_on_live_drive':str(s).startswith(str(root)),'live_root':str(root),'storage_admitted':ok,'storage_evidence':ev,'cursor':c,'pending_blueprints':pending(s),'inbox':{x:len(list((s/'inbox'/x).glob('*'))) for x in IN_LANES},'outbox':{x:len(list((s/'outbox'/x).glob('*'))) for x in OUT_LANES}}
def once(root,s):
    dirs(s); r=sync_repo(s); incoming=mirror_new(r,s); worker=worker_tick(r,root,s); r=sync_repo(s); outgoing=publish_out(r,s); st=status(s,root); h={'schema':SCHEMA,'utc':utc(),'incoming':incoming,'worker':worker,'outgoing':outgoing,'status':st}; atomic(s/'runtime'/'heartbeat.json',h); return h
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default=str(DEFAULT_ROOT)); ap.add_argument('--state',default=str(DEFAULT_STATE)); sp=ap.add_subparsers(dest='cmd',required=True)
    sp.add_parser('once'); d=sp.add_parser('daemon'); d.add_argument('--interval',type=float,default=3.0); sp.add_parser('status'); sp.add_parser('blueprint-once'); b=sp.add_parser('baseline'); b.add_argument('--clear-inbox',action='store_true')
    a=ap.parse_args(); root=Path(a.root).expanduser(); s=Path(a.state).expanduser(); dirs(s)
    if a.cmd=='status': print(json.dumps(status(s,root),indent=2)); return 0
    if a.cmd=='blueprint-once': return blueprint_once(root,s)
    if a.cmd=='baseline':
        r=sync_repo(s); cursor_path(s).write_text(head(r)+'\n')
        if a.clear_inbox:
            for lane in IN_LANES:
                for p in (s/'inbox'/lane).glob('*'):
                    if p.is_file(): p.rename(s/'archive'/f'{lane}__{p.name}')
        print(json.dumps({'schema':SCHEMA,'baseline':head(r),'historical_replay':False},indent=2)); return 0
    if a.cmd=='once': print(json.dumps(once(root,s),indent=2)); return 0
    while True:
        try: print(json.dumps(once(root,s),separators=(',',':')),flush=True)
        except Exception as exc: atomic(s/'runtime'/'last_error.json',{'schema':SCHEMA,'utc':utc(),'error':f'{type(exc).__name__}:{exc}'})
        time.sleep(max(1.0,a.interval))
if __name__=='__main__': raise SystemExit(main())
