#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
REPO=ROOT
STATE=ROOT/'eira_probe/orin_mailbox_v4'
BRIDGE=ROOT/'tools/eira2_orin_direct_bridge.py'
REMOTE='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
CMD='eira2_transport_bus/to_superprobe/bridge_commands'
OUT='eira2_transport_bus/from_superprobe/orin_mailbox'
POLL=5

def run(a,timeout=30,check=True):
 r=subprocess.run(a,cwd=REPO,text=True,capture_output=True,timeout=timeout)
 if check and r.returncode: raise RuntimeError((r.stderr or r.stdout)[-1200:])
 return r
def git(*a,timeout=30,check=True):return run(['git',*a],timeout,check)
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+f'.tmp.{os.getpid()}');t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(t,p)
def publish(rid,rec):
 git('fetch','origin','master',timeout=20);git('checkout','master',timeout=10);git('pull','--rebase','origin','master',timeout=25)
 p=REPO/OUT/f'{rid}.json';write(p,rec);git('add','--',str(p.relative_to(REPO)));git('commit','-m',f'EIRA receipt {rid}',timeout=15,check=False);git('push','origin','master',timeout=25)
def commands():
 git('fetch','origin','master',timeout=20);git('checkout','master',timeout=10);git('reset','--hard','origin/master',timeout=10)
 d=REPO/CMD
 if not d.exists():return []
 out=[]
 for p in sorted(d.glob('*.json')):
  try:
   x=json.loads(p.read_text());rid=str(x.get('request_id') or '')
   if rid and len(rid)<100 and all(c.isalnum() or c in '._-' for c in rid):out.append((rid,x))
  except Exception:pass
 return out
def one(rid,cmd):
 marker=STATE/'processed'/f'{rid}.json'
 if marker.exists():return
 started=time.time();q=run([sys.executable,str(BRIDGE),'--request-id',rid],timeout=150,check=False)
 rec={'schema':'eira2_orin_mailbox_receipt_v4','request_id':rid,'ok':q.returncode==0,'returncode':q.returncode,'stdout_tail':(q.stdout or '')[-7000:],'stderr_tail':(q.stderr or '')[-3000:],'started_unix':started,'completed_unix':time.time()}
 write(STATE/'receipts'/f'{rid}.json',rec);publish(rid,rec)
 if rec['ok']:write(marker,rec)
def main():
 STATE.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   for rid,cmd in commands():one(rid,cmd)
   write(STATE/'heartbeat.json',{'ok':True,'pid':os.getpid(),'unix':time.time()})
  except KeyboardInterrupt:return 0
  except Exception as e:write(STATE/'heartbeat.json',{'ok':False,'pid':os.getpid(),'error':f'{type(e).__name__}:{e}','unix':time.time()})
  time.sleep(POLL)
if __name__=='__main__':raise SystemExit(main())
