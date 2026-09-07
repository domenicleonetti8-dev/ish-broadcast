#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
cd "$ROOT"
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="$ROOT/eira_probe/current_io_state/$STAMP"
mkdir -p "$OUT"
python3 - <<'PY' "$ROOT" "$OUT"
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()
def readj(p):
 try:
  v=json.loads(p.read_text()); return v if isinstance(v,dict) else {'_value':v}
 except Exception as e: return {'_missing_or_invalid':f'{type(e).__name__}:{e}'}
files={
 'live.py':root/'eira2/live.py',
 'watcher.py':root/'extensions/repair_watcher_ai/plugin.py',
 'transaction_receipt.json':root/'eira_probe/eira2_transaction_receipt.json',
 'builder_receipt.json':root/'eira_probe/eira2_builder_receipt.json',
 'builder_plan.json':root/'eira_probe/eira2_builder_plan.json',
 'package_manifest.json':root/'eira2-package-manifest.json',
 'superprobe_report.json':root/'eira_probe/eira2_superprobe_report.json',
}
state={'schema':'eira2_current_io_transaction_state_v2','root':str(root),'files':{}}
for name,p in files.items():
 row={'path':str(p),'exists':p.is_file()}
 if p.is_file():
  row['sha256']=sha(p); row['bytes']=p.stat().st_size
  if p.suffix=='.json': row['json']=readj(p)
 state['files'][name]=row
(out/'state.json').write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')
for name in ('live.py','watcher.py'):
 p=files[name]
 if p.is_file(): (out/name).write_bytes(p.read_bytes())
for name in ('transaction_receipt.json','builder_receipt.json','builder_plan.json','package_manifest.json','superprobe_report.json'):
 p=files[name]
 if p.is_file(): (out/name).write_bytes(p.read_bytes())
print('LIVE_SHA256='+state['files']['live.py'].get('sha256','MISSING'))
print('WATCHER_SHA256='+state['files']['watcher.py'].get('sha256','MISSING'))
PY
TMP=$(mktemp -d /tmp/eira2-state-publish.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
git clone -q https://github.com/domenicleonetti8-dev/ish-broadcast.git "$TMP/repo"
DEST="eira2_transport_bus/from_superprobe/current_io_state/$STAMP"
mkdir -p "$TMP/repo/$DEST"
cp -a "$OUT/." "$TMP/repo/$DEST/"
cd "$TMP/repo"
git add "$DEST"
git -c user.name='EIRA2 Transport' -c user.email='eira2@local' commit -qm "Publish current IO transaction state $STAMP"
for n in 1 2 3 4 5; do
  if git push -q origin HEAD:master; then
    echo EIRA2_CURRENT_IO_STATE_EXPORT=PASS
    echo GITHUB_PATH="$DEST"
    exit 0
  fi
  git fetch -q origin master
  git rebase -q origin/master
  sleep 1
done
echo EIRA2_CURRENT_IO_STATE_EXPORT=FAIL >&2
exit 2
