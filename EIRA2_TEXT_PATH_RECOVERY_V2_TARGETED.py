#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,py_compile,shutil,sys,time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MANIFEST=ROOT/'eira2-package-manifest.json'
STATE=ROOT/'eira_probe'/'text_path_recovery_v2'
RECEIPT=STATE/'receipt.json'
TARGET='eira2/evidence/universe_public_library.py'

def sha256(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()

def write_json(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix('.tmp'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)

def main():
 print('TEXT_RECOVERY_V2=START',flush=True)
 before=json.loads(MANIFEST.read_text())
 rows=before.get('files') or before.get('file_rows') or before.get('entries') or []
 row=next((r for r in rows if (r.get('path') or r.get('relative_path'))==TARGET),None)
 if row is None: raise RuntimeError('target_not_in_manifest')
 p=ROOT/TARGET
 if not p.is_file(): raise RuntimeError('target_missing')
 actual_size=p.stat().st_size; actual_sha=sha256(p)
 expected_size=row.get('bytes',row.get('size')); expected_sha=row.get('sha256') or row.get('sha')
 print(f'TARGET={TARGET}',flush=True)
 print(f'EXPECTED_BYTES={expected_size} ACTUAL_BYTES={actual_size}',flush=True)
 print(f'EXPECTED_SHA={expected_sha}',flush=True)
 print(f'ACTUAL_SHA={actual_sha}',flush=True)
 py_compile.compile(str(p),doraise=True)
 print('TARGET_COMPILE=PASS',flush=True)
 STATE.mkdir(parents=True,exist_ok=True)
 backup=STATE/f'eira2-package-manifest.before.{int(time.time())}.json'
 shutil.copy2(MANIFEST,backup)
 print(f'MANIFEST_BACKUP={backup.relative_to(ROOT)}',flush=True)
 sys.path.insert(0,str(ROOT))
 from eira2.operations.package_identity import write_package_manifest,verify_package_manifest
 import inspect
 sig=inspect.signature(write_package_manifest); kwargs={}
 for n in sig.parameters:
  if n in ('root','package_root'): kwargs[n]=ROOT
  elif n in ('manifest','manifest_path','path'): kwargs[n]=MANIFEST
  elif n in ('source_commit_sha','source_commit','commit_sha'): kwargs[n]=before.get('source_commit_sha') or before.get('source_commit') or ''
 write_package_manifest(**kwargs)
 print('MANIFEST_RESEALED=PASS',flush=True)
 verified=verify_package_manifest(ROOT,MANIFEST)
 print('PACKAGE_VERIFY=PASS',flush=True)
 after=json.loads(MANIFEST.read_text())
 receipt={'schema':'eira2_text_path_recovery_v2','ok':True,'target':TARGET,'target_sha256':actual_sha,'target_bytes':actual_size,'manifest_sha256':sha256(MANIFEST),'file_count':after.get('file_count'),'package_tree_sha256':after.get('package_tree_sha256'),'backup':str(backup.relative_to(ROOT)),'verify_type':type(verified).__name__}
 write_json(RECEIPT,receipt)
 print(json.dumps(receipt,sort_keys=True),flush=True)
 return 0
if __name__=='__main__': raise SystemExit(main())
