#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
RAW='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast'
STATE=ROOT/'eira_probe/see_build_v1'

def get(u,t=20):
 with urllib.request.urlopen(u,timeout=t) as r:return r.read()
def sha(b):return hashlib.sha256(b).hexdigest()
def safe(v):
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts:raise RuntimeError('unsafe_path')
 return p.as_posix()
def atomic(p,b):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+'.tmp.'+str(os.getpid()));q.write_bytes(b);os.replace(q,p)
def run(a,t=120):return subprocess.run(a,cwd=ROOT,text=True,capture_output=True,timeout=t)
def see(rid,req):
 s=req.get('see') or {}; paths=s.get('paths') or ['main.py','extensions/repair_watcher_ai/plugin.py','tools/eira2_builder_probe.py']; maxb=min(int(s.get('max_bytes',200000)),1000000); items=[]
 for x in paths[:100]:
  rel=safe(x);p=ROOT/rel
  if not p.exists():items.append({'path':rel,'exists':False});continue
  if p.is_dir():
   names=[]
   for q in sorted(p.rglob('*')):
    if q.is_file() and '.git' not in q.parts:names.append(str(q.relative_to(ROOT)))
    if len(names)>=500:break
   items.append({'path':rel,'exists':True,'type':'dir','files':names});continue
  b=p.read_bytes()[:maxb];items.append({'path':rel,'exists':True,'type':'file','bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'text':b.decode('utf-8','replace')})
 ps=run(['ps','-eo','pid,comm,args'],15)
 return {'schema':'eira2_see_build_receipt_v1','request_id':rid,'operation':'see','ok':True,'unix':time.time(),'items':items,'processes':ps.stdout.splitlines()[:120]}
def build(rid,req):
 dep=req.get('deployment') or {};src=dep.get('source') or {};tgt=dep.get('target') or {};commit=str(src.get('commit') or '');sp=safe(src.get('path'));tp=safe(tgt.get('path'))
 if len(commit)!=40:raise RuntimeError('source_commit_invalid')
 payload=get(f'{RAW}/{commit}/{sp}');expected=str(src.get('sha256') or '').lower()
 if expected and sha(payload)!=expected:raise RuntimeError('source_hash_mismatch')
 inbox=ROOT/'eira_probe/watcher_inbox_v8';staged=Path(rid)/Path(tp).name;atomic(inbox/'stage'/staged,payload)
 atomic(inbox/'file_index.json',(json.dumps({'files':[{'target_path':tp,'staged_path':staged.as_posix(),'sha256':sha(payload)}]},indent=2)+'\n').encode());atomic(inbox/'surgery_package.json',(json.dumps({'package_fingerprint_sha256':sha(payload)},indent=2)+'\n').encode())
 code='import json;from extensions.repair_watcher_ai import plugin as w;r=w.inspect_once();print(json.dumps(r));raise SystemExit(0 if r.get("ok") else 2)';q=run([sys.executable,'-c',code],20)
 if q.returncode:raise RuntimeError('watcher_failed:'+(q.stderr or q.stdout)[-1000:])
 plan=ROOT/'eira_probe/eira2_builder_plan.json';receipt=STATE/f'{rid}.builder.json';q=run([sys.executable,str(ROOT/'tools/eira2_builder_probe.py'),'--root',str(ROOT),'--plan',str(plan),'--receipt',str(receipt)],120)
 if q.returncode:raise RuntimeError('builder_failed:'+(q.stderr or q.stdout)[-1200:])
 out=json.loads(receipt.read_text());out.update({'schema':'eira2_see_build_receipt_v1','request_id':rid,'operation':'build','target_path':tp});return out
def main():
 a=argparse.ArgumentParser();a.add_argument('--request-id',required=True);x=a.parse_args();rid=x.request_id;req=json.loads(get(f'{RAW}/master/eira2_transport_bus/to_superprobe/requests/{rid}.json'));op=req.get('operation')
 try:r=see(rid,req) if op=='see' else build(rid,req) if op=='deploy' else (_ for _ in ()).throw(RuntimeError('unsupported_operation'))
 except Exception as e:r={'schema':'eira2_see_build_receipt_v1','request_id':rid,'operation':op,'ok':False,'error':f'{type(e).__name__}:{e}','unix':time.time()}
 atomic(STATE/'receipts'/f'{rid}.json',(json.dumps(r,indent=2,sort_keys=True)+'\n').encode());print(json.dumps(r,sort_keys=True));return 0 if r.get('ok') else 2
if __name__=='__main__':raise SystemExit(main())
