#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,sys,time,urllib.error,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
STATE=ROOT/'eira_probe/see_build_receiver_v3'
ENGINE=ROOT/'tools/eira2_see_build.py'
RAW='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/'
INBOX='eira2_transport_bus/see_build_v3/inbox'
OUTBOX='eira2_transport_bus/see_build_v3/outbox'
LIST='https://api.github.com/repos/domenicleonetti8-dev/ish-broadcast/contents/'+INBOX+'?ref=master'

def req(u,t=20):
 q=urllib.request.Request(u,headers={'User-Agent':'EIRA2-SEE-BUILD-V3','Cache-Control':'no-cache'})
 with urllib.request.urlopen(q,timeout=t) as r:return r.read()
def atomic(p,o):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+f'.tmp.{os.getpid()}');q.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');os.replace(q,p)
def valid_id(s):return bool(s) and len(s)<=100 and all(c.isalnum() or c in '._-' for c in s)
def commands():
 try:a=json.loads(req(LIST))
 except urllib.error.HTTPError as e:
  if e.code==404:return []
  raise
 out=[]
 for x in a if isinstance(a,list) else []:
  if x.get('type')!='file' or not x.get('name','').endswith('.json'):continue
  try:
   c=json.loads(req(x['download_url']));rid=str(c.get('request_id') or '')
   if c.get('schema')!='eira2_see_build_command_v3' or c.get('operation') not in ('see','deploy') or not valid_id(rid):continue
   out.append((rid,c))
  except Exception:pass
 return out
def execute(rid,c):
 done=STATE/'executed'/f'{rid}.json'
 if done.exists():return json.loads(done.read_text())
 # Engine V1 fetches only its legacy request URL. Mirror the isolated command locally into an engine-compatible direct execution instead of scanning legacy queues.
 op=c['operation']
 if op=='see':
  code='import importlib.util,json; p="'+str(ENGINE)+'";s=importlib.util.spec_from_file_location("sb",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);c=json.loads('+repr(json.dumps(c))+');print(json.dumps(m.see('+repr(rid)+',c)))'
  r=subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True,timeout=120)
 else:
  code='import importlib.util,json; p="'+str(ENGINE)+'";s=importlib.util.spec_from_file_location("sb",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);c=json.loads('+repr(json.dumps(c))+');print(json.dumps(m.build('+repr(rid)+',c)))'
  r=subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True,timeout=180)
 try:rec=json.loads((r.stdout or '').splitlines()[-1])
 except Exception:rec={'schema':'eira2_see_build_receipt_v3','request_id':rid,'operation':op,'ok':False,'returncode':r.returncode,'stdout_tail':(r.stdout or '')[-4000:],'stderr_tail':(r.stderr or '')[-3000:]}
 atomic(done,rec);return rec
def stage_return(rid,rec):
 # No clone, no push, no repository mutation from LIVE. Receipt is staged locally for the authenticated GitHub bridge to collect.
 p=STATE/'outbox'/f'{rid}.json';atomic(p,rec);return p
def main():
 STATE.mkdir(parents=True,exist_ok=True)
 while True:
  try:
   n=0
   for rid,c in commands():
    if not (STATE/'executed'/f'{rid}.json').exists():stage_return(rid,execute(rid,c));n+=1
   atomic(STATE/'heartbeat.json',{'ok':True,'pid':os.getpid(),'fresh_inbox':INBOX,'legacy_scan':False,'git_clone':False,'processed':n,'unix':time.time()})
  except KeyboardInterrupt:return 0
  except Exception as e:atomic(STATE/'heartbeat.json',{'ok':False,'pid':os.getpid(),'error':f'{type(e).__name__}:{e}','unix':time.time()})
  time.sleep(8)
if __name__=='__main__':raise SystemExit(main())
