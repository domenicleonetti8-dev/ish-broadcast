#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
TARGET=ROOT/'eira2/neural/live.py'
EXPECTED='2e54b6a05e5ab231e7b9d69f7f304e25e4a12a72f8e1c02a4b957438d2bc6bb5'
OLD='''        self.root = root\n        self._inventory = detected_inventory\n        initial = NeuralAtlas(root, inventory=self._inventory).build()\n        overlay_live_filesystem(initial, root)\n'''
NEW='''        self.root = root\n        self._inventory = detected_inventory\n        # The baseline build already used the canonical explicit/discovered inventory.\n        # Reuse it as the initial immutable topology instead of rebuilding the same atlas.\n        initial = baseline\n        overlay_live_filesystem(initial, root)\n'''
raw=TARGET.read_bytes(); before=hashlib.sha256(raw).hexdigest(); text=raw.decode('utf-8')
out={'schema':'eira2_neural_live_single_build_generator_v1','mutates_live':False,'before_sha256':before,'anchor_count':text.count(OLD)}
if before!=EXPECTED:
    out.update(ok=False,error='before_sha_mismatch'); print(json.dumps(out,separators=(',',':'))); raise SystemExit(1)
if text.count(OLD)!=1:
    out.update(ok=False,error='anchor_count_invalid'); print(json.dumps(out,separators=(',',':'))); raise SystemExit(1)
replacement=text.replace(OLD,NEW,1)
compile(replacement,str(TARGET),'exec')
new_raw=replacement.encode('utf-8'); out.update(ok=True,after_sha256=hashlib.sha256(new_raw).hexdigest(),bytes=len(new_raw),replacement_source=replacement)
print(json.dumps(out,separators=(',',':')))
