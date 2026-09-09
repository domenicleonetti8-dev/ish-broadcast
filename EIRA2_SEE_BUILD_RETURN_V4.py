#!/usr/bin/env python3
from pathlib import Path
import json,os,subprocess,sys,time
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
STATE=ROOT/'eira_probe/see_build_receiver_v3'
REPO=STATE/'return_repo_v4'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
OUT='eira2_transport_bus/see_build_v3/outbox'

def run(cmd,cwd,timeout=90,check=True):
 r=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=timeout)
 if check and r.returncode: raise RuntimeError(f"{cmd[-1]} rc={r.returncode} stderr={r.stderr[-1200:]}")
 return r

def init_repo():
 REPO.mkdir(parents=True,exist_ok=True)
 if not (REPO/'.git').exists():
  run(['git','init'],REPO,20)
  run(['git','remote','add','origin',ORIGIN],REPO,20)
  run(['git','config','user.name','EIRA2-SEE-BUILD'],REPO,20)
  run(['git','config','user.email','eira2-see-build@localhost'],REPO,20)

def publish_one(src):
 rid=src.stem
 for _ in range(3):
  run(['git','fetch','--filter=blob:none','--depth','1','origin','master'],REPO,120)
  run(['git','checkout','-B','master','FETCH_HEAD'],REPO,20)
  dst=REPO/OUT/f'{rid}.json';dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(src.read_bytes())
  run(['git','add',str(dst.relative_to(REPO))],REPO,20)
  c=run(['git','commit','-m',f'Return SEE BUILD receipt {rid}'],REPO,20,False)
  if c.returncode!=0 and 'nothing to commit' not in (c.stdout+c.stderr).lower():raise RuntimeError(c.stderr[-1200:])
  p=run(['git','push','origin','HEAD:master'],REPO,120,False)
  if p.returncode==0:return True
  time.sleep(2)
 raise RuntimeError('push_failed_after_retries')

def main():
 init_repo();out=STATE/'outbox';pub=STATE/'published_v4';pub.mkdir(parents=True,exist_ok=True)
 n=0
 for src in sorted(out.glob('*.json')):
  mark=pub/src.name
  if mark.exists():continue
  publish_one(src);mark.write_text(json.dumps({'ok':True,'rid':src.stem,'unix':time.time()})+'\n');n+=1
 print(json.dumps({'ok':True,'published':n,'repo':str(REPO)}))
if __name__=='__main__':raise SystemExit(main())
