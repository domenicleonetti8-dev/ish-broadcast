#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,signal,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
from typing import Any
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve(); STATE=ROOT/'eira_probe'/'orin_build_probe_v3'; REPO=STATE/'repo'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'; INBOX=Path('eira2_build_probe/inbox'); OUTBOX=Path('eira2_build_probe/outbox')
SCHEMA='eira2_orin_build_probe_v3'; VERSION='3.3-eira-invoke'; POLL=3.0; UPGRADE_DIR=ROOT/'eira_probe'/'orin_build_probe_versions'; UPGRADE_REQUEST=ROOT/'eira_probe'/'orin_build_probe_supervisor_v3'/'upgrade_request.json'
LEGACY_STATE=ROOT/'eira_probe'/'orin_build_probe_v1'; LEGACY_HEARTBEAT=LEGACY_STATE/'heartbeat.json'; LEGACY_DORMANT=LEGACY_STATE/'DORMANT.json'
MANIFEST=ROOT/'eira2-package-manifest.json'; PUBLIC_LIBRARY='eira2/evidence/universe_public_library.py'; EIRA_URL='http://127.0.0.1:8782/v1/text'; EIRA_LOG=ROOT/'var'/'orin_eira_start.log'
GIT_ENV={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_HTTP_LOW_SPEED_LIMIT':'1024','GIT_HTTP_LOW_SPEED_TIME':'20'}
def atom(p,obj): p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def hb(phase,ok=True,**kw): atom(STATE/'heartbeat.json',{'schema':SCHEMA,'ok':ok,'phase':phase,'pid':os.getpid(),'unix':time.time(),'version':VERSION,**kw})
def run(cmd,cwd=None,timeout=45,check=True):
 p=subprocess.run(cmd,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False,env=GIT_ENV)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2500:])
 return p
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()
def safe_rel(v):
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe_path')
 out=(ROOT/p).resolve()
 if out!=ROOT and ROOT not in out.parents: raise ValueError('outside_live')
 return out
def sync():
 STATE.mkdir(parents=True,exist_ok=True); hb('sync_start')
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  run(['git','clone','--quiet','--depth','1','--branch','master',ORIGIN,str(REPO)],timeout=60)
 else: run(['git','fetch','--quiet','--depth','1','origin','master'],REPO,timeout=45)
 for cmd in (['git','checkout','--quiet','-B','orin_build_probe_runtime','FETCH_HEAD' if (REPO/'.git').is_dir() else 'origin/master'],['git','reset','--hard','FETCH_HEAD'],['git','clean','-fd']):
  try: run(cmd,REPO,timeout=20)
  except Exception:
   if cmd[1]=='checkout': run(['git','checkout','--quiet','-B','orin_build_probe_runtime','origin/master'],REPO,timeout=20)
   elif cmd[1]=='reset': run(['git','reset','--hard','origin/master'],REPO,timeout=20)
   else: raise
 head=run(['git','rev-parse','HEAD'],REPO,timeout=10).stdout.strip(); hb('synced',head=head); return head
def publish(rid,rec):
 sync(); rel=OUTBOX/f'{rid}.json'; p=REPO/rel; atom(p,rec); run(['git','add',rel.as_posix()],REPO,timeout=10)
 if run(['git','diff','--cached','--quiet'],REPO,timeout=10,check=False).returncode!=0:
  run(['git','-c','user.name=EIRA Orin Build Probe','-c','user.email=eira-build-probe@localhost','commit','--quiet','-m',f'Build probe receipt {rid}'],REPO,timeout=20)
  run(['git','pull','--rebase','--quiet','origin','master'],REPO,timeout=45); run(['git','push','--quiet','origin','HEAD:master'],REPO,timeout=45)
 return run(['git','rev-parse','HEAD'],REPO,timeout=10).stdout.strip()
def git_blob(commit,path):
 if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise ValueError('invalid_commit')
 rel=Path(path)
 if rel.is_absolute() or '..' in rel.parts or not rel.parts: raise ValueError('invalid_repo_path')
 p=subprocess.run(['git','-C',str(REPO),'show',f'{commit}:{rel.as_posix()}'],capture_output=True,timeout=30,check=False)
 if p.returncode: raise RuntimeError('source_blob_missing:'+p.stderr[-1200:].decode(errors='replace'))
 return p.stdout
def backup(rid,target):
 if not target.is_file(): return None
 rel=target.relative_to(ROOT); dst=STATE/'backups'/rid/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,dst); return str(dst.relative_to(ROOT))
def deploy(rid,cmd):
 src=cmd.get('source') or {}; target=safe_rel(cmd.get('target_path') or ''); raw=git_blob(str(src.get('commit') or ''),str(src.get('path') or '')); expected=str(src.get('sha256') or '').lower(); digest=sha_bytes(raw)
 if expected and digest!=expected: raise RuntimeError('source_sha256_mismatch')
 if target.suffix=='.py': compile(raw.decode('utf-8'),str(target),'exec')
 before=target.read_bytes() if target.is_file() else None; bak=backup(rid,target); target.parent.mkdir(parents=True,exist_ok=True); tmp=target.with_name(target.name+'.tmp.build_probe'); tmp.write_bytes(raw); os.replace(tmp,target)
 if sha_file(target)!=digest:
  if before is None: target.unlink(missing_ok=True)
  else: target.write_bytes(before)
  raise RuntimeError('post_write_hash_mismatch_rolled_back')
 if target.suffix=='.py': run(['python3','-m','py_compile',str(target)],timeout=30)
 return {'target_path':str(target.relative_to(ROOT)),'before_sha256':sha_bytes(before) if before is not None else None,'after_sha256':digest,'backup':bak,'compile_ok':target.suffix=='.py'}
def stage_upgrade(rid,cmd):
 src=cmd.get('source') or {}; raw=git_blob(str(src.get('commit') or ''),str(src.get('path') or '')); digest=sha_bytes(raw); expected=str(src.get('sha256') or '').lower()
 if expected and digest!=expected: raise RuntimeError('source_sha256_mismatch')
 compile(raw.decode('utf-8'),'<probe-upgrade>','exec'); UPGRADE_DIR.mkdir(parents=True,exist_ok=True); cand=UPGRADE_DIR/f'probe_{digest[:16]}.py'; cand.write_bytes(raw); run(['python3','-m','py_compile',str(cand)],timeout=30)
 atom(UPGRADE_REQUEST,{'schema':'eira2_orin_build_probe_upgrade_v1','id':rid,'candidate':str(cand.relative_to(ROOT)),'sha256':digest,'requested_unix':time.time()}); return {'candidate':str(cand.relative_to(ROOT)),'sha256':digest,'handoff':'supervisor_v3'}
def isolate_legacy_v1():
 if not LEGACY_HEARTBEAT.is_file(): return {'already_dormant':True,'reason':'legacy_heartbeat_missing','marker':str(LEGACY_DORMANT.relative_to(ROOT))}
 data=json.loads(LEGACY_HEARTBEAT.read_text()); pid=int(data.get('pid') or 0)
 if pid<=1 or pid==os.getpid(): raise RuntimeError('invalid_legacy_pid')
 proc=Path('/proc')/str(pid); cmdp=proc/'cmdline'
 if not cmdp.is_file():
  atom(LEGACY_DORMANT,{'schema':'eira2_legacy_build_probe_dormant_v1','ok':True,'pid':pid,'state':'not_running','unix':time.time()}); return {'already_dormant':True,'pid':pid,'reason':'process_absent','marker':str(LEGACY_DORMANT.relative_to(ROOT))}
 cmdline=cmdp.read_bytes().replace(b'\0',b' ').decode('utf-8','replace')
 if 'eira2_orin_build_probe.py' not in cmdline: raise RuntimeError('legacy_pid_cmdline_mismatch')
 os.kill(pid,signal.SIGTERM); deadline=time.time()+8.0
 while time.time()<deadline and proc.exists(): time.sleep(0.1)
 alive=proc.exists(); atom(LEGACY_DORMANT,{'schema':'eira2_legacy_build_probe_dormant_v1','ok':not alive,'pid':pid,'state':'dormant' if not alive else 'terminate_sent','cmdline':cmdline,'unix':time.time()})
 if alive: raise RuntimeError('legacy_v1_did_not_exit_after_sigterm')
 return {'isolated':True,'pid':pid,'state':'dormant','marker':str(LEGACY_DORMANT.relative_to(ROOT))}
def canonical_bytes(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def tree_hash(files): return hashlib.sha256(canonical_bytes(files)).hexdigest()
def reseal_public_library_manifest(cmd):
 path=str(cmd.get('path') or '')
 if path!=PUBLIC_LIBRARY: raise ValueError('reseal_path_not_allowed')
 target=ROOT/path; old_size=int(cmd.get('expected_old_size')); old_sha=str(cmd.get('expected_old_sha256') or '').lower(); new_size=int(cmd.get('expected_live_size')); new_sha=str(cmd.get('expected_live_sha256') or '').lower()
 if not MANIFEST.is_file() or not target.is_file(): raise RuntimeError('manifest_or_target_missing')
 if target.stat().st_size!=new_size or sha_file(target)!=new_sha: raise RuntimeError('live_library_evidence_mismatch')
 original=MANIFEST.read_bytes(); manifest=json.loads(original.decode('utf-8')); files=manifest.get('files')
 if not isinstance(files,list): raise RuntimeError('manifest_files_invalid')
 matches=[r for r in files if isinstance(r,dict) and r.get('path')==path]
 if len(matches)!=1: raise RuntimeError('manifest_row_count_invalid')
 row=matches[0]
 if int(row.get('size',-1))!=old_size or str(row.get('sha256') or '').lower()!=old_sha: raise RuntimeError('manifest_stale_row_mismatch')
 before_tree=str(manifest.get('package_tree_sha256') or ''); row['size']=new_size; row['sha256']=new_sha; after_tree=tree_hash(files); manifest['package_tree_sha256']=after_tree
 backup_path=STATE/'backups'/str(cmd.get('id') or 'reseal')/'eira2-package-manifest.json'; backup_path.parent.mkdir(parents=True,exist_ok=True); backup_path.write_bytes(original)
 tmp=MANIFEST.with_name(MANIFEST.name+'.tmp.reseal'); tmp.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8'); os.chmod(tmp,0o600); os.replace(tmp,MANIFEST)
 try:
  check=json.loads(MANIFEST.read_text()); rows=[r for r in check.get('files',[]) if isinstance(r,dict) and r.get('path')==path]
  if len(rows)!=1 or rows[0].get('size')!=new_size or str(rows[0].get('sha256') or '').lower()!=new_sha: raise RuntimeError('post_reseal_row_verify_failed')
  if str(check.get('package_tree_sha256') or '')!=tree_hash(check.get('files',[])): raise RuntimeError('post_reseal_tree_verify_failed')
  if target.stat().st_size!=new_size or sha_file(target)!=new_sha: raise RuntimeError('library_changed_during_reseal')
 except Exception: MANIFEST.write_bytes(original); raise
 return {'path':path,'manifest_backup':str(backup_path.relative_to(ROOT)),'tree_before':before_tree,'tree_after':after_tree,'library_size':new_size,'library_sha256':new_sha,'manifest_sha256':sha_file(MANIFEST)}
def post_eira(text):
 payload=json.dumps({'text':text,'source':'orin_canonical_text_probe'}).encode('utf-8'); req=urllib.request.Request(EIRA_URL,data=payload,headers={'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=300) as r: return json.loads(r.read().decode('utf-8'))
def invoke_eira_text_turn(cmd):
 text=' '.join(str(cmd.get('text') or '').split())
 if not text: raise ValueError('empty_eira_turn')
 try: response=post_eira(text); return {'started':False,'endpoint':EIRA_URL,'response':response}
 except Exception as first:
  main=ROOT/'main.py'
  if not main.is_file(): raise RuntimeError('canonical_main_missing')
  EIRA_LOG.parent.mkdir(parents=True,exist_ok=True); log=EIRA_LOG.open('ab',buffering=0)
  proc=subprocess.Popen([sys.executable,str(main)],cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,env=GIT_ENV)
  deadline=time.time()+35.0; last=first
  while time.time()<deadline:
   if proc.poll() is not None: break
   try:
    response=post_eira(text); return {'started':True,'pid':proc.pid,'endpoint':EIRA_URL,'response':response}
   except Exception as e: last=e; time.sleep(1.0)
  tail=''
  try: tail=EIRA_LOG.read_text(errors='replace')[-5000:]
  except Exception: pass
  raise RuntimeError(f'eira_turn_failed:{type(last).__name__}:{last};startup_pid={proc.pid};returncode={proc.poll()};log_tail={tail}')
def inspect(cmd):
 op=str(cmd.get('op') or '')
 if op=='read':
  p=safe_rel(cmd.get('path') or ''); b=p.read_bytes(); lim=min(max(int(cmd.get('max_bytes',500000)),1),2000000); return {'path':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':sha_bytes(b),'text':b[:lim].decode('utf-8','replace'),'truncated':len(b)>lim}
 if op=='list':
  p=safe_rel(cmd.get('path') or '.'); lim=min(max(int(cmd.get('limit',500)),1),5000); return {'path':str(p.relative_to(ROOT)) if p!=ROOT else '.','items':[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:lim]]}
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
  p=safe_rel(cmd.get('path') or ''); q=run(['python3','-m','py_compile',str(p)],timeout=30,check=False); return {'path':str(p.relative_to(ROOT)),'ok':q.returncode==0,'returncode':q.returncode,'stderr':q.stderr[-2000:]}
 if op=='health': return {'root':str(ROOT),'state':str(STATE),'repo':str(REPO),'pid':os.getpid(),'version':VERSION,'capabilities':['read','list','search','compile','health','deploy','upgrade_probe','isolate_legacy_v1','reseal_public_library_manifest','invoke_eira_text_turn']}
 raise ValueError('unsupported_op')
def execute(cmd):
 rid=str(cmd.get('id') or '').strip(); op=str(cmd.get('op') or '').strip()
 if not rid: raise ValueError('missing_id')
 base={'schema':SCHEMA,'id':rid,'op':op,'root':str(ROOT),'unix':time.time()}
 if op=='deploy': base.update(ok=True,result=deploy(rid,cmd))
 elif op=='upgrade_probe': base.update(ok=True,result=stage_upgrade(rid,cmd))
 elif op=='isolate_legacy_v1': base.update(ok=True,result=isolate_legacy_v1())
 elif op=='reseal_public_library_manifest': base.update(ok=True,result=reseal_public_library_manifest(cmd))
 elif op=='invoke_eira_text_turn': base.update(ok=True,result=invoke_eira_text_turn(cmd))
 else: base.update(ok=True,result=inspect(cmd))
 return base
def loop(interval):
 executed=STATE/'executed'; executed.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   sync(); inbox=REPO/INBOX; inbox.mkdir(parents=True,exist_ok=True)
   for p in sorted(inbox.glob('*.json')):
    raw=p.read_bytes(); digest=sha_bytes(raw); marker=executed/f'{digest}.json'
    if marker.exists(): continue
    try: rec=execute(json.loads(raw.decode()))
    except Exception as e: rec={'schema':SCHEMA,'id':p.stem,'ok':False,'error':f'{type(e).__name__}:{e}'[:7000],'unix':time.time(),'root':str(ROOT)}
    rec['command_sha256']=digest; atom(marker,rec); rec['return_commit']=publish(str(rec.get('id') or p.stem),rec)
    if rec.get('ok') and rec.get('op')=='upgrade_probe': return
   hb('idle'); time.sleep(max(1.0,interval))
  except Exception as e: hb('error',False,error=f'{type(e).__name__}:{e}'[:2500]); time.sleep(max(2.0,interval))
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--interval',type=float,default=POLL); ap.add_argument('--once',action='store_true'); a=ap.parse_args()
 if a.once: print(json.dumps({'schema':SCHEMA,'ok':True,'head':sync(),'root':str(ROOT),'version':VERSION},indent=2)); return
 loop(a.interval)
if __name__=='__main__': main()
