#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
MAN=ROOT/'eira2-package-manifest.json'
EXPECTED_SOURCE='d45797f72f11723593e0d7f2b9cde971cf1208d6'
EXPECTED_TREE='7dad45fbf0578a7cd8ef051de613bbf658bc65bf1c5908bfba65d5a22a64cdee'
EXPECTED_CHANGED={
 'eira2/operations/doctor.py':('0932c00b6e8bf99e085bf2ece878db23a1fbc569a0db789345061afa98f317db',13284,'43ea7281ebb242b6a799849de077a4e18e495dc5c61e06c630f4b8ce685e68e9',15186),
 'extensions/repair_watcher_ai/plugin.py':('65fcc14c34ec8fcdf394cd702b3cd1a13ae46f51e7698af69a2437b5ae9c6d17',11845,'9a754d434ca3c1ce638a4810ddfd756159a30b77992050b9e7893ed5f6c962ec',12786),
}
sys.path.insert(0,str(ROOT))
from eira2.operations.package_identity import build_package_manifest,verify_package_manifest

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def main()->int:
 old=json.loads(MAN.read_text())
 if old.get('source_commit_sha')!=EXPECTED_SOURCE: raise RuntimeError('source_commit_mismatch')
 old_rows={r['path']:r for r in old['files']}
 new=build_package_manifest(ROOT,source_commit_sha=EXPECTED_SOURCE)
 if new.get('package_tree_sha256')!=EXPECTED_TREE: raise RuntimeError('tree_hash_mismatch:'+str(new.get('package_tree_sha256')))
 new_rows={r['path']:r for r in new['files']}
 changed=[]
 for k in sorted(set(old_rows)|set(new_rows)):
  if old_rows.get(k)!=new_rows.get(k): changed.append(k)
 if set(changed)!=set(EXPECTED_CHANGED): raise RuntimeError('unexpected_manifest_delta:'+json.dumps(changed))
 for path,(bsha,bsize,asha,asize) in EXPECTED_CHANGED.items():
  b=old_rows[path]; a=new_rows[path]
  if b.get('sha256')!=bsha or b.get('size')!=bsize: raise RuntimeError('before_mismatch:'+path)
  if a.get('sha256')!=asha or a.get('size')!=asize: raise RuntimeError('after_mismatch:'+path)
 before=sha(MAN)
 tmp=MAN.with_name(MAN.name+'.reseal_v1.tmp')
 tmp.write_text(json.dumps(new,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 tmp.replace(MAN)
 verified=verify_package_manifest(ROOT,MAN,expected_source_commit_sha=EXPECTED_SOURCE,expected_tree_sha256=EXPECTED_TREE)
 out={'schema':'eira2_package_reseal_recovery_v1','ok':True,'manifest_before_sha256':before,'manifest_after_sha256':sha(MAN),'package_tree_sha256':verified['package_tree_sha256'],'file_count':verified['file_count'],'changed':changed,'mutated_only':'eira2-package-manifest.json'}
 print(json.dumps(out,separators=(',',':'))); return 0
if __name__=='__main__': raise SystemExit(main())
