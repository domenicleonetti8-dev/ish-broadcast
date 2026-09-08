#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
EXPECTED_NEURAL='9f056a89d292179b924d3431ed5bcde3c3ec1d9940ab43b2af8a95a301e2a620'
CMD_SUFFIX=f'-m eira2 --live --root {ROOT}'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def eligible():
    p=subprocess.run(['ps','-eo','pid=,args='],text=True,capture_output=True,check=False)
    rows=[]
    for line in p.stdout.splitlines():
        s=line.strip()
        if not s: continue
        parts=s.split(None,1)
        if len(parts)!=2: continue
        pid=int(parts[0]); args=parts[1]
        if ('python3 -m eira2 --live --root '+str(ROOT)) in args or (sys.executable+' -m eira2 --live --root '+str(ROOT)) in args:
            rows.append((pid,args))
    return rows
def port_open():
    try:
        with socket.create_connection(('127.0.0.1',8782),timeout=1): return True
    except OSError: return False
def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8782/health',timeout=5) as r:
            raw=r.read(); return {'ok':getattr(r,'status',200)==200,'status':getattr(r,'status',200),'body':raw.decode(errors='replace')[:12000]}
    except Exception as e: return {'ok':False,'error':f'{type(e).__name__}:{e}'}
out={'schema':'eira2_controlled_runtime_reload_v1','ok':False,'mutates_source_files':False,'runtime_process_mutation':True}
try:
    neural=ROOT/'eira2/neural/organism.py'; observed=sha(neural); out['neural_sha256']=observed
    if observed!=EXPECTED_NEURAL: raise RuntimeError('neural_hash_guard_failed:'+observed)
    before=eligible(); out['before']=before
    if len(before)>1: raise RuntimeError('multiple_canonical_runtime_processes')
    if len(before)==1:
        old=before[0][0]; os.kill(old,signal.SIGTERM); out['terminated_pid']=old
        deadline=time.time()+25
        while time.time()<deadline and Path(f'/proc/{old}').exists(): time.sleep(.25)
        if Path(f'/proc/{old}').exists(): raise RuntimeError('canonical_runtime_did_not_exit_on_TERM')
    deadline=time.time()+15
    while time.time()<deadline and port_open(): time.sleep(.25)
    log=ROOT/'eira_probe'/'canonical_live_controlled_reload_v1.log'; log.parent.mkdir(parents=True,exist_ok=True)
    fh=open(log,'ab',buffering=0)
    proc=subprocess.Popen([sys.executable,'-m','eira2','--live','--root',str(ROOT)],cwd=str(ROOT),stdout=fh,stderr=fh,start_new_session=True)
    out['spawned_pid']=proc.pid; out['log']=str(log)
    deadline=time.time()+150; h={'ok':False}
    while time.time()<deadline:
        if proc.poll() is not None: break
        if port_open():
            h=health()
            if h.get('ok'): break
        time.sleep(2)
    out['health']=h; out['after']=eligible(); out['port_8782_open']=port_open(); out['spawn_returncode']=proc.poll()
    if proc.poll() is not None: raise RuntimeError('new_runtime_exited:'+str(proc.returncode))
    if not h.get('ok'): raise RuntimeError('new_runtime_health_not_ready')
    if len(out['after'])!=1 or out['after'][0][0]!=proc.pid: raise RuntimeError('canonical_runtime_singleton_guard_failed')
    out['ok']=True
except Exception as e:
    out['error']=f'{type(e).__name__}:{e}'
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out.get('ok') else 1)
