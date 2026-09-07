#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, py_compile, tempfile
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
p=ROOT/'eira2/operations/doctor.py'
expected='d5d7807c22a35449a11f9913ea7c8f9f2db9d320eec7074c3fba9b828f21f542'
desired='43ea7281ebb242b6a799849de077a4e18e495dc5c61e06c630f4b8ce685e68e9'
old='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var"}'
new='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var", "eira_probe"}'
raw=p.read_bytes(); before=hashlib.sha256(raw).hexdigest()
if before==desired:
 print(json.dumps({'ok':True,'already_applied':True,'before_sha256':before,'after_sha256':before,'target':str(p)},sort_keys=True)); raise SystemExit(0)
if before!=expected: raise SystemExit('doctor_unexpected_before_sha256:'+before)
text=raw.decode('utf-8')
if text.count(old)!=1: raise SystemExit('doctor_boundary_anchor_mismatch')
replacement=text.replace(old,new).encode('utf-8')
if hashlib.sha256(replacement).hexdigest()!=desired: raise SystemExit('doctor_replacement_sha256_mismatch')
compile(replacement.decode('utf-8'),str(p),'exec')
fd,tmp=tempfile.mkstemp(prefix='doctor.py.',dir=str(p.parent)); os.close(fd)
Path(tmp).write_bytes(replacement); py_compile.compile(tmp,doraise=True); os.replace(tmp,p)
after=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'ok':after==desired,'already_applied':False,'before_sha256':before,'after_sha256':after,'target':str(p),'boundary':'exclude_eira_probe_from_doctor_scan'},sort_keys=True))
if after!=desired: raise SystemExit(2)
