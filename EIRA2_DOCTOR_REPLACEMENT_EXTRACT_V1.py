#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
p=ROOT/'eira2/operations/doctor.py'
raw=p.read_text(encoding='utf-8')
old='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var"}'
new='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var", "eira_probe"}'
if raw.count(old)!=1: raise SystemExit('doctor_boundary_anchor_mismatch')
rep=raw.replace(old,new)
compile(rep,str(p),'exec')
blob=rep.encode()
chunks={f'chunk_{i:03d}':blob[i:i+2400].decode('utf-8') for i in range(0,len(blob),2400)}
out={'schema':'eira2_doctor_replacement_extract_v1','ok':True,'mutates_live':False,'before_sha256':hashlib.sha256(raw.encode()).hexdigest(),'after_sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'chunks':chunks}
print(json.dumps(out,sort_keys=True))
