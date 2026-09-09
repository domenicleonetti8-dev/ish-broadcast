#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
PLAN_SCHEMA='eira2_builder_plan_v3'

def sha(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()

def atomic_json(p:Path,v)->None:
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(t,p)

def safe_rel(v:str)->str:
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts: raise RuntimeError('unsafe_relative_path:'+str(v))
 if p.parts[0]=='.git': raise RuntimeError('git_metadata_write_blocked')
 return p.as_posix()

def compile_if_python(p:Path,target:str)->None:
 if target.endswith('.py'):
  q=subprocess.run([sys.executable,'-m','py_compile',str(p)],capture_output=True,text=True,timeout=90)
  if q.returncode: raise RuntimeError('python_compile_failed:'+target+':'+q.stderr[-1200:])

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--plan',required=True); ap.add_argument('--receipt',required=True); a=ap.parse_args()
 root=Path(a.root).resolve(); plan_path=Path(a.plan).resolve(); receipt=Path(a.receipt).resolve(); tx=f'{int(time.time())}-{os.getpid()}'; backups=root/'eira_probe'/'builder_backups_v3'/tx
 applied=[]; backup_rows=[]
 try:
  plan=json.loads(plan_path.read_text())
  if plan.get('schema')!=PLAN_SCHEMA: raise RuntimeError('builder_plan_schema_mismatch')
  if plan.get('authorized_by')!='repair_watcher_ai': raise RuntimeError('watcher_authorization_missing')
  stage=Path(str(plan.get('offsystem_stage_root') or '')).resolve()
  if not stage.is_dir(): raise RuntimeError('stage_root_missing')
  rows=plan.get('files') or []
  if not rows: raise RuntimeError('files_missing')
  verified=[]
  for row in rows:
   rel=safe_rel(str(row.get('staged_path') or '')); target_rel=safe_rel(str(row.get('target_path') or '')); expected=str(row.get('sha256') or '').lower(); src=(stage/rel).resolve(); src.relative_to(stage)
   if not src.is_file(): raise RuntimeError('staged_missing:'+rel)
   actual=sha(src)
   if expected and actual!=expected: raise RuntimeError('staged_hash_mismatch:'+rel)
   compile_if_python(src,target_rel)
   target=(root/target_rel).resolve(); target.relative_to(root)
   verified.append((src,target,target_rel,actual))
  for src,target,target_rel,actual in verified:
   backup=backups/target_rel; backup.parent.mkdir(parents=True,exist_ok=True)
   existed=target.is_file()
   if existed: shutil.copy2(target,backup)
   backup_rows.append((target,backup,existed))
  for src,target,target_rel,actual in verified:
   target.parent.mkdir(parents=True,exist_ok=True); tmp=target.with_name(target.name+f'.eira2tmp.{os.getpid()}'); shutil.copy2(src,tmp); os.replace(tmp,target)
   if sha(target)!=actual: raise RuntimeError('post_write_hash_mismatch:'+target_rel)
   applied.append(target_rel)
  payload={'schema':'eira2_builder_receipt_v3','ok':True,'transaction_id':tx,'authorized_by':'repair_watcher_ai','applied':applied,'rollback_performed':False,'completed_unix':time.time()}; atomic_json(receipt,payload); print('EIRA2_BUILDER_PROBE=PASS'); print(json.dumps(payload)); return 0
 except Exception as e:
  rolled=False
  for target,backup,existed in reversed(backup_rows):
   try:
    if existed and backup.is_file(): target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(backup,target); rolled=True
    elif not existed and target.exists(): target.unlink(); rolled=True
   except Exception: pass
  payload={'schema':'eira2_builder_receipt_v3','ok':False,'transaction_id':tx,'applied':applied,'rollback_performed':rolled,'error':f'{type(e).__name__}:{e}','completed_unix':time.time()}; atomic_json(receipt,payload); print('EIRA2_BUILDER_PROBE=FAIL',file=sys.stderr); print(json.dumps(payload),file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
