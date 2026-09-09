#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe'/'orin_continuous_probe_v2'; REPO=STATE/'repo'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
REMOTE=Path('eira2_continuous_probe'); TELEMETRY=REMOTE/'telemetry'; INBOX=REMOTE/'inbox'; OUTBOX=REMOTE/'outbox'
SCHEMA='eira2_continuous_probe_v2'; VERSION='2.3.0-bounded-scheduler'; INTERVAL=8.0; MAX_COMMANDS_PER_CYCLE=3
ENV={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_HTTP_LOW_SPEED_LIMIT':'1024','GIT_HTTP_LOW_SPEED_TIME':'15'}
CORE=['main.py','eira2/__main__.py','eira2/runtime.py','eira2/conversation/spine.py','eira2/conversation/analysis.py','eira2/reasoning/provider.py','eira2/operations/package_identity.py','eira2/evidence/universe_public_library.py','tools/eira2_orin_build_probe.py']
LIBROOT=(ROOT/'eira2/evidence').resolve()
def atom(p,o):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def run(c,cwd=None,timeout=45,check=True):
 p=subprocess.run(c,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False,env=ENV)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2000:])
 return p
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''): h.update(c)
 return h.hexdigest()
def canonical_bytes(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def sync():
 STATE.mkdir(parents=True,exist_ok=True)
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  run(['git','clone','--quiet','--depth','1','--branch','master',ORIGIN,str(REPO)],timeout=60)
 else: run(['git','fetch','--quiet','--depth','1','origin','master'],REPO)
 run(['git','checkout','--quiet','-B','continuous_probe_runtime','origin/master'],REPO,timeout=20)
 run(['git','reset','--hard','origin/master'],REPO,timeout=20)
 return run(['git','rev-parse','HEAD'],REPO,timeout=10).stdout.strip()
def publish(rel,payload):
 sync(); p=REPO/rel; atom(p,payload); run(['git','add',rel.as_posix()],REPO,timeout=10)
 if run(['git','diff','--cached','--quiet'],REPO,timeout=10,check=False).returncode:
  run(['git','-c','user.name=EIRA Continuous Probe','-c','user.email=eira-probe@localhost','commit','--quiet','-m',f'Continuous probe {rel.name}'],REPO,timeout=20)
  run(['git','pull','--rebase','--quiet','origin','master'],REPO,timeout=35)
  run(['git','push','--quiet','origin','HEAD:master'],REPO,timeout=35)
def safe(v):
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe_path')
 q=(ROOT/p).resolve()
 if q!=ROOT and ROOT not in q.parents: raise ValueError('outside_live')
 return q,p
def source_blob(src):
 commit=str(src.get('commit') or ''); path=str(src.get('path') or '')
 if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise ValueError('invalid_commit')
 rp=Path(path)
 if rp.is_absolute() or '..' in rp.parts or not rp.parts: raise ValueError('invalid_repo_path')
 p=subprocess.run(['git','-C',str(REPO),'show',f'{commit}:{rp.as_posix()}'],capture_output=True,timeout=30,check=False)
 if p.returncode: raise RuntimeError('source_blob_missing:'+p.stderr[-1200:].decode(errors='replace'))
 raw=p.stdout; exp=str(src.get('sha256') or '').lower()
 if exp and sha_bytes(raw)!=exp: raise RuntimeError('source_sha256_mismatch')
 return raw
def deploy(rid,c):
 q,r=safe(c.get('target_path')); raw=source_blob(c.get('source') or {})
 if (q==LIBROOT or LIBROOT in q.parents) and not bool(c.get('allow_library_write')): raise ValueError('library_write_requires_explicit_allow')
 if q.suffix=='.py': compile(raw.decode('utf-8'),str(q),'exec')
 before=q.read_bytes() if q.is_file() else None; backup=None
 if before is not None:
  backup=STATE/'backups'/rid/r; backup.parent.mkdir(parents=True,exist_ok=True); backup.write_bytes(before)
 q.parent.mkdir(parents=True,exist_ok=True); tmp=q.with_name(q.name+f'.tmp.{os.getpid()}'); tmp.write_bytes(raw); os.replace(tmp,q)
 if sha(q)!=sha_bytes(raw):
  if before is None: q.unlink(missing_ok=True)
  else: q.write_bytes(before)
  raise RuntimeError('post_write_hash_mismatch_rolled_back')
 if q.suffix=='.py':
  p=run(['python3','-m','py_compile',str(q)],timeout=30,check=False)
  if p.returncode:
   if before is None: q.unlink(missing_ok=True)
   else: q.write_bytes(before)
   raise RuntimeError('compile_failed_rolled_back:'+p.stderr[-1200:])
 return {'target_path':str(r),'before_sha256':sha_bytes(before) if before is not None else None,'after_sha256':sha(q),'payload_sha256':sha_bytes(raw),'backup':str(backup.relative_to(ROOT)) if backup else None,'compile_ok':True if q.suffix=='.py' else None}
def reseal_plan(c,apply=False):
 manifest=ROOT/'eira2-package-manifest.json'; rel=str(c.get('path') or '').strip()
 old_sha=str(c.get('expected_old_sha256') or '').lower(); old_size=int(c.get('expected_old_size'))
 new_sha=str(c.get('expected_live_sha256') or c.get('expected_new_sha256') or '').lower(); new_size=int(c.get('expected_live_size') if c.get('expected_live_size') is not None else c.get('expected_new_size'))
 if rel!='eira2/evidence/universe_public_library.py': raise ValueError('reseal_path_not_allowed')
 live=ROOT/rel
 if not manifest.is_file() or not live.is_file(): raise RuntimeError('manifest_or_live_target_missing')
 live_raw=live.read_bytes(); live_sha=sha_bytes(live_raw)
 if len(live_raw)!=new_size or live_sha!=new_sha: raise RuntimeError('live_target_not_expected_preserved_version')
 original=manifest.read_bytes(); payload=json.loads(original.decode('utf-8')); rows=payload.get('files')
 if not isinstance(rows,list): raise RuntimeError('manifest_files_invalid')
 hits=[x for x in rows if isinstance(x,dict) and x.get('path')==rel]
 if len(hits)!=1: raise RuntimeError('manifest_target_row_count_invalid')
 row=hits[0]
 if int(row.get('size'))!=old_size or str(row.get('sha256') or '').lower()!=old_sha: raise RuntimeError('manifest_old_row_not_expected')
 before_tree=str(payload.get('package_tree_sha256') or '')
 trial=[dict(x) if isinstance(x,dict) else x for x in rows]; trial_row=[x for x in trial if isinstance(x,dict) and x.get('path')==rel][0]
 trial_row['size']=new_size; trial_row['sha256']=new_sha; after_tree=hashlib.sha256(canonical_bytes(trial)).hexdigest()
 plan={'mode':'apply' if apply else 'preflight','manifest_path':'eira2-package-manifest.json','manifest_before_sha256':sha_bytes(original),'row_path':rel,'old_size':old_size,'old_sha256':old_sha,'new_size':new_size,'new_sha256':new_sha,'tree_before':before_tree,'tree_after':after_tree,'library_bytes_preserved':len(live_raw),'library_sha256_preserved':live_sha}
 if not apply: return plan
 backup=STATE/'backups'/'package_reseal'/f'eira2-package-manifest.{int(time.time())}.json'; backup.parent.mkdir(parents=True,exist_ok=True); backup.write_bytes(original)
 row['size']=new_size; row['sha256']=new_sha; payload['package_tree_sha256']=after_tree
 new=(json.dumps(payload,indent=2,sort_keys=True)+'\n').encode('utf-8'); tmp=manifest.with_name(manifest.name+f'.tmp.{os.getpid()}'); tmp.write_bytes(new); os.replace(tmp,manifest)
 try:
  check=json.loads(manifest.read_text()); check_rows=check.get('files'); chk=[x for x in check_rows if x.get('path')==rel]
  if hashlib.sha256(canonical_bytes(check_rows)).hexdigest()!=str(check.get('package_tree_sha256')): raise RuntimeError('post_reseal_tree_hash_invalid')
  if len(chk)!=1 or int(chk[0].get('size'))!=new_size or str(chk[0].get('sha256')).lower()!=new_sha: raise RuntimeError('post_reseal_row_invalid')
  if sha_bytes(live.read_bytes())!=live_sha: raise RuntimeError('library_changed_during_reseal')
 except Exception:
  manifest.write_bytes(original); raise
 plan.update({'backup':str(backup.relative_to(ROOT)),'manifest_after_sha256':sha(manifest)}); return plan
def snapshot(extra=None):
 rows=[]
 for rel in CORE:
  p=ROOT/rel; rows.append({'path':rel,'exists':p.is_file(),'bytes':p.stat().st_size if p.is_file() else None,'sha256':sha(p) if p.is_file() else None})
 ps=run(['ps','-eo','pid,etimes,comm,args'],timeout=10,check=False).stdout.splitlines(); procs=[x[-400:] for x in ps if 'eira' in x.lower() or 'orin' in x.lower()][:50]
 out={'schema':SCHEMA,'version':VERSION,'unix':time.time(),'pid':os.getpid(),'root':str(ROOT),'core':rows,'processes':procs}
 if extra: out.update(extra)
 return out
def inspect(c):
 op=str(c.get('op') or '')
 if op=='health': return snapshot()
 if op=='read':
  q,r=safe(c.get('path')); b=q.read_bytes(); lim=min(max(int(c.get('max_bytes',250000)),1),2000000); return {'path':str(r),'bytes':len(b),'sha256':sha_bytes(b),'text':b[:lim].decode('utf-8','replace'),'truncated':len(b)>lim}
 if op=='list':
  q,r=safe(c.get('path') or '.'); lim=min(max(int(c.get('limit',500)),1),5000); return {'path':str(r),'items':[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(q.iterdir())[:lim]]}
 if op=='compile':
  q,r=safe(c.get('path')); p=run(['python3','-m','py_compile',str(q)],timeout=30,check=False); return {'path':str(r),'ok':p.returncode==0,'returncode':p.returncode,'stderr':p.stderr[-1500:]}
 if op=='search':
  term=str(c.get('term') or ''); roots=[safe(x)[0] for x in (c.get('roots') or ['eira2','extensions','tools'])]; lim=min(max(int(c.get('limit',100)),1),500); hits=[]
  for base in roots:
   if not base.exists(): continue
   for p in base.rglob('*'):
    if len(hits)>=lim: break
    if not p.is_file() or p.suffix.lower() not in {'.py','.json','.md','.txt','.html','.js'}: continue
    try: text=p.read_text(errors='replace')
    except Exception: continue
    if term in text: hits.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
  return {'term':term,'hits':hits}
 if op in {'reseal_manifest_row_preflight','surgical_reseal_package_preflight'}: return reseal_plan(c,False)
 if op in {'reseal_manifest_row','surgical_reseal_package'}: return reseal_plan(c,True)
 raise ValueError('unsupported_op')
def pending_commands():
 inbox=REPO/INBOX; done=STATE/'executed'; inbox.mkdir(parents=True,exist_ok=True); done.mkdir(parents=True,exist_ok=True)
 pending=[]
 for p in inbox.glob('*.json'):
  try: raw=p.read_bytes(); dig=sha_bytes(raw)
  except OSError: continue
  if (done/f'{dig}.json').exists(): continue
  pending.append((p,dig))
 pending.sort(key=lambda item:(item[0].stat().st_mtime,item[0].name),reverse=True)
 return pending
def process_bounded():
 done=STATE/'executed'; completed=[]
 for p,dig in pending_commands()[:MAX_COMMANDS_PER_CYCLE]:
  mark=done/f'{dig}.json'
  try:
   c=json.loads(p.read_text()); rid=str(c.get('id') or p.stem); op=str(c.get('op') or '')
   result=deploy(rid,c) if op=='deploy' else inspect(c)
   rec={'schema':SCHEMA,'id':rid,'op':op,'ok':True,'unix':time.time(),'result':result}
  except Exception as e: rec={'schema':SCHEMA,'id':p.stem,'ok':False,'unix':time.time(),'error':f'{type(e).__name__}:{e}'[:2500]}
  rec['command_sha256']=dig; atom(mark,rec); publish(OUTBOX/f"{rec['id']}.json",rec); completed.append(rec['id']); sync()
 return completed
def main():
 STATE.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   head=sync(); before=pending_commands(); s=snapshot({'git_head':head,'phase':'before_commands','pending_command_count':len(before)}); atom(STATE/'heartbeat.json',s); publish(TELEMETRY/'latest.json',s)
   sync(); completed=process_bounded(); head=sync(); after=pending_commands(); s=snapshot({'git_head':head,'phase':'after_commands','completed_this_cycle':completed,'pending_command_count':len(after)}); atom(STATE/'heartbeat.json',s); publish(TELEMETRY/'latest.json',s)
  except Exception as e: atom(STATE/'heartbeat.json',{'schema':SCHEMA,'version':VERSION,'unix':time.time(),'pid':os.getpid(),'ok':False,'error':f'{type(e).__name__}:{e}'[:2500]})
  time.sleep(INTERVAL)
if __name__=='__main__': main()
