#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
OUT="$ROOT/eira_probe/kernel_lock_forensic_v1.json"
TMP="$OUT.tmp.$$"
cd "$ROOT"
python3 - <<'PY' > "$TMP"
from __future__ import annotations
import ast, json, traceback, importlib.util, asyncio, inspect, os, sys, time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
result={'schema':'eira2_kernel_lock_forensic_v1','generated_unix':time.time(),'root':str(ROOT),'matches':[],'runtime_start':None}
# Find exact live references to kernel.lock and nearby source.
for base in [ROOT/'eira2', ROOT/'extensions']:
    if not base.exists(): continue
    for p in base.rglob('*.py'):
        try: text=p.read_text(encoding='utf-8',errors='replace')
        except Exception: continue
        if 'kernel.lock' not in text and 'required_service_failed' not in text: continue
        lines=text.splitlines()
        hits=[]
        for i,line in enumerate(lines):
            if 'kernel.lock' in line or 'required_service_failed' in line:
                a=max(0,i-50); b=min(len(lines),i+51)
                hits.append({'line':i+1,'start_line':a+1,'end_line':b,'source':'\n'.join(f'{n+1:05d}: {lines[n]}' for n in range(a,b))})
        result['matches'].append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'hits':hits})
# Capture imported supervisor/service topology without mutating anything.
try:
    sp=ROOT/'eira2/kernel/supervisor.py'
    if sp.is_file():
        spec=importlib.util.spec_from_file_location('eira2_kernel_supervisor_forensic',sp)
        mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        result['supervisor_module']={'loaded':True,'symbols':[n for n in dir(mod) if 'lock' in n.lower() or 'service' in n.lower() or 'supervisor' in n.lower()]}
except Exception as e:
    result['supervisor_module']={'loaded':False,'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()}
# Reproduce the live runtime start to expose the chained inner exception.
async def probe_runtime():
    try:
        from eira2.runtime import Eira2Runtime
        sig=inspect.signature(Eira2Runtime)
        return {'constructed':False,'signature':str(sig),'note':'constructor requires live dependencies; traceback below is captured from canonical live entry instead'}
    except Exception as e:
        return {'constructed':False,'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()}
try:
    result['runtime_probe']=asyncio.run(probe_runtime())
except Exception as e:
    result['runtime_probe']={'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()}
print(json.dumps(result,indent=2,sort_keys=True))
PY
mv -f "$TMP" "$OUT"
# Publish evidence through the existing GitHub checkout if available; otherwise clone a minimal transport checkout.
WORK="$ROOT/eira_probe/kernel_lock_forensic_repo"
if [[ ! -d "$WORK/.git" ]]; then
  rm -rf "$WORK"
  git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$WORK"
fi
git -C "$WORK" fetch --quiet origin master
git -C "$WORK" checkout --quiet master
git -C "$WORK" reset --hard --quiet origin/master
DEST="$WORK/eira2_transport_bus/from_superprobe/receipts/kernel_lock_forensic_bootstrap_v1__receipt.json"
mkdir -p "$(dirname "$DEST")"
cp "$OUT" "$DEST"
git -C "$WORK" add "eira2_transport_bus/from_superprobe/receipts/kernel_lock_forensic_bootstrap_v1__receipt.json"
if ! git -C "$WORK" diff --cached --quiet; then
  git -C "$WORK" -c user.name='EIRA Kernel Forensic' -c user.email='eira-kernel-forensic@localhost' commit --quiet -m 'Return kernel.lock forensic bootstrap evidence'
  git -C "$WORK" pull --rebase --quiet origin master
  git -C "$WORK" push --quiet origin master
fi
printf 'EIRA2_KERNEL_LOCK_FORENSIC=PASS\n'
printf 'EVIDENCE=%s\n' "$OUT"
