#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
p=ROOT/'eira2/operations/doctor.py'
expected='43ea7281ebb242b6a799849de077a4e18e495dc5c61e06c630f4b8ce685e68e9'
raw=p.read_bytes(); actual=hashlib.sha256(raw).hexdigest(); text=raw.decode('utf-8')
checks={
 'sha_match': actual==expected,
 'boundary_marker': '_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var", "eira_probe"}' in text,
 'doctor_service_present': 'class DoctorService:' in text,
 'audit_project_present': 'def audit_project(' in text,
 'wrapper_absent': 'EIRA2_DOCTOR_BOUNDARY_REPLACEMENT_V1' not in text and 'doctor_unexpected_before_sha256' not in text,
}
try:
 compile(text,str(p),'exec'); checks['syntax_ok']=True
except Exception as exc:
 checks['syntax_ok']=False; checks['syntax_error']=f'{type(exc).__name__}:{exc}'
ok=all(v is True for k,v in checks.items() if k!='syntax_error')
print(json.dumps({'schema':'eira2_verify_doctor_recovery_v1','ok':ok,'mutates_live':False,'sha256':actual,'checks':checks},sort_keys=True))
raise SystemExit(0 if ok else 2)
