#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
TARGET="$ROOT/extensions/repair_watcher_ai/plugin.py"
EXPECTED_OLD="65fcc14c34ec8fcdf394cd702b3cd1a13ae46f51e7698af69a2437b5ae9c6d17"
SRC="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/4c0b8adbcbfedb140a9676a5caf0bcff9b77555d/EIRA2_REPAIR_WATCHER_V6_FAST_READONLY_FULL_REPLACEMENT.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

before="$(sha256sum "$TARGET" | awk '{print $1}')"
if [ "$before" != "$EXPECTED_OLD" ]; then
  echo "EIRA2_FINAL_TRANSPORT_UNLOCK=ABORT"
  echo "REASON=watcher_sha_mismatch"
  echo "CURRENT_SHA256=$before"
  exit 23
fi

curl -fsSL "$SRC" -o "$TMP/source.py"
python3 - "$TMP/source.py" "$TMP/plugin.py" <<'PY'
import ast, pathlib, sys
src=pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
mod=ast.parse(src)
vals={}
for node in mod.body:
    if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0], ast.Name):
        name=node.targets[0].id
        if name in {'TARGET','NEW'}:
            vals[name]=ast.literal_eval(node.value)
if vals.get('TARGET')!='extensions/repair_watcher_ai/plugin.py':
    raise SystemExit('bad_target_contract')
new=vals.get('NEW')
if not isinstance(new,str):
    raise SystemExit('missing_new_payload')
if 'VERSION = "2.6.0-eira2-fast-readonly-transport-authority"' not in new:
    raise SystemExit('wrong_watcher_version')
if 'fast_read_only_authorization' not in new or 'superprobe_required_for_authorization' not in new:
    raise SystemExit('missing_fast_readonly_contract')
compile(new,'plugin.py','exec')
pathlib.Path(sys.argv[2]).write_text(new,encoding='utf-8')
PY

backup="$ROOT/eira_probe/final_transport_unlock_watcher_v5.py"
cp -f "$TARGET" "$backup"
python3 -m py_compile "$TMP/plugin.py"
install -m 0644 "$TMP/plugin.py" "$TARGET.new"
mv -f "$TARGET.new" "$TARGET"
after="$(sha256sum "$TARGET" | awk '{print $1}')"
python3 -m py_compile "$TARGET"
systemctl --user restart eira2-autonomous-transport-v6.service
sleep 2

if ! systemctl --user is-active --quiet eira2-autonomous-transport-v6.service; then
  echo "EIRA2_FINAL_TRANSPORT_UNLOCK=FAIL"
  echo "AFTER_SHA256=$after"
  exit 24
fi

echo "EIRA2_FINAL_TRANSPORT_UNLOCK=PASS"
echo "BEFORE_SHA256=$before"
echo "AFTER_SHA256=$after"
echo "WATCHER_VERSION=2.6.0-eira2-fast-readonly-transport-authority"
echo "TRANSPORT_V6=ACTIVE"
