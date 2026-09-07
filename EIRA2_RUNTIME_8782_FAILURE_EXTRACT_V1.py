#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
probe=ROOT/'eira_probe'
receipt=probe/'runtime_8782_recovery_v2.json'
log=probe/'canonical_live_recovery_v2.log'
out={'schema':'eira2_runtime_8782_failure_extract_v1','ok':True,'mutates_live':False,'recovery_receipt':None,'log_tail':''}
try:
    if receipt.is_file(): out['recovery_receipt']=json.loads(receipt.read_text())
except Exception as exc:
    out['receipt_error']=f'{type(exc).__name__}:{exc}'
try:
    if log.is_file(): out['log_tail']=log.read_text(errors='replace')[-20000:]
except Exception as exc:
    out['log_error']=f'{type(exc).__name__}:{exc}'
print(json.dumps(out,sort_keys=True))
