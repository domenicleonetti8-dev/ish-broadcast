#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
TARGET="$ROOT/eira2/operations/doctor.py"
BACKUP="$ROOT/eira_probe/builder_backups/20260907T190906/eira2/operations/doctor.py"
EXPECTED_BACKUP=d5d7807c22a35449a11f9913ea7c8f9f2db9d320eec7074c3fba9b828f21f542
EXPECTED_FIXED=43ea7281ebb242b6a799849de077a4e18e495dc5c61e06c630f4b8ce685e68e9

python3 - "$BACKUP" "$TARGET" "$EXPECTED_BACKUP" "$EXPECTED_FIXED" <<'PY'
from pathlib import Path
import hashlib, os, py_compile, sys, tempfile
backup=Path(sys.argv[1]); target=Path(sys.argv[2]); expected_old=sys.argv[3]; expected_new=sys.argv[4]
raw=backup.read_bytes()
old=hashlib.sha256(raw).hexdigest()
if old != expected_old:
    raise SystemExit(f'BACKUP_HASH_MISMATCH={old}')
text=raw.decode('utf-8')
anchor='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var"}'
replacement='_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var", "eira_probe"}'
if text.count(anchor) != 1:
    raise SystemExit('BOUNDARY_ANCHOR_MISMATCH')
fixed=text.replace(anchor,replacement)
blob=fixed.encode('utf-8')
new=hashlib.sha256(blob).hexdigest()
if new != expected_new:
    raise SystemExit(f'FIXED_HASH_MISMATCH={new}')
compile(fixed,str(target),'exec')
fd,tmp=tempfile.mkstemp(prefix='doctor.py.recover.',dir=str(target.parent)); os.close(fd)
Path(tmp).write_bytes(blob)
py_compile.compile(tmp,doraise=True)
os.replace(tmp,target)
after=hashlib.sha256(target.read_bytes()).hexdigest()
if after != expected_new:
    raise SystemExit(f'POSTWRITE_HASH_MISMATCH={after}')
print('EIRA2_DOCTOR_RECOVERY=PASS')
print('BEFORE_BACKUP_SHA256='+old)
print('AFTER_SHA256='+after)
print('TARGET='+str(target))
PY
