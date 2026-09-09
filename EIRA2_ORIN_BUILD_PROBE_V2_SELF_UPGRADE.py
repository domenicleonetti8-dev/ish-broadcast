#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe'/'orin_build_probe_v2'
REPO=STATE/'repo'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
INBOX=Path('eira2_build_probe/inbox'); OUTBOX=Path('eira2_build_probe/outbox')
SCHEMA='eira2_orin_build_probe_v2'; POLL=3.0
UPGRADE_DIR=ROOT/'eira_probe'/'orin_build_probe_versions'
UPGRADE_REQUEST=ROOT/'eira_probe'/'orin_build_probe_supervisor_v3'/'upgrade_request.json'

def run(cmd,cwd=None,timeout=600,check=True):
 p=subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2500:])
 return p

def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha_file(p:Path)->str:return sha_bytes(p.read_bytes())
def atomic_json(p:Path,obj:Any):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)

def safe_rel(v:str)->Path:
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe_path')
 out=(ROOT/p).resolve()
 if out!=ROOT and ROOT not in out.parents: raise ValueError('outside_live')
 return out

def sync():
 STATE.mkdir(parents=True,exist_ok=True)
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  run(['git','clone','--quiet',ORIGIN,str(REPO)],timeout=600)
 for cmd in (['git','fetch','--quiet','origin','master'],['git','checkout','--quiet','-B','orin_build_probe_runtime','origin/master'],['git','reset','--hard','origin/master'],['git','clean','-fd']): run(cmd,REPO)
 return run(['git','rev-parse','HEAD'],REPO).stdout.strip()

def publish(rid:str,receipt:dict[str,Any])->str:
 sync(); rel=OUTBOX/f'{rid}.json'; p=REPO/rel; atomic_json(p,receipt); run(['git','add',rel.as_posix()],REPO)
 if run(['git','diff','--cached','--quiet'],REPO,check=False).returncode!=0:
  run(['git','-c','user.name=EIRA Orin Build Probe','-c','user.email=eira-build-probe@localhost','commit','--quiet','-m',f'Build probe receipt {rid}'],REPO)
  run(['git','pull','--rebase','--quiet','origin','master'],REPO); run(['git','push','--quiet','origin','HEAD:master'],REPO)
 return run(['git','rev-parse','HEAD'],REPO).stdout.strip()

def git_blob(commit:str,repo_path:str)->bytes:
 if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise ValueError('invalid_commit')
 rel=Path(repo_path)
 if rel.is_absolute() or '..' in rel.parts or not rel.parts: raise ValueError('invalid_repo_path')
 p=subprocess.run(['git','-C',str(REPO),'show',f'{commit}:{rel.as_posix()}'],capture_output=True,timeout=180,check=False)
 if p.returncode: raise RuntimeError('source_blob_missing:'+p.stderr[-1600:].decode(errors='replace'))
 return p.stdout

def backup(rid:str,target:Path):
 if not target.is_file(): return None
 rel=target.relative_to(ROOT); dst=STATE/'backups'/rid/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,dst); return str(dst.relative_to(ROOT))

def deploy(rid:str,cmd:dict[str,Any])->dict[str,Any]:
 src=cmd.get('source') or {}; target=safe_rel(str(cmd.get('target_path') or '')); raw=git_blob(str(src.get('commit') or ''),str(src.get('path') or ''))
 expected=str(src.get('sha256') or '').lower()
 if expected and sha_bytes(raw)!=expected: raise RuntimeError('source_sha256_mismatch')
 if target.suffix=='.py': compile(raw.decode('utf-8'),str(target),'exec')
 before=target.read_bytes() if target.is_file() else None; bak=backup(rid,target); target.parent.mkdir(parents=True,exist_ok=True)
 tmp=target.with_name(target.name+'.build_probe_tmp'); tmp.write_bytes(raw); os.replace(tmp,target); after=sha_file(target)
 if after!=sha_bytes(raw):
  if before is None: target.unlink(missing_ok=True)
  else: target.write_bytes(before)
  raise RuntimeError('post_write_hash_mismatch_rolled_back')
 if target.suffix=='.py':
  q=run(['python3','-m','py_compile',str(target)],timeout=60,check=False)
  if q.returncode:
   if before is None: target.unlink(missing_ok=True)
   else: target.write_bytes(before)
   raise RuntimeError('python_compile_failed_rolled_back:'+q.stderr[-1200:])
 return {'target_path':str(target.relative_to(ROOT)),'before_sha256':sha_bytes(before) if before is not None else None,'after_sha256':after,'payload_sha256':sha_bytes(raw),'backup':bak,'compile_ok':True if target.suffix=='.py' else None}

def stage_upgrade(rid:str,cmd:dict[str,Any])->dict[str,Any]:
 src=cmd.get('source') or {}; raw=git_blob(str(src.get('commit') or ''),str(src.get('path') or '')); expected=str(src.get('sha256') or '').lower(); digest=sha_bytes(raw)
 if expected and digest!=expected: raise RuntimeError('source_sha256_mismatch')
 compile(raw.decode('utf-8'),'<probe-upgrade>','exec')
 UPGRADE_DIR.mkdir(parents=True,exist_ok=True); candidate=UPGRADE_DIR/f'probe_{digest[:16]}.py'; tmp=candidate.with_suffix('.tmp'); tmp.write_bytes(raw); os.replace(tmp,candidate)
 q=run(['python3','-m','py_compile',str(candidate)],timeout=60,check=False)
 if q.returncode: candidate.unlink(missing_ok=True); raise RuntimeError('upgrade_compile_failed:'+q.stderr[-1200:])
 req={'schema':'eira2_orin_build_probe_upgrade_v1','id':rid,'candidate':str(candidate.relative_to(ROOT)),'sha256':digest,'requested_unix':time.time()}; atomic_json(UPGRADE_REQUEST,req)
 return {'candidate':req['candidate'],'sha256':digest,'handoff':'supervisor_v3'}

def inspect(cmd):
 op=str(cmd.get('op') or '')
 if op=='read':
  p=safe_rel(str(cmd.get('path') or '')); b=p.read_bytes(); lim=min(max(int(cmd.get('max_bytes',500000)),1),2000000); return {'path':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':sha_bytes(b),'text':b[:lim].decode('utf-8','replace'),'truncated':len(b)>lim}
 if op=='list':
  p=safe_rel(str(cmd.get('path') or '.')); lim=min(max(int(cmd.get('limit',500)),1),5000); return {'path':str(p.relative_to(ROOT)) if p!=ROOT else '.','items':[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:lim]]}
 if op=='search':
  term=str(cmd.get('term') or ''); roots=[safe_rel(x) for x in (cmd.get('roots') or ['eira2','extensions','tools'])]; lim=min(max(int(cmd.get('limit',100)),1),500); hits=[]
  for base in roots:
   if not base.exists(): continue
   for p in base.rglob('*'):
    if len(hits)>=lim: break
    if not p.is_file() or p.suffix.lower() not in {'.py','.json','.js','.html','.md','.txt'}: continue
    try:text=p.read_text(errors='replace')
    except Exception:continue
    if term in text:hits.append({'path':str(p.relative_to(ROOT)),'sha256':sha_file(p),'bytes':p.stat().st_size})
  return {'term':term,'hits':hits}
 if op=='compile':
  p=safe_rel(str(cmd.get('path') or '')); q=run(['python3','-m','py_compile',str(p)],timeout=60,check=False); return {'path':str(p.relative_to(ROOT)),'ok':q.returncode==0,'returncode':q.returncode,'stderr':q.stderr[-2000:]}
 if op=='health': return {'root':str(ROOT),'state':str(STATE),'repo':str(REPO),'pid':os.getpid(),'version':'2.0-self-upgrade'}
 raise ValueError('unsupported_op')

def execute(cmd):
 rid=str(cmd.get('id') or '').strip(); op=str(cmd.get('op') or '').strip()
 if not rid: raise ValueError('missing_id')
 base={'schema':SCHEMA,'id':rid,'op':op,'root':str(ROOT),'unix':time.time()}
 if op=='deploy': base.update(ok=True,result=deploy(rid,cmd))
 elif op=='upgrade_probe': base.update(ok=True,result=stage_upgrade(rid,cmd))
 else: base.update(ok=True,result=inspect(cmd))
 return base

def loop(interval:float):
 executed=STATE/'executed'; executed.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   head=sync(); atomic_json(STATE/'heartbeat.json',{'schema':SCHEMA,'ok':True,'phase':'synced','head':head,'pid':os.getpid(),'unix':time.time(),'version':'2.0-self-upgrade'})
   inbox=REPO/INBOX; inbox.mkdir(parents=True,exist_ok=True)
   for p in sorted(inbox.glob('*.json')):
    raw=p.read_bytes(); digest=sha_bytes(raw); marker=executed/f'{digest}.json'
    if marker.exists(): continue
    try: cmd=json.loads(raw.decode('utf-8')); rec=execute(cmd)
    except Exception as e: rec={'schema':SCHEMA,'id':p.stem,'ok':False,'error':f'{type(e).__name__}:{e}'[:4000],'unix':time.time(),'root':str(ROOT)}
    rec['command_sha256']=digest; atomic_json(marker,rec); rec['return_commit']=publish(str(rec.get('id') or p.stem),rec)
    if rec.get('ok') and rec.get('op')=='upgrade_probe': return
   time.sleep(max(1.0,interval))
  except Exception as e:
   atomic_json(STATE/'heartbeat.json',{'schema':SCHEMA,'ok':False,'phase':'error','error':f'{type(e).__name__}:{e}'[:3000],'pid':os.getpid(),'unix':time.time(),'version':'2.0-self-upgrade'}); time.sleep(max(2.0,interval))

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--interval',type=float,default=POLL); ap.add_argument('--once',action='store_true'); args=ap.parse_args()
 if args.once: print(json.dumps({'schema':SCHEMA,'ok':True,'head':sync(),'root':str(ROOT)},indent=2)); return
 loop(args.interval)
if __name__=='__main__': main()
