#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,queue,shutil,subprocess,threading,time

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe/orin_worker_v4'
REPO=Path('/tmp/eira2_orin_worker_v4_repo')
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
CURRENT_REL=Path('eira2_portal/current.json')
OUT='eira2_portal/outbox'
TELE='eira2_portal/telemetry'
SCHEMA='eira2_orin_worker_receipt_v4'
PUBLISH_Q=queue.Queue(); STOP=threading.Event(); REPO_LOCK=threading.Lock()

def rr(cmd,cwd=None,timeout=600,check=True):
 p=subprocess.run(cmd,cwd=str(cwd or ROOT),text=True,capture_output=True,timeout=timeout)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2000:])
 return p

def safe(v):
 p=(ROOT/str(v or '.')).resolve()
 if p!=ROOT and ROOT not in p.parents: raise ValueError('outside_eira_live')
 return p

def sha(b): return hashlib.sha256(b).hexdigest()

def jwrite(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+'.tmp'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)

def heartbeat(**v): jwrite(STATE/'heartbeat.json',{'schema':'eira2_orin_worker_heartbeat_v4','pid':os.getpid(),'unix':time.time(),**v})

def backup(rid,p):
 if not p.exists() or not p.is_file(): return None
 rel=p.relative_to(ROOT); dst=STATE/'backups'/rid/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst); return str(dst.relative_to(ROOT))

def execute(c):
 rid=str(c.get('id','')).strip(); op=str(c.get('op','')).strip(); r={'schema':SCHEMA,'id':rid,'op':op,'root':str(ROOT)}
 if not rid: raise ValueError('missing_id')
 if op=='list':
  p=safe(c.get('path')); lim=min(max(int(c.get('limit',500)),1),5000)
  r.update(ok=True,path=str(p.relative_to(ROOT)) if p!=ROOT else '.',items=[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:lim]])
 elif op=='read':
  p=safe(c.get('path')); b=p.read_bytes(); m=min(max(int(c.get('max_bytes',500000)),1),2000000)
  r.update(ok=True,path=str(p.relative_to(ROOT)),size=len(b),sha256=sha(b),text=b[:m].decode('utf-8','replace'),truncated=len(b)>m)
 elif op=='write':
  p=safe(c.get('path')); data=str(c.get('text','')).encode(); p.parent.mkdir(parents=True,exist_ok=True); before=p.read_bytes() if p.is_file() else None; bak=backup(rid,p); tmp=p.with_name(p.name+'.orin_tmp'); tmp.write_bytes(data); os.replace(tmp,p)
  comp=None
  if p.suffix=='.py':
   q=rr(['python3','-m','py_compile',str(p)],timeout=60,check=False); comp={'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
   if q.returncode!=0:
    if before is None:p.unlink(missing_ok=True)
    else:p.write_bytes(before)
    raise RuntimeError('python_compile_failed_rolled_back:'+q.stderr[-1200:])
  r.update(ok=True,path=str(p.relative_to(ROOT)),backup=bak,before_sha256=sha(before) if before is not None else None,after_sha256=sha(data),bytes=len(data),compile=comp)
 elif op=='compile':
  p=safe(c.get('path')); q=rr(['python3','-m','py_compile',str(p)],timeout=60,check=False); r.update(ok=q.returncode==0,path=str(p.relative_to(ROOT)),returncode=q.returncode,stdout=q.stdout,stderr=q.stderr)
 else: raise ValueError('unsupported_op')
 r['unix']=time.time(); return r

def sync_repo_locked():
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  rr(['git','clone','--quiet',ORIGIN,str(REPO)],timeout=600)
 for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','-B','orin_worker_runtime','origin/master'],['git','reset','--hard','origin/master']): rr(cmd,REPO,600)

def publish_and_get_command(items):
 with REPO_LOCK:
  sync_repo_locked(); changed=[]
  for rel,obj in items:
   p=REPO/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); changed.append(str(rel))
  if changed:
   rr(['git','add',*changed],REPO,120)
   if rr(['git','diff','--cached','--quiet'],REPO,120,False).returncode!=0:
    rr(['git','-c','user.name=EIRA Orin Worker','-c','user.email=eira-orin-worker@localhost','commit','--quiet','-m','Orin worker V4 tether update'],REPO,120)
    rr(['git','pull','--rebase','--quiet','origin','master'],REPO,600); rr(['git','push','--quiet','origin','HEAD:master'],REPO,600)
    sync_repo_locked()
  cp=REPO/CURRENT_REL
  return json.loads(cp.read_text()) if cp.is_file() else None, rr(['git','rev-parse','HEAD'],REPO,120).stdout.strip()

def enqueue(rel,obj): PUBLISH_Q.put((Path(rel),obj))

def filesystem_probe():
 while not STOP.is_set():
  try:
   items=[]
   for p in sorted(ROOT.iterdir()):
    if p.name=='.git': continue
    try: items.append({'name':p.name,'type':'dir' if p.is_dir() else 'file','size':p.stat().st_size if p.is_file() else None,'mtime':p.stat().st_mtime})
    except Exception: pass
   snap={'schema':'eira2_probe_filesystem_v2','unix':time.time(),'root':str(ROOT),'items':items[:500]}; jwrite(STATE/'probes/filesystem.json',snap); enqueue(f'{TELE}/filesystem_latest.json',snap)
  except Exception as e: jwrite(STATE/'probes/filesystem_error.json',{'unix':time.time(),'error':f'{type(e).__name__}:{e}'})
  STOP.wait(15)

def runtime_probe():
 while not STOP.is_set():
  try:
   q=rr(['ps','-eo','pid,ppid,stat,etime,cmd','--sort=pid'],timeout=20,check=False); lines=[x for x in q.stdout.splitlines() if 'EIRA/LIVE' in x or 'eira2_' in x or 'main.py' in x]
   snap={'schema':'eira2_probe_runtime_v2','unix':time.time(),'loadavg':Path('/proc/loadavg').read_text().strip() if Path('/proc/loadavg').exists() else None,'processes':lines[:300]}; jwrite(STATE/'probes/runtime.json',snap); enqueue(f'{TELE}/runtime_latest.json',snap)
  except Exception as e: jwrite(STATE/'probes/runtime_error.json',{'unix':time.time(),'error':f'{type(e).__name__}:{e}'})
  STOP.wait(10)

def library_probe():
 roots=[ROOT/'eira2',ROOT/'extensions',ROOT/'manifests',ROOT/'var']
 while not STOP.is_set():
  try:
   hits=[]
   for base in roots:
    if not base.exists(): continue
    for dirpath,dirnames,filenames in os.walk(base):
     p=Path(dirpath)
     try: depth=len(p.relative_to(base).parts)
     except Exception: depth=99
     if depth>=6: dirnames[:]=[]
     for name in list(dirnames)+filenames:
      low=name.lower()
      if any(k in low for k in ('library','textbook','book','seed','chunk','corpus','complete')):
       q=p/name
       try: hits.append({'path':str(q.relative_to(ROOT)),'type':'dir' if q.is_dir() else 'file','size':q.stat().st_size if q.is_file() else None})
       except Exception: pass
       if len(hits)>=1000: break
     if len(hits)>=1000: break
    if len(hits)>=1000: break
   snap={'schema':'eira2_probe_library_v2','unix':time.time(),'candidates':hits}; jwrite(STATE/'probes/library.json',snap); enqueue(f'{TELE}/library_latest.json',snap)
  except Exception as e: jwrite(STATE/'probes/library_error.json',{'unix':time.time(),'error':f'{type(e).__name__}:{e}'})
  STOP.wait(30)

def publisher_and_command_loop():
 pending={}; executed=STATE/'executed'; executed.mkdir(parents=True,exist_ok=True)
 while not STOP.is_set():
  try:
   while True:
    rel,obj=PUBLISH_Q.get_nowait(); pending[str(rel)]=(rel,obj)
  except queue.Empty: pass
  batch=list(pending.values()); pending.clear()
  try:
   heartbeat(ok=True,phase='sync',queued=len(batch)); cmd,commit=publish_and_get_command(batch)
   if cmd and str(cmd.get('id','')).strip():
    rid=str(cmd['id']).strip(); saved=executed/f'{rid}.json'
    if saved.exists(): rec=json.loads(saved.read_text())
    else:
     heartbeat(ok=True,phase='executing',id=rid)
     try: rec=execute(cmd)
     except Exception as e: rec={'schema':SCHEMA,'id':rid,'op':cmd.get('op'),'ok':False,'error':f'{type(e).__name__}:{e}','root':str(ROOT),'unix':time.time()}
     jwrite(saved,rec)
    enqueue(f'{OUT}/{rid}.json',rec)
   heartbeat(ok=True,phase='idle',telemetry_commit=commit,last_id=str(cmd.get('id','')) if cmd else None)
  except Exception as e:
   for rel,obj in batch: pending[str(rel)]=(rel,obj)
   heartbeat(ok=False,phase='sync_error',error=f'{type(e).__name__}:{e}',queued=len(pending))
  STOP.wait(5)

def main():
 STATE.mkdir(parents=True,exist_ok=True); heartbeat(ok=True,phase='boot')
 for fn in (filesystem_probe,runtime_probe,library_probe): threading.Thread(target=fn,daemon=True).start()
 try: publisher_and_command_loop()
 finally: STOP.set()

if __name__=='__main__': main()
