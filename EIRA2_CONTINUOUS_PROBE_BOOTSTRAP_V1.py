#!/usr/bin/env python3
from pathlib import Path
import os, subprocess, textwrap

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
PROBE=ROOT/'eira_probe'/'eira_continuous_probe.py'
UNIT=Path.home()/'.config/systemd/user/eira-continuous-probe.service'

probe=r'''#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'eira_probe'/'orin_continuous_probe_v1'; REPO=STATE/'repo'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
REMOTE=Path('eira2_continuous_probe'); TELEMETRY=REMOTE/'telemetry'; INBOX=REMOTE/'inbox'; OUTBOX=REMOTE/'outbox'
SCHEMA='eira2_continuous_probe_v1'; VERSION='1.0.0'; INTERVAL=10.0
ENV={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_HTTP_LOW_SPEED_LIMIT':'1024','GIT_HTTP_LOW_SPEED_TIME':'15'}
CORE=['main.py','eira2/__main__.py','eira2/runtime.py','eira2/conversation/spine.py','eira2/conversation/analysis.py','eira2/reasoning/provider.py','eira2/operations/package_identity.py','eira2/evidence/universe_public_library.py','tools/eira2_orin_build_probe.py']
def atom(p,o): p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def run(c,cwd=None,timeout=35,check=True):
 p=subprocess.run(c,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False,env=ENV)
 if check and p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1500:])
 return p
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''): h.update(c)
 return h.hexdigest()
def sync():
 STATE.mkdir(parents=True,exist_ok=True)
 if not (REPO/'.git').is_dir():
  if REPO.exists(): shutil.rmtree(REPO)
  run(['git','clone','--quiet','--depth','1','--branch','master',ORIGIN,str(REPO)],timeout=60)
 else: run(['git','fetch','--quiet','--depth','1','origin','master'],REPO)
 run(['git','checkout','--quiet','-B','continuous_probe_runtime','origin/master'],REPO,timeout=20)
 run(['git','reset','--hard','origin/master'],REPO,timeout=20)
 return run(['git','rev-parse','HEAD'],REPO,timeout=10).stdout.strip()
def snapshot():
 rows=[]
 for rel in CORE:
  p=ROOT/rel; rows.append({'path':rel,'exists':p.is_file(),'bytes':p.stat().st_size if p.is_file() else None,'sha256':sha(p) if p.is_file() else None})
 pkg={}; m=ROOT/'eira2-package-manifest.json'; lib=ROOT/'eira2/evidence/universe_public_library.py'
 if m.is_file(): pkg={'manifest_bytes':m.stat().st_size,'manifest_sha256':sha(m)}
 if lib.is_file(): pkg['library_live']={'bytes':lib.stat().st_size,'sha256':sha(lib)}
 ps=run(['ps','-eo','pid,etimes,comm,args'],timeout=10,check=False).stdout.splitlines(); procs=[x[-400:] for x in ps if 'eira' in x.lower() or 'orin' in x.lower()][:40]
 return {'schema':SCHEMA,'version':VERSION,'unix':time.time(),'pid':os.getpid(),'root':str(ROOT),'core':rows,'package':pkg,'processes':procs}
def publish(rel,payload):
 sync(); p=REPO/rel; atom(p,payload); run(['git','add',rel.as_posix()],REPO,timeout=10)
 if run(['git','diff','--cached','--quiet'],REPO,timeout=10,check=False).returncode:
  run(['git','-c','user.name=EIRA Continuous Probe','-c','user.email=eira-probe@localhost','commit','--quiet','-m',f'Continuous probe {rel.name}'],REPO,timeout=20)
  run(['git','pull','--rebase','--quiet','origin','master'],REPO,timeout=35); run(['git','push','--quiet','origin','HEAD:master'],REPO,timeout=35)
def safe(v):
 p=Path(str(v or ''))
 if p.is_absolute() or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe_path')
 q=(ROOT/p).resolve()
 if q!=ROOT and ROOT not in q.parents: raise ValueError('outside_live')
 return q,p
def process():
 inbox=REPO/INBOX; inbox.mkdir(parents=True,exist_ok=True); done=STATE/'executed'; done.mkdir(parents=True,exist_ok=True)
 for p in sorted(inbox.glob('*.json')):
  dig=hashlib.sha256(p.read_bytes()).hexdigest(); mark=done/f'{dig}.json'
  if mark.exists(): continue
  try:
   c=json.loads(p.read_text()); rid=str(c.get('id') or p.stem); op=str(c.get('op') or '')
   if op=='health': result=snapshot()
   elif op=='read':
    q,r=safe(c.get('path')); b=q.read_bytes(); lim=min(max(int(c.get('max_bytes',200000)),1),1000000); result={'path':str(r),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'text':b[:lim].decode('utf-8','replace'),'truncated':len(b)>lim}
   elif op=='list':
    q,r=safe(c.get('path') or '.'); result={'path':str(r),'items':[x.name for x in sorted(q.iterdir())[:1000]]}
   elif op=='upgrade':
    src=c.get('source') or {}; commit=str(src.get('commit') or ''); path=str(src.get('path') or '')
    if len(commit)!=40: raise ValueError('invalid_commit')
    raw=subprocess.run(['git','-C',str(REPO),'show',f'{commit}:{path}'],capture_output=True,timeout=30,check=False).stdout; compile(raw.decode(),'<upgrade>','exec'); dg=hashlib.sha256(raw).hexdigest(); cand=STATE/'versions'/f'probe_{dg[:16]}.py'; cand.parent.mkdir(parents=True,exist_ok=True); cand.write_bytes(raw); result={'candidate':str(cand),'sha256':dg,'staged':True}
   else: raise ValueError('unsupported_op')
   rec={'schema':SCHEMA,'id':rid,'op':op,'ok':True,'unix':time.time(),'result':result}
  except Exception as e: rec={'schema':SCHEMA,'id':p.stem,'ok':False,'unix':time.time(),'error':f'{type(e).__name__}:{e}'[:2000]}
  atom(mark,rec); publish(OUTBOX/f"{rec['id']}.json",rec); sync()
def main():
 STATE.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   head=sync(); s=snapshot(); s['git_head']=head; atom(STATE/'heartbeat.json',s); publish(TELEMETRY/'latest.json',s); sync(); process()
  except Exception as e: atom(STATE/'heartbeat.json',{'schema':SCHEMA,'version':VERSION,'unix':time.time(),'pid':os.getpid(),'ok':False,'error':f'{type(e).__name__}:{e}'[:2000]})
  time.sleep(INTERVAL)
if __name__=='__main__': main()
'''
unit='''[Unit]\nDescription=EIRA Continuous Evidence Probe\nAfter=network-online.target\nWants=network-online.target\nStartLimitIntervalSec=0\n\n[Service]\nType=simple\nWorkingDirectory=/media/domenicleonetti/easystore/EIRA/LIVE\nExecStart=/usr/bin/python3 /media/domenicleonetti/easystore/EIRA/LIVE/eira_probe/eira_continuous_probe.py\nRestart=always\nRestartSec=2\nKillMode=control-group\nTimeoutStopSec=10\n\n[Install]\nWantedBy=default.target\n'''
PROBE.parent.mkdir(parents=True,exist_ok=True); UNIT.parent.mkdir(parents=True,exist_ok=True)
compile(probe,str(PROBE),'exec')
pt=PROBE.with_suffix('.tmp'); pt.write_text(probe); os.replace(pt,PROBE)
ut=UNIT.with_suffix('.tmp'); ut.write_text(unit); os.replace(ut,UNIT)
subprocess.run(['python3','-m','py_compile',str(PROBE)],check=True)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','eira-continuous-probe.service'],check=True)
print('EIRA_CONTINUOUS_PROBE=STARTED')
