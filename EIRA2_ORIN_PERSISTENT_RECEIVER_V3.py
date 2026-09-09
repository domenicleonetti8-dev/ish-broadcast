#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
RAW='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master'
API='https://api.github.com/repos/domenicleonetti8-dev/ish-broadcast/contents/eira2_transport_bus/to_superprobe/bridge_commands?ref=master'
STATE=ROOT/'eira_probe/orin_receiver_v3'
BRIDGE=ROOT/'tools/eira2_orin_direct_bridge.py'
POLL=5

def get(url,timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':'EIRA2-Orin-Receiver-V3','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
def atomic(p,b):
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+f'.tmp.{os.getpid()}');t.write_bytes(b);os.replace(t,p)
def js(p,v):atomic(p,(json.dumps(v,indent=2,sort_keys=True)+'\n').encode())
def safe_id(v):
    s=str(v or '');
    if not s or len(s)>96 or any(not(c.isalnum() or c in '._-') for c in s):raise RuntimeError('unsafe_id')
    return s
def heartbeat(status='running',error=None):js(STATE/'heartbeat.json',{'schema':'eira2_orin_receiver_v3','status':status,'pid':os.getpid(),'error':error,'unix':time.time()})
def commands():
    rows=json.loads(get(API)); out=[]
    for r in rows:
        if r.get('type')!='file' or not str(r.get('name','')).endswith('.json'):continue
        try:
            cmd=json.loads(get(r['download_url'])); rid=safe_id(cmd.get('request_id'))
            out.append((rid,cmd,r.get('sha')))
        except Exception as e:js(STATE/'errors'/f"command_{int(time.time()*1000)}.json",{'error':f'{type(e).__name__}:{e}'})
    return out
def run_one(rid,cmd,blobsha):
    done=STATE/'processed'/f'{rid}.json'
    if done.exists():return
    kind=str(cmd.get('kind') or 'request')
    if kind not in {'request','deploy'}:return
    started=time.time()
    q=subprocess.run([sys.executable,str(BRIDGE),'--request-id',rid],cwd=ROOT,text=True,capture_output=True,timeout=150)
    rec={'schema':'eira2_orin_receiver_receipt_v3','request_id':rid,'command_blob_sha':blobsha,'ok':q.returncode==0,'returncode':q.returncode,'stdout_tail':(q.stdout or '')[-6000:],'stderr_tail':(q.stderr or '')[-3000:],'started_unix':started,'completed_unix':time.time()}
    js(STATE/'receipts'/f'{rid}.json',rec)
    if q.returncode==0:js(done,rec)
    else:raise RuntimeError('job_failed:'+rid+':'+rec['stderr_tail'][-800:])
def main():
    STATE.mkdir(parents=True,exist_ok=True); heartbeat()
    while True:
        try:
            heartbeat();
            for rid,cmd,bsha in commands():run_one(rid,cmd,bsha)
            heartbeat()
        except KeyboardInterrupt:
            heartbeat('stopped');return 0
        except Exception as e:
            heartbeat('degraded',f'{type(e).__name__}:{e}');js(STATE/'errors'/f'{int(time.time()*1000)}.json',{'error':f'{type(e).__name__}:{e}','unix':time.time()})
        time.sleep(POLL)
if __name__=='__main__':raise SystemExit(main())
