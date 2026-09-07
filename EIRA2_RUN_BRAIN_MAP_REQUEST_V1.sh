#!/usr/bin/env bash
set -euo pipefail

ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"

REQ_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/eira2_transport_bus/to_superprobe/map_request.md"
MAP_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/88bf511997b6788618d262f6c23b1c12ed5e7e88/EIRA2_FULL_BRAIN_RECONSTRUCTOR_V1.py"
REQ="eira_probe/transport_inbox/map_request.md"
ENGINE="eira_probe/transport_runtime/EIRA2_FULL_BRAIN_RECONSTRUCTOR_V1.py"

mkdir -p "$(dirname "$REQ")" "$(dirname "$ENGINE")"
curl -fsSL "$REQ_URL" -o "$REQ"
curl -fsSL "$MAP_URL" -o "$ENGINE"
python3 -m py_compile "$ENGINE"

python3 "$ENGINE" --root "$ROOT" --request "$ROOT/$REQ"

LATEST="$(find eira_probe/full_brain_reconstruction -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
RETURN="eira_probe/transport_outbox/from_superprobe/$(basename "$LATEST")"
mkdir -p "$RETURN"
cp -a "$LATEST"/. "$RETURN"/

python3 - <<PY
from pathlib import Path
import hashlib, json
p=Path("$RETURN")
rows=[]
for f in sorted(x for x in p.rglob('*') if x.is_file()):
    b=f.read_bytes()
    rows.append({'path':f.relative_to(p).as_posix(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
receipt={'schema':'eira2_transport_return_bundle_v1','direction':'from_superprobe','file_count':len(rows),'files':rows,'return_path':str(p.resolve())}
(p/'transport_return_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps({'EIRA2_GITHUB_BRIDGE_REQUEST':'CONSUMED','RETURN_STAGED':str(p.resolve()),'files':len(rows)},indent=2))
PY
