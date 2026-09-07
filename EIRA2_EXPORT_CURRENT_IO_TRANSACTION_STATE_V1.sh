#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
cd "$ROOT"
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="/tmp/eira2_current_io_state_$STAMP"
mkdir -p "$OUT"
python3 - <<'PY' "$OUT"
import hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]); root=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()
def readj(p):
 try:
  v=json.loads(p.read_text()); return v if isinstance(v,dict) else {}
 except Exception:return {}
live=root/'eira2/live.py'; watcher=root/'extensions/repair_watcher_ai/plugin.py'
wtxt=watcher.read_text(errors='replace') if watcher.is_file() else ''
m=re.search(r'^VERSION\s*=\s*["\']([^"\']+)',wtxt,re.M)
state={
 'schema':'eira2_current_io_transaction_state_v1',
 'live_py':{'exists':live.is_file(),'sha256':sha(live) if live.is_file() else None,'bytes':live.stat().st_size if live.is_file() else None,'has_post_bridge':'def _install_conversation_post_bridge' in (live.read_text(errors='replace') if live.is_file() else ''),'has_terminal_turn':'async def terminal_turn' in (live.read_text(errors='replace') if live.is_file() else '')},
 'watcher':{'exists':watcher.is_file(),'sha256':sha(watcher) if watcher.is_file() else None,'version':m.group(1) if m else None,'uses_superprobe_engine':'eira2_superprobe_engine.py' in wtxt,'expects_v4':'eira2_superprobe_forensic_v4' in wtxt},
 'transaction_receipt':readj(root/'eira_probe/eira2_transaction_receipt.json'),
 'builder_receipt':readj(root/'eira_probe/eira2_builder_receipt.json'),
 'package_manifest':readj(root/'eira2-package-manifest.json'),
 'superprobe_report':readj(root/'eira_probe/eira2_superprobe_report.json'),
}
(out/'state.json').write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')
PY
REPO_URL="https://github.com/domenicleonetti8-dev/ish-broadcast.git"
TMP=$(mktemp -d)
git clone -q "$REPO_URL" "$TMP/repo"
DEST="eira2_transport_bus/from_superprobe/io_transaction_state/$STAMP"
mkdir -p "$TMP/repo/$DEST"
cp "$OUT/state.json" "$TMP/repo/$DEST/state.json"
cd "$TMP/repo"
git config user.email "eira2-transport@local"
git config user.name "EIRA2 Transport"
git add "$DEST/state.json"
git commit -q -m "Publish current EIRA2 IO transaction state $STAMP"
git push -q origin HEAD:master
printf 'EIRA2_CURRENT_IO_STATE_EXPORT=PASS\nGITHUB_PATH=%s\n' "$DEST"
