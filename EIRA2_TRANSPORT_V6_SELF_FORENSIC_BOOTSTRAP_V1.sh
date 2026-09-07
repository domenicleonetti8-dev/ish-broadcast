#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v6"
OUT="$ROOT/eira_probe/transport_v6_self_forensic_v1.json"
REPO="$RUNTIME/repo"
cd "$ROOT"
python3 - <<'PY'
import json, os, subprocess, time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
RUNTIME=ROOT/'eira_probe'/'transport_runtime_v6'
REPO=RUNTIME/'repo'
OUT=ROOT/'eira_probe'/'transport_v6_self_forensic_v1.json'
def cmd(args,cwd=None):
    try:
        p=subprocess.run(args,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=20,check=False)
        return {'rc':p.returncode,'stdout':p.stdout[-12000:],'stderr':p.stderr[-12000:]}
    except Exception as e:
        return {'error':f'{type(e).__name__}:{e}'}
def read_json(p):
    try:return json.loads(p.read_text())
    except Exception:return None
def tail(p,n=120):
    try:return '\n'.join(p.read_text(errors='replace').splitlines()[-n:])
    except Exception as e:return f'{type(e).__name__}:{e}'
out={
 'schema':'eira2_transport_v6_self_forensic_v1',
 'generated_unix':time.time(),
 'root':str(ROOT),
 'runtime_exists':RUNTIME.exists(),
 'heartbeat':read_json(RUNTIME/'heartbeat.json'),
 'supervisor_error':read_json(RUNTIME/'supervisor_error.json'),
 'local_receipts':[p.name for p in sorted((RUNTIME/'local_receipts').glob('*.json'))][-40:] if (RUNTIME/'local_receipts').exists() else [],
 'state_files':[p.name for p in sorted((RUNTIME/'state').glob('*.json'))][-40:] if (RUNTIME/'state').exists() else [],
 'service_status':cmd(['systemctl','--user','status','eira2-autonomous-transport-v6.service','--no-pager','-n','80']),
 'service_props':cmd(['systemctl','--user','show','eira2-autonomous-transport-v6.service','-p','ActiveState','-p','SubState','-p','MainPID','-p','ExecMainStatus','-p','NRestarts']),
 'processes':cmd(['ps','-eo','pid,ppid,etime,stat,cmd']),
 'log_tail':tail(ROOT/'eira_probe'/'autonomous_transport_v6.log',160),
 'repo_exists':(REPO/'.git').is_dir(),
 'repo_head':cmd(['git','rev-parse','HEAD'],cwd=REPO) if (REPO/'.git').is_dir() else None,
 'repo_status':cmd(['git','status','--short','--branch'],cwd=REPO) if (REPO/'.git').is_dir() else None,
 'origin_master':cmd(['git','rev-parse','origin/master'],cwd=REPO) if (REPO/'.git').is_dir() else None,
 'inbox_files':[p.name for p in sorted((REPO/'eira2_transport_bus/to_superprobe/requests').glob('*.json'))] if (REPO/'eira2_transport_bus/to_superprobe/requests').exists() else [],
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$TMP/repo"
cd "$TMP/repo"
mkdir -p eira2_transport_bus/from_superprobe/receipts
cp "$OUT" eira2_transport_bus/from_superprobe/receipts/transport_v6_self_forensic_v1__receipt.json
git add eira2_transport_bus/from_superprobe/receipts/transport_v6_self_forensic_v1__receipt.json
git -c user.name='EIRA Transport Forensic' -c user.email='eira-transport-forensic@localhost' commit --quiet -m 'Return EIRA2 transport V6 self forensic v1'
git push --quiet origin master
printf 'EIRA2_TRANSPORT_V6_SELF_FORENSIC=PASS\n'
printf 'EVIDENCE=%s\n' "$OUT"
