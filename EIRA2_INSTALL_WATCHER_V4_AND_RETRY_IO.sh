#!/usr/bin/env bash
set -euo pipefail

ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"

TARGET="extensions/repair_watcher_ai/plugin.py"
MANIFEST="eira2-package-manifest.json"
EXPECTED_OLD="57f945f90764d0d3772daf0289e6b06963076e0900c0914a1c84bb889e518a36"
SRC_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/83e05ebc558f11be5cc39d0d16815c73b3939d4a/EIRA2_REPAIR_WATCHER_V4_FULL_REPLACEMENT.py"
LANE_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/62e6f53d5e443f0a8acaff0a2fdcfe5855d72003/EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
PACKET_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/69c34cc15de0fa6aa666bb29477fbc6b36d3b028/eira2_transport_bus/to_superprobe/blueprints/eira2_live_io_path_v3.json"

[ -f "$TARGET" ] || { echo "WATCHER_TARGET_MISSING"; exit 2; }
[ -f "$MANIFEST" ] || { echo "PACKAGE_MANIFEST_MISSING"; exit 2; }

ACTUAL="$(sha256sum "$TARGET" | awk '{print $1}')"
if [ "$ACTUAL" != "$EXPECTED_OLD" ]; then
  echo "WATCHER_BEFORE_HASH_MISMATCH=$ACTUAL"
  exit 3
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
WATCHER_BAK="${TARGET}.retired_pre_v4_${STAMP}"
MANIFEST_BAK="${MANIFEST}.retired_pre_watcher_v4_${STAMP}"
TMP="/tmp/eira2_repair_watcher_v4.py"
LANE="eira_probe/transport_runtime/eira2_blueprint_deployment_lane_v4.py"
PACKET="/tmp/eira2_live_io_path_v3.json"

curl -fsSL "$SRC_URL" -o "$TMP"
python3 -m py_compile "$TMP"
cp -a "$TARGET" "$WATCHER_BAK"
cp -a "$MANIFEST" "$MANIFEST_BAK"

rollback() {
  cp -a "$WATCHER_BAK" "$TARGET"
  cp -a "$MANIFEST_BAK" "$MANIFEST"
  echo "EIRA2_WATCHER_V4_ROLLBACK=PASS"
}
trap 'rc=$?; if [ $rc -ne 0 ]; then rollback; fi; exit $rc' EXIT

install -m 0644 "$TMP" "${TARGET}.new"
mv -f "${TARGET}.new" "$TARGET"

python3 - <<'PY'
import importlib, json, sys
from pathlib import Path
root=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
manifest=root/'eira2-package-manifest.json'
old=json.loads(manifest.read_text())
source=str(old.get('source_commit_sha') or '').strip()
if not source:
    raise SystemExit('SOURCE_COMMIT_MISSING')
if str(root) not in sys.path:
    sys.path.insert(0,str(root))
mod=importlib.import_module('eira2.operations.package_identity')
write=getattr(mod,'write_package_manifest',None)
verify=getattr(mod,'verify_package_manifest',None)
if not callable(write) or not callable(verify):
    raise SystemExit('PACKAGE_IDENTITY_CONTRACT_UNAVAILABLE')
write(root, source_commit_sha=source)
verified=verify(root)
print('PACKAGE_TREE_SHA256='+str(verified.get('package_tree_sha256')))
PY

python3 tools/eira2_superprobe_engine.py --root "$ROOT" --json >/tmp/eira2_superprobe_v4_check.txt 2>&1
if ! grep -q 'EIRA2_SUPERPROBE=PASS' /tmp/eira2_superprobe_v4_check.txt; then
  tail -40 /tmp/eira2_superprobe_v4_check.txt
  exit 4
fi

python3 - <<'PY'
import json, importlib.util
from pathlib import Path
root=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
report=json.loads((root/'eira_probe/eira2_superprobe_report.json').read_text())
assert report.get('ok') is True, report
assert report.get('schema') == 'eira2_superprobe_forensic_v4', report.get('schema')
assert report.get('evidence_schema') == 'eira2_superprobe_evidence_v4', report.get('evidence_schema')
path=root/'extensions/repair_watcher_ai/plugin.py'
spec=importlib.util.spec_from_file_location('watcher_v4_verify',path)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
status=mod.status()
assert status.get('version') == '2.4.0-eira2-superprobe-v4', status
print('EIRA2_WATCHER_V4=PASS')
PY

mkdir -p "$(dirname "$LANE")"
curl -fsSL "$LANE_URL" -o "$LANE"
python3 -m py_compile "$LANE"
curl -fsSL "$PACKET_URL" -o "$PACKET"
python3 "$LANE" --root "$ROOT" --packet "$PACKET" --source-repo-root "$ROOT/eira_probe/transport_runtime/repo_cache/ish-broadcast"

trap - EXIT
echo "EIRA2_WATCHER_V4_INSTALL=PASS"
echo "EIRA2_IO_RETRY=COMPLETE"
