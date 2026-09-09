#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,urllib.request

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe/orin_worker_v2'
REPO=Path('/tmp/eira2_orin_worker_v2_repo')
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
CURRENT_BASE='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/eira2_portal/current.json'
OUT='eira2_portal/outbox'
SCHEMA='eira2_orin_worker_receipt_v2'

def rr(cmd,cwd=None,timeout=600,check=True):
 p=subprocess.run(cmd,cwd=str(cwd or ROOT),text=True,capture_output=True,timeout=timeout)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2000:])
 return p

def safe(v):
 p=(ROOT/str(v or '.')).resolve()
 if p!=ROOT and ROOT not in p.parents: raise ValueError('outside_eira_live')
 return p

def sha(b): return hashlib.sha256(b).hexdigest()

def fetch_cmd():
 url=f"{CURRENT_BASE}?t={time.time_ns()}"
 q=urllib.request.Request(url,headers={'User-Agent':'EIRA2-ORIN-WORKER/2','Cache-Control':'no-cache, no-store','Pragma':'no-cache'})
 with urllib.request.urlopen(q,timeout=15) as r:return json.loads(r.read().decode())

def heartbeat(**v):
 STATE.mkdir(parents=True,exist_ok=True)
 (STATE/'heartbeat.json').write_text(json.dumps({'schema':'eira2_orin_worker_heartbeat_v2','pid':os.getpid(),'unix':time.time(),**v},indent=2)+'\n')

def backup(rid,p):
 if not p.exists() or not p.is_file(): return None
 rel=p.relative_to(ROOT);dst=STATE/'backups'/rid/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);return str(dst.relative_to(ROOT))

def execute(c):
 rid=str(c.get('id','')).strip();op=str(c.get('op','')).strip();r={'schema':SCHEMA,'id':rid,'op':op,'root':str(ROOT)}
 if not rid: raise ValueError('missing_id')
 if op=='list':
  p=safe(c.get('path'));r.update(ok=True,path=str(p.relative_to(ROOT)) if p!=ROOT else '.',items=[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:int(c.get('limit',500))]])
 elif op=='read':
  p=safe(c.get('path'));b=p.read_bytes();m=min(int(c.get('max_bytes',500000)),2000000);r.update(ok=True,path=str(p.relative_to(ROOT)),size=len(b),sha256=sha(b),text=b[:m].decode('utf-8','replace'),truncated=len(b)>m)
 elif op=='write':
  p=safe(c.get('path'));data=str(c.get('text','')).encode();p.parent.mkdir(parents=True,exist_ok=True);before=p.read_bytes() if p.is_file() else None;bak=backup(rid,p);tmp=p.with_name(p.name+'.orin_tmp');tmp.write_bytes(data);os.replace(tmp,p)
  compile_result=None
  if p.suffix=='.py':
   q=rr(['python3','-m','py_compile',str(p)],timeout=60,check=False);compile_result={'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
   if q.returncode!=0:
    if before is None: p.unlink(missing_ok=True)
    else: p.write_bytes(before)
    raise RuntimeError('python_compile_failed_rolled_back:'+q.stderr[-1200:])
  r.update(ok=True,path=str(p.relative_to(ROOT)),backup=bak,before_sha256=sha(before) if before is not None else None,after_sha256=sha(data),bytes=len(data),compile=compile_result)
 elif op=='compile':
  p=safe(c.get('path'));q=rr(['python3','-m','py_compile',str(p)],timeout=60,check=False);r.update(ok=q.returncode==0,path=str(p.relative_to(ROOT)),returncode=q.returncode,stdout=q.stdout,stderr=q.stderr)
 else: raise ValueError('unsupported_op')
 r['unix']=time.time();return r

def sync_repo():
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  rr(['git','clone','--quiet',ORIGIN,str(REPO)],timeout=600)
 for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','-B','orin_worker_runtime','origin/master'],['git','reset','--hard','origin/master']): rr(cmd,REPO,600)

def publish(rec):
 sync_repo();rel=Path(OUT)/f"{rec['id']}.json";p=REPO/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
 rr(['git','add',str(rel)],REPO,120)
 if rr(['git','diff','--cached','--quiet'],REPO,120,False).returncode!=0:
  rr(['git','-c','user.name=EIRA Orin Worker','-c','user.email=eira-orin-worker@localhost','commit','--quiet','-m',f"Orin worker receipt {rec['id']}"],REPO,120)
  rr(['git','pull','--rebase','--quiet','origin','master'],REPO,600)
  rr(['git','push','--quiet','origin','HEAD:master'],REPO,600)
 return rr(['git','rev-parse','HEAD'],REPO,120).stdout.strip()

def main():
 STATE.mkdir(parents=True,exist_ok=True);seen=STATE/'last_id';heartbeat(ok=True,phase='boot')
 while True:
  try:
   c=fetch_cmd();rid=str(c.get('id','')).strip();last=seen.read_text().strip() if seen.exists() else ''
   if rid and rid!=last:
    heartbeat(ok=True,phase='executing',id=rid)
    try: rec=execute(c)
    except Exception as e: rec={'schema':SCHEMA,'id':rid or 'invalid','op':c.get('op'),'ok':False,'error':f'{type(e).__name__}:{e}','root':str(ROOT),'unix':time.time()}
    (STATE/f"{rec['id']}.json").write_text(json.dumps(rec,indent=2)+'\n');heartbeat(ok=True,phase='publishing',id=rec['id']);commit=publish(rec);seen.write_text(rec['id']);heartbeat(ok=True,phase='idle',last_id=rec['id'],commit=commit)
   else: heartbeat(ok=True,phase='idle',last_id=last)
  except Exception as e: heartbeat(ok=False,phase='error',error=f'{type(e).__name__}:{e}')
  time.sleep(5)

if __name__=='__main__': main()
