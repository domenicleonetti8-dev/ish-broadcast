#!/usr/bin/env python3
from pathlib import Path
import json,os,subprocess,time
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
STATE=ROOT/'eira_probe/see_build_receiver_v3'
REPO=STATE/'return_repo_v5'
ORIGIN='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
OUT='eira2_transport_bus/see_build_v3/outbox'

def run(cmd,timeout=120,check=True,env=None):
 r=subprocess.run(cmd,cwd=REPO,text=True,capture_output=True,timeout=timeout,env=env)
 if check and r.returncode: raise RuntimeError(f"{cmd[1] if len(cmd)>1 else cmd[0]} rc={r.returncode} stderr={r.stderr[-1200:]}")
 return r

def init_repo():
 REPO.mkdir(parents=True,exist_ok=True)
 if not (REPO/'.git').exists():
  run(['git','init'],20)
  run(['git','remote','add','origin',ORIGIN],20)
  run(['git','config','user.name','EIRA2-SEE-BUILD'],20)
  run(['git','config','user.email','eira2-see-build@localhost'],20)

def publish_one(src):
 rid=src.stem
 for _ in range(3):
  run(['git','fetch','--depth','1','origin','master'],180)
  parent=run(['git','rev-parse','FETCH_HEAD'],20).stdout.strip()
  base_tree=run(['git','rev-parse',f'{parent}^{{tree}}'],20).stdout.strip()
  blob=run(['git','hash-object','-w',str(src)],20).stdout.strip()
  env=os.environ.copy();env['GIT_INDEX_FILE']=str(REPO/'.index_v5')
  try:
   run(['git','read-tree',base_tree],20,env=env)
   run(['git','update-index','--add','--cacheinfo','100644',blob,f'{OUT}/{rid}.json'],20,env=env)
   tree=run(['git','write-tree'],20,env=env).stdout.strip()
  finally:
   Path(env['GIT_INDEX_FILE']).unlink(missing_ok=True)
  msg=f'Return SEE BUILD receipt {rid}'
  commit=run(['git','commit-tree',tree,'-p',parent],20,env={**os.environ,'GIT_AUTHOR_NAME':'EIRA2-SEE-BUILD','GIT_AUTHOR_EMAIL':'eira2-see-build@localhost','GIT_COMMITTER_NAME':'EIRA2-SEE-BUILD','GIT_COMMITTER_EMAIL':'eira2-see-build@localhost'},check=False)
  if commit.returncode: raise RuntimeError(commit.stderr[-1200:])
  sha=commit.stdout.strip()
  p=run(['git','push','origin',f'{sha}:refs/heads/master'],180,False)
  if p.returncode==0:return sha
  time.sleep(2)
 raise RuntimeError('push_failed_after_retries')

def main():
 init_repo();out=STATE/'outbox';pub=STATE/'published_v5';pub.mkdir(parents=True,exist_ok=True)
 n=0;last=None
 for src in sorted(out.glob('*.json')):
  mark=pub/src.name
  if mark.exists():continue
  last=publish_one(src);mark.write_text(json.dumps({'ok':True,'rid':src.stem,'commit':last,'unix':time.time()})+'\n');n+=1
 print(json.dumps({'ok':True,'published':n,'commit':last,'checkout':False,'repo':str(REPO)}))
if __name__=='__main__':raise SystemExit(main())
