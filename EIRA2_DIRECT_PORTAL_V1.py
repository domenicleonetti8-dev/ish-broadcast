#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,subprocess,time,urllib.request
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe/direct_portal_v1'
REPO=STATE/'return_repo'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
CURRENT='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/eira2_portal/current.json'
OUT='eira2_portal/outbox'

def rr(cmd,cwd=None,timeout=120,check=True,env=None,input_text=None):
 p=subprocess.run(cmd,cwd=str(cwd or ROOT),text=True,input=input_text,capture_output=True,timeout=timeout,env=env)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2000:])
 return p

def safe(v):
 p=(ROOT/str(v or '.')).resolve()
 if p!=ROOT and ROOT not in p.parents: raise ValueError('outside_eira_live')
 return p

def fetch_cmd():
 req=urllib.request.Request(CURRENT,headers={'User-Agent':'EIRA2-DIRECT-PORTAL/1','Cache-Control':'no-cache'})
 with urllib.request.urlopen(req,timeout=15) as r:return json.loads(r.read().decode())

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
 rid=str(c.get('id','')).strip();op=c.get('op');r={'schema':'eira2_direct_portal_receipt_v1','id':rid,'op':op,'root':str(ROOT)}
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

def init_repo():
 REPO.mkdir(parents=True,exist_ok=True)
 if not (REPO/'.git').exists():
  rr(['git','init'],REPO,20);rr(['git','remote','add','origin',ORIGIN],REPO,20);rr(['git','config','user.name','EIRA Direct Portal'],REPO,20);rr(['git','config','user.email','eira-direct-portal@localhost'],REPO,20)

def publish(rec):
 init_repo();payload=json.dumps(rec,indent=2,sort_keys=True)+'\n'
 for n in range(4):
  rr(['git','fetch','--depth','1','origin','master'],REPO,180);base=rr(['git','rev-parse','FETCH_HEAD'],REPO,20).stdout.strip();idx=STATE/f'idx_{os.getpid()}_{n}';env=os.environ.copy();env['GIT_INDEX_FILE']=str(idx)
  try:
   rr(['git','read-tree',base+'^{tree}'],REPO,30,env=env);blob=rr(['git','hash-object','-w','--stdin'],REPO,30,env=env,input_text=payload).stdout.strip();path=f"{OUT}/{rec['id']}.json";rr(['git','update-index','--add','--cacheinfo',f'100644,{blob},{path}'],REPO,30,env=env);tree=rr(['git','write-tree'],REPO,30,env=env).stdout.strip();commit=rr(['git','commit-tree',tree,'-p',base,'-m',f"Portal receipt {rec['id']}"],REPO,30,env=env).stdout.strip();p=rr(['git','push','origin',f'{commit}:refs/heads/master'],REPO,180,False)
   if p.returncode==0:return commit
  finally:
   try: idx.unlink()
   except: pass
  time.sleep(2)
 raise RuntimeError('push_failed')

def main():
 STATE.mkdir(parents=True,exist_ok=True);seen=STATE/'last_id';hb=STATE/'heartbeat.json'
 while True:
  try:
   c=fetch_cmd();rid=str(c.get('id','')).strip();last=seen.read_text().strip() if seen.exists() else ''
   if rid and rid!=last:
    try: rec=execute(c)
    except Exception as e: rec={'schema':'eira2_direct_portal_receipt_v1','id':rid or 'invalid','op':c.get('op'),'ok':False,'error':f'{type(e).__name__}:{e}','root':str(ROOT),'unix':time.time()}
    (STATE/f'{rec["id"]}.json').write_text(json.dumps(rec,indent=2)+'\n');commit=publish(rec);seen.write_text(rec['id']);hb.write_text(json.dumps({'ok':True,'pid':os.getpid(),'last_id':rec['id'],'commit':commit,'unix':time.time()},indent=2)+'\n')
   else: hb.write_text(json.dumps({'ok':True,'pid':os.getpid(),'last_id':last,'unix':time.time()},indent=2)+'\n')
  except Exception as e: hb.write_text(json.dumps({'ok':False,'pid':os.getpid(),'error':f'{type(e).__name__}:{e}','unix':time.time()},indent=2)+'\n')
  time.sleep(5)
if __name__=='__main__':main()
