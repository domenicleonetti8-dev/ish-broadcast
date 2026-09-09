#!/usr/bin/env python3
from __future__ import annotations
import hashlib,importlib.util,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
BASE='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/orin-bridge-forensic-only/'
FILES=[
 ('EIRA2_REPAIR_WATCHER_V6_FULL.py','extensions/repair_watcher_ai/plugin.py'),
 ('EIRA2_BUILDER_PROBE_V3_FULL.py','tools/eira2_builder_probe.py'),
 ('EIRA2_ORIN_FULL_DUPLEX_BRIDGE_V1.py','tools/eira2_orin_full_duplex_bridge.py'),
]
def sha(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()
def fetch(name:str)->bytes:
 with urllib.request.urlopen(BASE+name,timeout=60) as r: return r.read()
def atomic(p:Path,data:bytes)->None:
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_bytes(data); os.replace(t,p)
def load(path:Path,name:str):
 s=importlib.util.spec_from_file_location(name,path)
 if s is None or s.loader is None: raise RuntimeError('import_failed:'+str(path))
 m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def main()->int:
 if not ROOT.is_dir(): raise SystemExit('EIRA_ROOT_MISSING')
 tx=time.strftime('%Y%m%d_%H%M%S'); backup=ROOT/'eira_probe'/'control_plane_backups'/tx; backup.mkdir(parents=True,exist_ok=False)
 staged=ROOT/'eira_probe'/'control_plane_stage'/tx; staged.mkdir(parents=True,exist_ok=False)
 records=[]
 try:
  for remote,target_rel in FILES:
   data=fetch(remote); sp=staged/remote; sp.write_bytes(data)
   q=subprocess.run([sys.executable,'-m','py_compile',str(sp)],capture_output=True,text=True,timeout=90)
   if q.returncode: raise RuntimeError('compile_failed:'+remote+':'+q.stderr[-1200:])
   target=(ROOT/target_rel).resolve(); target.relative_to(ROOT); bp=backup/target_rel; bp.parent.mkdir(parents=True,exist_ok=True); existed=target.is_file()
   if existed: shutil.copy2(target,bp)
   records.append((sp,target,bp,existed,target_rel))
  for sp,target,bp,existed,target_rel in records: atomic(target,sp.read_bytes())
  watcher=load(ROOT/'extensions/repair_watcher_ai/plugin.py','eira2_watcher_v6_smoke'); idle=watcher.inspect_once()
  if not isinstance(idle,dict) or idle.get('ok') is not True: raise RuntimeError('watcher_smoke_failed:'+json.dumps(idle)[-1200:])
  for p in (ROOT/'tools/eira2_builder_probe.py',ROOT/'tools/eira2_orin_full_duplex_bridge.py'):
   q=subprocess.run([sys.executable,str(p),'--help'],capture_output=True,text=True,timeout=30)
   if q.returncode: raise RuntimeError('cli_smoke_failed:'+str(p)+':'+q.stderr[-1000:])
  receipt={'schema':'eira2_control_plane_install_v1','ok':True,'transaction':tx,'backup_root':str(backup),'installed':[{'path':r[4],'sha256':sha(r[1])} for r in records],'watcher_version':getattr(watcher,'VERSION',None),'completed_unix':time.time()}
  out=ROOT/'eira_probe'/'control_plane_install_receipt.json'; out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n'); print(json.dumps(receipt,indent=2)); print('EIRA2_CONTROL_PLANE_INSTALL=PASS'); return 0
 except Exception as e:
  rolled=[]
  for sp,target,bp,existed,target_rel in reversed(records):
   try:
    if existed and bp.is_file(): target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(bp,target); rolled.append(target_rel)
    elif not existed and target.exists(): target.unlink(); rolled.append(target_rel)
   except Exception: pass
  receipt={'schema':'eira2_control_plane_install_v1','ok':False,'transaction':tx,'backup_root':str(backup),'rollback_performed':True,'rolled_back':rolled,'error':f'{type(e).__name__}:{e}','completed_unix':time.time()}; out=ROOT/'eira_probe'/'control_plane_install_receipt.json'; out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n'); print(json.dumps(receipt,indent=2),file=sys.stderr); print('EIRA2_CONTROL_PLANE_INSTALL=FAIL',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
