#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
DST="$ROOT/extensions/repair_watcher_ai"
SRC_URL="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_REPAIR_WATCHER_PLUGIN_V3_BOUNDED.py"

cd "$ROOT"
mkdir -p "$DST"

if [ ! -f "$DST/plugin_legacy_v2_6_0.py" ]; then
  cp "$DST/plugin.py" "$DST/plugin_legacy_v2_6_0.py"
fi

curl -fsSL "$SRC_URL" -o "$DST/plugin.py.new"
python3 -m py_compile "$DST/plugin.py.new"
mv "$DST/plugin.py.new" "$DST/plugin.py"

python3 - <<'PY'
import importlib.util
from pathlib import Path
p=Path('extensions/repair_watcher_ai/plugin.py')
s=importlib.util.spec_from_file_location('rw',p)
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
r=m.authorize_transport_request({
 'schema':'eira2_transport_request_v1',
 'request_id':'watcher_v3_local_selftest',
 'operation':'deploy',
 'deployment':{
   'source':{'commit':'0'*40,'path':'EIRA2_SELFTEST.py'},
   'target':{'path':'eira_probe/selftest/EIRA2_SELFTEST.py'}
 },
 'requirements':{'watcher_authorizes':True,'builder_invoked':True}
})
assert r.get('authorized') is True, r
assert r.get('fast_deploy_authorization') is True, r
assert r.get('write_authority_granted') is True, r
print('WATCHER_V3=PASS')
print('VERSION='+r['watcher_version'])
print('AUTH_MS='+str(r['authorization_elapsed_ms']))
PY
