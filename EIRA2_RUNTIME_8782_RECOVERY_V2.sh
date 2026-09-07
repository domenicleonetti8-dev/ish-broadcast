#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
PROBE="$ROOT/eira_probe"
LOG="$PROBE/canonical_live_recovery_v2.log"
RECEIPT="$PROBE/runtime_8782_recovery_v2.json"
cd "$ROOT"
mkdir -p "$PROBE"

port_ok(){ python3 - <<'PY'
import socket
s=socket.socket(); s.settimeout(1)
try:
 s.connect(('127.0.0.1',8782)); print('1')
except Exception: print('0')
finally: s.close()
PY
}

before="$(port_ok)"
action=preserve_existing
if [[ "$before" != 1 ]]; then
  action=start_canonical_eira2_live
  : >"$LOG"
  nohup python3 -m eira2 --live --root "$ROOT" >>"$LOG" 2>&1 &
  pid=$!
  for _ in $(seq 1 30); do
    [[ "$(port_ok)" == 1 ]] && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
fi
after="$(port_ok)"
python3 - "$RECEIPT" "$before" "$after" "$action" <<'PY'
import json,sys,time,subprocess
p,b,a,action=sys.argv[1:]
def cmd(x):
 r=subprocess.run(x,text=True,capture_output=True,check=False); return {'rc':r.returncode,'stdout':r.stdout[-6000:],'stderr':r.stderr[-3000:]}
obj={'schema':'eira2_runtime_8782_recovery_v2','generated_unix':time.time(),'port_8782_before':b=='1','port_8782_after':a=='1','action':action,'health':cmd(['curl','-sS','--max-time','5','http://127.0.0.1:8782/health']),'processes':cmd(['pgrep','-af','python3.*(main.py|eira2.*live)'])}
open(p,'w').write(json.dumps(obj,indent=2,sort_keys=True)+'\n')
print('EIRA2_RUNTIME_8782_RECOVERY='+('PASS' if a=='1' else 'FAIL'))
print('ACTION='+action)
print('EVIDENCE='+p)
raise SystemExit(0 if a=='1' else 2)
PY