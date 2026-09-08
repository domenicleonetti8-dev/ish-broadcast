#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
MAN=ROOT/'eira2-package-manifest.json'
EXCLUDED={'.git','var','__pycache__','.pytest_cache','.mypy_cache','build','dist','eira_probe'}
EX_SUFFIX={'.pyc','.pyo'}

def included(rel:Path):
    if rel.name=='eira2-package-manifest.json': return False
    if any(p in EXCLUDED for p in rel.parts): return False
    if rel.suffix.casefold() in EX_SUFFIX: return False
    return True

def canon(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def main():
    old=json.loads(MAN.read_text())
    old_rows={r['path']:r for r in old['files']}
    new=[]
    for p in sorted(ROOT.rglob('*'),key=lambda x:x.as_posix()):
        rel=p.relative_to(ROOT)
        if not included(rel) or not p.is_file() or p.is_symlink(): continue
        data=p.read_bytes(); new.append({'path':rel.as_posix(),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    new_rows={r['path']:r for r in new}
    changed=[]
    for k in sorted(set(old_rows)|set(new_rows)):
        if old_rows.get(k)!=new_rows.get(k): changed.append({'path':k,'before':old_rows.get(k),'after':new_rows.get(k)})
    out={'schema':'eira2_package_manifest_delta_v1','ok':True,'mutates_live':False,'old_file_count':len(old_rows),'new_file_count':len(new_rows),'changed_count':len(changed),'changed':changed,'source_commit_sha':old.get('source_commit_sha'),'new_package_tree_sha256':hashlib.sha256(canon(new)).hexdigest()}
    print(json.dumps(out,separators=(',',':')))
    return 0
if __name__=='__main__': raise SystemExit(main())
