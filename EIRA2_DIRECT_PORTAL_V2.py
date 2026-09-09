#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,urllib.request
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe/direct_portal_v2'
REPO=Path('/tmp/eira2_direct_portal_v2_repo')
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
CURRENT='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/eira2_portal/current.json'
OUT='eira2_portal/outbox'

def rr(cmd,cwd=None,timeout=600,check=True):
 p=subprocess.run(cmd,cwd=str(cwd or ROOT),text=True,capture_output=True,timeout=timeout)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2000:])
 return p

def safe(v):
 p=(ROOT/str(v or '.')).resolve()
 if p!=ROOT and ROOT not in p.parents: raise ValueError('outside_eira_live')
 return p

def fetch_cmd():
 q=urllib.request.Request(CURRENT,headers={'User-Agent':'EIRA2-DIRECT-PORTAL/2','Cache-Control':'no-cache'})
 with urllib.request.urlopen(q,timeout=15) as r:return json.loads(r.read().decode())

def manifest(limit=10000):
 out=[]
 for p in ROOT.rglob('*'):
  if len(out)>=limit: break
  try:
   if p.is_file():
    b=p.read_bytes();out.append({'path':str(p.relative_to(ROOT)),'size':len(b),'sha256':hashlib.sha256(b).hexdigest()})
  except Exception as e: out.append({'path':str(p.relative_to(ROOT)),'error':type(e).__name__})
 return out

def execute(c):
 rid=str(c.get('id','')).strip();op=c.get('op');r={'schema':'eira2_direct_portal_receipt_v2','id':rid,'op':op,'root':str(ROOT)}
 if not rid: raise ValueError('missing_id')
 if op=='manifest': r.update(ok=True,items=manifest(int(c.get('limit',10000))))
 elif op=='list':
  p=safe(c.get('path'));r.update(ok=True,path=str(p.relative_to(ROOT)) if p!=ROOT else '.',items=[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:int(c.get('limit',5000))]])
 elif op=='read':
  p=safe(c.get('path'));b=p.read_bytes();m=min(int(c.get('max_bytes',500000)),2000000);r.update(ok=True,path=str(p.relative_to(ROOT)),size=len(b),sha256=hashlib.sha256(b).hexdigest(),text=b[:m].decode('utf-8','replace'),truncated=len(b)>m)
 elif op=='write':
  p=safe(c.get('path'));data=str(c.get('text','')).encode();p.parent.mkdir(parents=True,exist_ok=True);before=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None;tmp=p.with_name(p.name+'.portal_tmp');tmp.write_bytes(data);os.replace(tmp,p);r.update(ok=True,path=str(p.relative_to(ROOT)),before_sha256=before,after_sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
 elif op=='delete':
  p=safe(c.get('path'));before=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None;p.unlink();r.update(ok=True,path=str(p.relative_to(ROOT)),before_sha256=before)
 elif op=='move':
  a=safe(c.get('src'));b=safe(c.get('dst'));b.parent.mkdir(parents=True,exist_ok=True);os.replace(a,b);r.update(ok=True,src=str(a.relative_to(ROOT)),dst=str(b.relative_to(ROOT)))
 elif op=='mkdir':
  p=safe(c.get('path'));p.mkdir(parents=True,exist_ok=True);r.update(ok=True,path=str(p.relative_to(ROOT)))
 elif op=='compile':
  p=safe(c.get('path'));q=rr(['python3','-m','py_compile',str(p)],timeout=60,check=False);r.update(ok=q.returncode==0,path=str(p.relative_to(ROOT)),returncode=q.returncode,stdout=q.stdout,stderr=q.stderr)
 else: raise ValueError('unsupported_op')
 r['unix']=time.time();return r

def sync_repo():
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  rr(['git','clone','--quiet',ORIGIN,str(REPO)],timeout=600)
 for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','-B','portal_runtime','origin/master'],['git','reset','--hard','origin/master']): rr(cmd,REPO,600)

def publish(rec):
 sync_repo();p=REPO/OUT/f"{rec['id']}.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
 rr(['git','add',str(Path(OUT)/f"{rec['id']}.json")],REPO,120)
 if rr(['git','diff','--cached','--quiet'],REPO,120,False).returncode!=0:
  rr(['git','-c','user.name=EIRA Direct Portal','-c','user.email=eira-direct-portal@localhost','commit','--quiet','-m',f"Portal receipt {rec['id']}"],REPO,120)
  rr(['git','pull','--rebase','--quiet','origin','master'],REPO,600)
  rr(['git','push','--quiet','origin','HEAD:master'],REPO,600)
 return rr(['git','rev-parse','HEAD'],REPO,120).stdout.strip()

def heartbeat(**v):
 STATE.mkdir(parents=True,exist_ok=True);(STATE/'heartbeat.json').write_text(json.dumps({'pid':os.getpid(),'unix':time.time(),**v},indent=2)+'\n')

def main():
 STATE.mkdir(parents=True,exist_ok=True);seen=STATE/'last_id'
 while True:
  try:
   c=fetch_cmd();rid=str(c.get('id','')).strip();last=seen.read_text().strip() if seen.exists() else ''
   if rid and rid!=last:
    heartbeat(ok=True,phase='executing',id=rid)
    try: rec=execute(c)
    except Exception as e: rec={'schema':'eira2_direct_portal_receipt_v2','id':rid or 'invalid','op':c.get('op'),'ok':False,'error':f'{type(e).__name__}:{e}','root':str(ROOT),'unix':time.time()}
    (STATE/f'{rec["id"]}.json').write_text(json.dumps(rec,indent=2)+'\n');heartbeat(ok=True,phase='publishing',id=rec['id']);commit=publish(rec);seen.write_text(rec['id']);heartbeat(ok=True,phase='idle',last_id=rec['id'],commit=commit)
   else: heartbeat(ok=True,phase='idle',last_id=last)
  except Exception as e: heartbeat(ok=False,phase='error',error=f'{type(e).__name__}:{e}')
  time.sleep(5)
if __name__=='__main__':main()
