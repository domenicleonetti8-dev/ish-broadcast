#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
RAW='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast'
ALLOWED_USER_SERVICES={'eira-continuous-probe.service'}

def get(url, timeout=20):
    req=urllib.request.Request(url,headers={'User-Agent':'EIRA2-Orin-Direct-Bridge-V3','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
def sha(b): return hashlib.sha256(b).hexdigest()
def safe(v):
    p=Path(str(v or ''))
    if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts: raise RuntimeError('unsafe_path:'+str(v))
    return p.as_posix()
def atomic(p,b):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+'.tmp.'+str(os.getpid())); t.write_bytes(b); os.replace(t,p)
def deploy(rid, req):
    dep=req.get('deployment') or {}; src=dep.get('source') or {}; tgt=dep.get('target') or {}
    commit=str(src.get('commit') or ''); sp=safe(src.get('path')); tp=safe(tgt.get('path'))
    if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise RuntimeError('source_commit_invalid')
    payload=get(f'{RAW}/{commit}/{sp}'); expected=str(src.get('sha256') or '').lower()
    if expected and sha(payload)!=expected: raise RuntimeError('source_hash_mismatch')
    inbox=ROOT/'eira_probe/watcher_inbox_v8'; stage=inbox/'stage'; staged=Path(rid)/Path(tp).name
    atomic(stage/staged,payload)
    index={'files':[{'target_path':tp,'staged_path':staged.as_posix(),'sha256':sha(payload)}]}
    atomic(inbox/'file_index.json',(json.dumps(index,indent=2)+'\n').encode()); atomic(inbox/'surgery_package.json',(json.dumps({'package_fingerprint_sha256':sha(payload)},indent=2)+'\n').encode())
    code='import json; from extensions.repair_watcher_ai import plugin as w; r=w.inspect_once(); print(json.dumps(r)); raise SystemExit(0 if r.get("ok") else 2)'
    q=subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True,timeout=20)
    if q.returncode: raise RuntimeError('watcher_failed:'+(q.stderr or q.stdout)[-1200:])
    plan=ROOT/'eira_probe/eira2_builder_plan.json'; receipt=ROOT/'eira_probe/eira2_builder_receipt.json'
    q=subprocess.run([sys.executable,str(ROOT/'tools/eira2_builder_probe.py'),'--root',str(ROOT),'--plan',str(plan),'--receipt',str(receipt)],cwd=ROOT,text=True,capture_output=True,timeout=120)
    if q.returncode: raise RuntimeError('builder_failed:'+(q.stderr or q.stdout)[-1600:])
    out=json.loads(receipt.read_text()); out.update({'bridge':'EIRA2_ORIN_DIRECT_BRIDGE_V3','request_id':rid,'payload_sha256':sha(payload),'target_path':tp,'operation':'deploy'})
    return out
def restart_user_service(rid, req):
    svc=str(req.get('service') or '')
    if svc not in ALLOWED_USER_SERVICES: raise RuntimeError('service_not_allowed')
    before=subprocess.run(['systemctl','--user','show',svc,'--property=MainPID,ActiveState,SubState','--value'],text=True,capture_output=True,timeout=15)
    q=subprocess.run(['systemctl','--user','restart',svc],text=True,capture_output=True,timeout=20)
    if q.returncode: raise RuntimeError('service_restart_failed:'+(q.stderr or q.stdout)[-1200:])
    after=subprocess.run(['systemctl','--user','show',svc,'--property=MainPID,ActiveState,SubState','--value'],text=True,capture_output=True,timeout=15)
    return {'bridge':'EIRA2_ORIN_DIRECT_BRIDGE_V3','request_id':rid,'operation':'restart_user_service','service':svc,'before':before.stdout.strip(),'after':after.stdout.strip(),'ok':q.returncode==0}
def request(rid):
    req=json.loads(get(f'{RAW}/master/eira2_transport_bus/to_superprobe/requests/{rid}.json'))
    if req.get('request_id')!=rid: raise RuntimeError('request_invalid')
    op=str(req.get('operation') or '')
    if op=='deploy': out=deploy(rid,req)
    elif op=='restart_user_service': out=restart_user_service(rid,req)
    else: raise RuntimeError('operation_not_allowed')
    local=ROOT/'eira_probe/orin_direct_bridge_v3/receipts'/f'{rid}.json'; atomic(local,(json.dumps(out,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps(out,sort_keys=True)); return 0

def main():
    a=argparse.ArgumentParser(); a.add_argument('--request-id',required=True); x=a.parse_args(); return request(x.request_id)
if __name__=='__main__': raise SystemExit(main())
