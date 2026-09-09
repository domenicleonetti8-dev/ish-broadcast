#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE=ROOT/'.orin_relay'
REPO_URL='https://github.com/domenicleonetti8-dev/ish-broadcast.git'
API='https://api.github.com/repos/domenicleonetti8-dev/ish-broadcast/contents/eira2_transport_bus/to_superprobe/bridge_commands?ref=master'
RAW='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master'
BRIDGE=ROOT/'tools/eira2_orin_direct_bridge.py'
OUT='eira2_transport_bus/from_superprobe/orin_relay'

def get(url,timeout=15):
 req=urllib.request.Request(url,headers={'User-Agent':'EIRA2-Orin-Relay-V5','Cache-Control':'no-cache'})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
def run(a,timeout=30,check=True,cwd=None):
 r=subprocess.run(a,cwd=cwd or ROOT,text=True,capture_output=True,timeout=timeout)
 if check and r.returncode:raise RuntimeError((r.stderr or r.stdout)[-1500:])
 return r
def atomic(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+f'.tmp.{os.getpid()}');q.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n');os.replace(q,p)
def ensure_bridge():
 data=get(RAW+'/EIRA2_ORIN_DIRECT_BRIDGE_V2.py')
 BRIDGE.parent.mkdir(parents=True,exist_ok=True)
 if not BRIDGE.exists() or BRIDGE.read_bytes()!=data:
  q=BRIDGE.with_suffix('.tmp');q.write_bytes(data);os.replace(q,BRIDGE)
 run([sys.executable,'-m','py_compile',str(BRIDGE)],20)
def mailbox_repo():
 p=STATE/'mail'
 if not (p/'.git').exists():run(['git','clone','--depth','1',REPO_URL,str(p)],30,cwd=STATE)
 return p
def publish(rid,rec):
 p=mailbox_repo();run(['git','fetch','origin','master'],20,cwd=p);run(['git','reset','--hard','origin/master'],15,cwd=p)
 f=p/OUT/f'{rid}.json';atomic(f,rec);run(['git','add','--',str(f.relative_to(p))],10,cwd=p)
 run(['git','commit','-m',f'Orin relay receipt {rid}'],15,False,p)
 run(['git','push','origin','master'],25,True,p)
def cmds():
 arr=json.loads(get(API));out=[]
 for x in arr if isinstance(arr,list) else []:
  if x.get('type')!='file' or not str(x.get('name','')).endswith('.json'):continue
  try:
   c=json.loads(get(x['download_url']));rid=str(c.get('request_id',''))
   if rid and len(rid)<100 and all(ch.isalnum() or ch in '._-' for ch in rid):out.append((rid,c))
  except Exception:pass
 return out
def execute(rid):
 done=STATE/'done'/f'{rid}.json'
 if done.exists():return
 t=time.time();r=run([sys.executable,str(BRIDGE),'--request-id',rid],150,False)
 rec={'schema':'eira2_orin_embedded_relay_receipt_v5','relay':'independent_of_eira_probe','request_id':rid,'ok':r.returncode==0,'returncode':r.returncode,'stdout':(r.stdout or '')[-9000:],'stderr':(r.stderr or '')[-4000:],'started_unix':t,'completed_unix':time.time()}
 atomic(STATE/'receipts'/f'{rid}.json',rec)
 try:publish(rid,rec);rec['published']=True
 except Exception as e:rec['published']=False;rec['publish_error']=f'{type(e).__name__}:{e}';atomic(STATE/'receipts'/f'{rid}.json',rec);return
 atomic(done,rec)
def main():
 STATE.mkdir(parents=True,exist_ok=True);ensure_bridge()
 while True:
  try:
   for rid,_ in cmds():execute(rid)
   atomic(STATE/'heartbeat.json',{'ok':True,'pid':os.getpid(),'unix':time.time()})
  except KeyboardInterrupt:return 0
  except Exception as e:atomic(STATE/'heartbeat.json',{'ok':False,'pid':os.getpid(),'error':f'{type(e).__name__}:{e}','unix':time.time()})
  time.sleep(5)
if __name__=='__main__':raise SystemExit(main())
