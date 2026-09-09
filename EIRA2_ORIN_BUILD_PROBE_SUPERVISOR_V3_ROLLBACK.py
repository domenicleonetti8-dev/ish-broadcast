#!/usr/bin/env python3
from __future__ import annotations
import fcntl,json,os,signal,subprocess,sys,time
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe'/'orin_build_probe_supervisor_v3'
LOCK=STATE/'supervisor.lock'; STATUS=STATE/'status.json'; REQUEST=STATE/'upgrade_request.json'
DEFAULT=ROOT/'tools'/'eira2_orin_build_probe.py'; ACTIVE=STATE/'active.json'; LAST_GOOD=STATE/'last_good.json'; LOG=STATE/'probe.log'
HEARTBEATS=[ROOT/'eira_probe'/'orin_build_probe_v2'/'heartbeat.json',ROOT/'eira_probe'/'orin_build_probe_v1'/'heartbeat.json']
CHECK=5.0; STARTUP_GRACE=120.0; STALE=45.0

def atom(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix('.tmp'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def status(**kw): atom(STATUS,{'schema':'eira2_orin_build_probe_supervisor_v3','unix':time.time(),**kw})
def readj(p):
 try:return json.loads(p.read_text())
 except Exception:return None

def hb():
 best=None
 for p in HEARTBEATS:
  d=readj(p)
  if isinstance(d,dict) and d.get('unix'):
   if best is None or float(d['unix'])>float(best[1].get('unix',0)): best=(p,d)
 return best

def stop(proc):
 if proc is None or proc.poll() is not None:return
 proc.terminate()
 try:proc.wait(timeout=8)
 except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

def valid_candidate(rel,sha):
 try:
  p=(ROOT/rel).resolve()
  if ROOT not in p.parents or p.suffix!='.py' or not p.is_file():return None
  raw=p.read_bytes(); import hashlib
  if hashlib.sha256(raw).hexdigest()!=sha:return None
  compile(raw.decode('utf-8'),str(p),'exec'); return p
 except Exception:return None

def selected():
 d=readj(ACTIVE)
 if isinstance(d,dict):
  p=valid_candidate(d.get('path',''),d.get('sha256',''))
  if p:return p,d
 return DEFAULT,{'path':str(DEFAULT.relative_to(ROOT)),'sha256':None,'source':'default'}

def main():
 STATE.mkdir(parents=True,exist_ok=True); lf=LOCK.open('w')
 try:fcntl.flock(lf,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError: status(ok=True,phase='already_supervised'); return 0
 if not DEFAULT.is_file(): status(ok=False,phase='default_probe_missing'); return 2
 stopping=False; proc=None; launched=0.0; mode=None
 def sig(*_):
  nonlocal stopping; stopping=True
 signal.signal(signal.SIGTERM,sig);signal.signal(signal.SIGINT,sig)
 with LOG.open('ab',buffering=0) as log:
  while not stopping:
   req=readj(REQUEST)
   if isinstance(req,dict):
    cand=valid_candidate(req.get('candidate',''),req.get('sha256',''))
    if cand:
     stop(proc); proc=None; atom(ACTIVE,{'path':str(cand.relative_to(ROOT)),'sha256':req['sha256'],'promoted_unix':time.time(),'request_id':req.get('id')}); REQUEST.unlink(missing_ok=True); mode='candidate'; status(ok=True,phase='candidate_staged',candidate=str(cand.relative_to(ROOT)))
    else:
     REQUEST.rename(STATE/f'rejected_upgrade_{int(time.time())}.json'); status(ok=False,phase='candidate_rejected')
   if proc is None or proc.poll() is not None:
    path,meta=selected(); proc=subprocess.Popen([sys.executable,str(path)],cwd=str(ROOT),stdout=log,stderr=log,start_new_session=True); launched=time.time(); mode='candidate' if path!=DEFAULT else 'default'; status(ok=True,phase='started',pid=proc.pid,probe=str(path.relative_to(ROOT)),mode=mode)
    time.sleep(CHECK); continue
   h=hb(); now=time.time(); age=(now-float(h[1].get('unix',0))) if h else None; healthy=bool(h and h[1].get('ok') and age<=STALE)
   if healthy:
    if mode=='candidate': atom(LAST_GOOD,readj(ACTIVE) or {}); status(ok=True,phase='healthy_promoted',pid=proc.pid,heartbeat_age=age,mode=mode)
    else: status(ok=True,phase='healthy',pid=proc.pid,heartbeat_age=age,mode=mode)
    time.sleep(CHECK); continue
   if now-launched<=STARTUP_GRACE:
    status(ok=True,phase='starting',pid=proc.pid,heartbeat_age=age,mode=mode); time.sleep(CHECK); continue
   oldmode=mode; stop(proc); proc=None
   if oldmode=='candidate': ACTIVE.unlink(missing_ok=True); status(ok=False,phase='candidate_failed_rolled_back')
   else: status(ok=False,phase='default_stale_restart')
   time.sleep(2)
 stop(proc); status(ok=True,phase='stopped'); return 0
if __name__=='__main__': raise SystemExit(main())
