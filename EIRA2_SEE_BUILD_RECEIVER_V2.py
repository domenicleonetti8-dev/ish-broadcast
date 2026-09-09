#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
STATE=ROOT/'eira_probe/see_build_receiver_v2'
ENGINE=ROOT/'tools/eira2_see_build.py'
REPO='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
API='https://api.github.com/repos/domenicleonetti8-dev/ish-broadcast/contents/eira2_transport_bus/to_superprobe/requests?ref=master'
OUT='eira2_transport_bus/from_superprobe/see_build'

def get(u,t=20):
 q=urllib.request.Request(u,headers={'User-Agent':'EIRA2-SEE-BUILD-V2','Cache-Control':'no-cache'})
 with urllib.request.urlopen(q,timeout=t) as r:return r.read()
def run(a,cwd=None,t=30,check=True):
 r=subprocess.run(a,cwd=cwd or ROOT,text=True,capture_output=True,timeout=t)
 if check and r.returncode:raise RuntimeError((r.stderr or r.stdout)[-1500:])
 return r
def atomic(p,o):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+f'.tmp.{os.getpid()}');q.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');os.replace(q,p)
def repo():
 p=STATE/'return_repo'
 if not (p/'.git').exists():run(['git','clone','--depth','1',REPO,str(p)],STATE,40)
 return p
def publish(rid,rec):
 p=repo();run(['git','fetch','origin','master'],p,25);run(['git','reset','--hard','origin/master'],p,15)
 f=p/OUT/f'{rid}.json';atomic(f,rec);run(['git','add','--',str(f.relative_to(p))],p,10);c=run(['git','commit','-m',f'Return SEE BUILD receipt {rid}'],p,15,False)
 if c.returncode==0:run(['git','push','origin','master'],p,30)
def requests():
 arr=json.loads(get(API));out=[]
 for x in arr if isinstance(arr,list) else []:
  if x.get('type')!='file' or not str(x.get('name','')).endswith('.json'):continue
  try:
   r=json.loads(get(x['download_url']));rid=str(r.get('request_id') or '');op=r.get('operation')
   if op not in ('see','deploy') or not rid:continue
   if len(rid)>100 or not all(c.isalnum() or c in '._-' for c in rid):continue
   out.append((rid,r))
  except Exception:pass
 return out
def one(rid):
 done=STATE/'executed'/f'{rid}.json';pub=STATE/'published'/f'{rid}.json'
 if not done.exists():
  q=run([sys.executable,str(ENGINE),'--request-id',rid],ROOT,180,False)
  try:rec=json.loads((q.stdout or '').splitlines()[-1])
  except Exception:rec={'schema':'eira2_see_build_receiver_receipt_v2','request_id':rid,'ok':False,'returncode':q.returncode,'stdout_tail':(q.stdout or '')[-5000:],'stderr_tail':(q.stderr or '')[-3000:]}
  atomic(done,rec)
 else:rec=json.loads(done.read_text())
 if not pub.exists():publish(rid,rec);atomic(pub,{'ok':True,'request_id':rid,'unix':time.time()})
def main():
 STATE.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   for rid,_ in requests():one(rid)
   atomic(STATE/'heartbeat.json',{'ok':True,'pid':os.getpid(),'unix':time.time()})
  except KeyboardInterrupt:return 0
  except Exception as e:atomic(STATE/'heartbeat.json',{'ok':False,'pid':os.getpid(),'error':f'{type(e).__name__}:{e}','unix':time.time()})
  time.sleep(8)
if __name__=='__main__':raise SystemExit(main())
