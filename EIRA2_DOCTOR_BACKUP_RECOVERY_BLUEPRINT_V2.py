#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
backup_root=ROOT/'eira_probe/builder_backups/20260907T190906'
expected='d5d7807c22a35449a11f9913ea7c8f9f2db9d320eec7074c3fba9b828f21f542'
desired='43ea7281ebb242b6a799849de077a4e18e495dc5c61e06c630f4b8ce685e68e9'
old='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var"}'
new='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var", "eira_probe"}'
candidates=[p for p in backup_root.rglob('*') if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected]
if len(candidates)!=1: raise SystemExit('doctor_backup_exact_match_count:'+str(len(candidates)))
raw=candidates[0].read_text(encoding='utf-8')
if raw.count(old)!=1: raise SystemExit('doctor_backup_boundary_anchor_mismatch')
rep=raw.replace(old,new); compile(rep,'eira2/operations/doctor.py','exec')
actual=hashlib.sha256(rep.encode()).hexdigest()
if actual!=desired: raise SystemExit('doctor_recovered_sha_mismatch:'+actual)
out={'schema':'eira2_doctor_backup_recovery_blueprint_v2','ok':True,'mutates_live':False,'backup_path':str(candidates[0]),'before_sha256':expected,'after_sha256':actual,'bytes':len(rep.encode()),'payload':rep}
print(json.dumps(out,sort_keys=True))
