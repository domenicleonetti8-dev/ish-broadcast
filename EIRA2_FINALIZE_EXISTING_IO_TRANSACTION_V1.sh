#!/usr/bin/env bash
set -euo pipefail

ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT" || exit 1

EXPECTED_LIVE_SHA="25b7ba54f61f74c46edc578f0315d5c311b6736238c17cc66142b0135573238f"
WATCHER_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/83e05ebc558f11be5cc39d0d16815c73b3939d4a/EIRA2_REPAIR_WATCHER_V4_FULL_REPLACEMENT.py"

LIVE_SHA="$(sha256sum eira2/live.py | awk '{print $1}')"
if [ "$LIVE_SHA" != "$EXPECTED_LIVE_SHA" ]; then
  echo "EIRA2_FINALIZE_IO=FAIL"
  echo "REASON=live_hash_not_expected"
  echo "LIVE_SHA256=$LIVE_SHA"
  exit 2
fi

python3 -m py_compile eira2/live.py

# Stop only the stale blueprint transport lane that is repeatedly replaying old packets.
pkill -f 'eira2_blueprint_transport_agent_v2.py.*--watch' 2>/dev/null || true
sleep 1

STAMP="$(date +%Y%m%d_%H%M%S)"
WATCHER="extensions/repair_watcher_ai/plugin.py"
MANIFEST="eira2-package-manifest.json"
WATCHER_BAK="${WATCHER}.retired_pre_finalize_${STAMP}"
MANIFEST_BAK="${MANIFEST}.retired_pre_finalize_${STAMP}"
cp -a "$WATCHER" "$WATCHER_BAK"
cp -a "$MANIFEST" "$MANIFEST_BAK"

rollback() {
  cp -a "$WATCHER_BAK" "$WATCHER" 2>/dev/null || true
  cp -a "$MANIFEST_BAK" "$MANIFEST" 2>/dev/null || true
  echo "EIRA2_FINALIZE_IO_ROLLBACK=PASS"
}
trap 'rollback' ERR

curl -fsSL "$WATCHER_URL" -o /tmp/eira2_repair_watcher_v4.py
python3 -m py_compile /tmp/eira2_repair_watcher_v4.py
install -m 0644 /tmp/eira2_repair_watcher_v4.py "$WATCHER"
python3 -m py_compile "$WATCHER"

grep -q 'VERSION = "2.4.0-eira2-superprobe-v4"' "$WATCHER"
grep -q 'SUPERPROBE_SCHEMA = "eira2_superprobe_forensic_v4"' "$WATCHER"

echo "EIRA2_WATCHER_V4=PASS"

python3 - <<'PY'
from pathlib import Path
import importlib, sys
root = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
mod = importlib.import_module('eira2.operations.package_identity')
manifest = root / 'eira2-package-manifest.json'
old = __import__('json').loads(manifest.read_text())
source_commit = str(old.get('source_commit_sha') or '').strip()
if not source_commit:
    raise RuntimeError('source_commit_sha_missing')
write_manifest = getattr(mod, 'write_package_manifest')
verify_manifest = getattr(mod, 'verify_package_manifest')
write_manifest(root, source_commit_sha=source_commit)
verified = verify_manifest(root)
print('PACKAGE_TREE_SHA256=' + str(verified.get('package_tree_sha256') or ''))
print('PACKAGE_FILE_COUNT=' + str(verified.get('file_count') or ''))
print('EIRA2_PACKAGE_IDENTITY=PASS')
PY

SP_OUT="$(python3 tools/eira2_superprobe_engine.py --root "$ROOT" --json 2>&1)"
printf '%s\n' "$SP_OUT" | tail -n 20
printf '%s\n' "$SP_OUT" | grep -q 'EIRA2_SUPERPROBE=PASS'

python3 - <<'PY'
import json
from pathlib import Path
root = Path('/media/domenicleonetti/easystore/EIRA/LIVE')
r = json.loads((root/'eira_probe/eira2_superprobe_report.json').read_text())
if r.get('ok') is not True:
    raise RuntimeError('superprobe_report_not_ok')
if (r.get('package_identity') or {}).get('ok') is not True:
    raise RuntimeError('package_identity_not_verified')
print('EIRA2_POST_SUPERPROBE=PASS')
PY

trap - ERR

echo "LIVE_SHA256=$LIVE_SHA"
echo "EIRA2_FINALIZE_EXISTING_IO_TRANSACTION=PASS"
