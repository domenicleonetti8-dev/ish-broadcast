#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="/tmp/eira2_watcher_contract_$TS"
REPO="/tmp/eira2_watcher_contract_repo_$TS"
mkdir -p "$OUT"
cp extensions/repair_watcher_ai/plugin.py "$OUT/plugin.py"
python3 - <<'PY' "$OUT"
import ast,json,sys
from pathlib import Path
out=Path(sys.argv[1]); p=out/'plugin.py'; src=p.read_text(); tree=ast.parse(src)
funcs={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
res={'schema':'eira2_watcher_contract_export_v1','functions':{},'string_literals':[]}
for name in ('_inbox','_verify_package','_impact','_build_plan','inspect_once','deploy_builder_probe'):
 n=funcs.get(name)
 if not n: continue
 res['functions'][name]={'args':[a.arg for a in n.args.args],'lineno':n.lineno,'end_lineno':getattr(n,'end_lineno',None)}
for n in ast.walk(tree):
 if isinstance(n,ast.Constant) and isinstance(n.value,str):
  s=n.value
  if any(k in s.casefold() for k in ('package','index','builder','watcher','inbox','stage','repair')):
   res['string_literals'].append(s)
(out/'contract.json').write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
PY
git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$REPO"
DEST="$REPO/eira2_transport_bus/from_superprobe/watcher_contract/$TS"
mkdir -p "$DEST"
cp "$OUT/plugin.py" "$OUT/contract.json" "$DEST/"
cd "$REPO"
git add "eira2_transport_bus/from_superprobe/watcher_contract/$TS"
git -c user.name='EIRA Watcher Contract Bridge' -c user.email='eira-watcher@localhost' commit --quiet -m "Return LIVE Watcher contract $TS"
git push --quiet origin master
echo "EIRA2_WATCHER_CONTRACT_EXPORT=PASS"
echo "GITHUB_PATH=eira2_transport_bus/from_superprobe/watcher_contract/$TS"
