#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe'/'orin_baby_probe_v1'
LEGACY_HB=ROOT/'eira_probe'/'orin_build_probe_v1'/'heartbeat.json'
REPO=STATE/'repo'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
INBOX=Path('eira2_build_probe/inbox'); OUTBOX=Path('eira2_build_probe/outbox')
SCHEMA='eira2_orin_baby_recovery_probe_v1'; POLL=3.0

def run(cmd,cwd=None,timeout=25,check=True):
 p=subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1800:])
 return p

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def atom(p:Path,obj):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def heartbeat(phase,ok=True,**extra):
 d={'schema':SCHEMA,'version':'baby-recovery-v1','ok':ok,'phase':phase,'pid':os.getpid(),'unix':time.time(),**extra}
 atom(STATE/'heartbeat.json',d); atom(LEGACY_HB,d)
def safe(v:str)->Path:
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe_path')
 q=(ROOT/p).resolve()
 if q!=ROOT and ROOT not in q.parents: raise ValueError('outside_live')
 return q

def sync():
 STATE.mkdir(parents=True,exist_ok=True); heartbeat('sync_start')
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  run(['git','clone','--depth','1','--quiet',ORIGIN,str(REPO)],timeout=45)
 else:
  run(['git','fetch','--depth','1','--quiet','origin','master']) if False else None
  run(['git','fetch','--depth','1','--quiet','origin','master'],cwd=REPO,timeout=25)
 run(['git','checkout','--quiet','-B','orin_baby_runtime','origin/master'],cwd=REPO)
 run(['git','reset','--hard','origin/master'],cwd=REPO)
 head=run(['git','rev-parse','HEAD'],cwd=REPO).stdout.strip(); heartbeat('synced',head=head); return head

def publish(rid,rec):
 sync(); rel=OUTBOX/f'{rid}.json'; p=REPO/rel; atom(p,rec); run(['git','add',rel.as_posix()],cwd=REPO)
 if run(['git','diff','--cached','--quiet'],cwd=REPO,check=False).returncode:
  run(['git','-c','user.name=EIRA Baby Probe','-c','user.email=eira-baby@localhost','commit','--quiet','-m',f'Baby probe receipt {rid}'],cwd=REPO)
  run(['git','pull','--rebase','--quiet','origin','master'],cwd=REPO,timeout=25)
  run(['git','push','--quiet','origin','HEAD:master'],cwd=REPO,timeout=25)
 return run(['git','rev-parse','HEAD'],cwd=REPO).stdout.strip()

def git_blob(commit,path):
 if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise ValueError('invalid_commit')
 rel=Path(path)
 if rel.is_absolute() or '..' in rel.parts or not rel.parts: raise ValueError('invalid_repo_path')
 p=subprocess.run(['git','-C',str(REPO),'show',f'{commit}:{rel.as_posix()}'],capture_output=True,timeout=20,check=False)
 if p.returncode: raise RuntimeError('source_blob_missing:'+p.stderr[-1000:].decode(errors='replace'))
 return p.stdout

def deploy(rid,c):
 src=c.get('source') or {}; target=safe(c.get('target_path','')); raw=git_blob(str(src.get('commit','')),str(src.get('path',''))); expected=str(src.get('sha256','')).lower()
 if expected and sha(raw)!=expected: raise RuntimeError('source_sha256_mismatch')
 if target.suffix=='.py': compile(raw.decode('utf-8'),str(target),'exec')
 before=target.read_bytes() if target.is_file() else None
 bak=None
 if before is not None:
  bak=STATE/'backups'/rid/target.relative_to(ROOT); bak.parent.mkdir(parents=True,exist_ok=True); bak.write_bytes(before)
 target.parent.mkdir(parents=True,exist_ok=True); tmp=target.with_name(target.name+'.baby_tmp'); tmp.write_bytes(raw); os.replace(tmp,target)
 if sha(target.read_bytes())!=sha(raw):
  if before is None: target.unlink(missing_ok=True)
  else: target.write_bytes(before)
  raise RuntimeError('post_write_hash_mismatch_rolled_back')
 return {'target_path':str(target.relative_to(ROOT)),'before_sha256':sha(before) if before else None,'after_sha256':sha(raw),'backup':str(bak.relative_to(ROOT)) if bak else None}

def inspect(c):
 op=str(c.get('op',''))
 if op=='health': return {'root':str(ROOT),'pid':os.getpid(),'version':'baby-recovery-v1','state':str(STATE)}
 if op=='read':
  p=safe(c.get('path','')); b=p.read_bytes(); lim=min(max(int(c.get('max_bytes',200000)),1),500000); return {'path':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':sha(b),'text':b[:lim].decode('utf-8','replace'),'truncated':len(b)>lim}
 if op=='list':
  p=safe(c.get('path','.')); lim=min(max(int(c.get('limit',200)),1),1000); return {'path':str(p.relative_to(ROOT)) if p!=ROOT else '.','items':[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:lim]]}
 if op=='compile':
  p=safe(c.get('path','')); q=run(['python3','-m','py_compile',str(p)],timeout=20,check=False); return {'path':str(p.relative_to(ROOT)),'ok':q.returncode==0,'stderr':q.stderr[-1200:]}
 if op=='search':
  term=str(c.get('term','')); roots=[safe(x) for x in (c.get('roots') or ['eira2'])]; lim=min(max(int(c.get('limit',80)),1),200); hits=[]
  for base in roots:
   if not base.exists(): continue
   for p in base.rglob('*.py'):
    if len(hits)>=lim: break
    try:t=p.read_text(errors='replace')
    except Exception: continue
    if term in t:hits.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())})
  return {'term':term,'hits':hits}
 raise ValueError('unsupported_op')

def execute(c):
 rid=str(c.get('id','')).strip(); op=str(c.get('op','')).strip()
 if not rid: raise ValueError('missing_id')
 base={'schema':SCHEMA,'id':rid,'op':op,'root':str(ROOT),'unix':time.time()}
 base.update(ok=True,result=deploy(rid,c) if op=='deploy' else inspect(c)); return base

def main():
 executed=STATE/'executed'; executed.mkdir(parents=True,exist_ok=True); heartbeat('boot')
 while True:
  try:
   sync(); inbox=REPO/INBOX; inbox.mkdir(parents=True,exist_ok=True)
   for p in sorted(inbox.glob('*.json')):
    raw=p.read_bytes(); digest=sha(raw); marker=executed/f'{digest}.json'
    if marker.exists(): continue
    try: rec=execute(json.loads(raw.decode('utf-8')))
    except Exception as e: rec={'schema':SCHEMA,'id':p.stem,'ok':False,'error':f'{type(e).__name__}:{e}'[:2500],'unix':time.time(),'root':str(ROOT)}
    rec['command_sha256']=digest; atom(marker,rec); rec['return_commit']=publish(str(rec.get('id') or p.stem),rec)
   heartbeat('idle'); time.sleep(POLL)
  except Exception as e:
   heartbeat('error',False,error=f'{type(e).__name__}:{e}'[:1800]); time.sleep(POLL)
if __name__=='__main__': main()
