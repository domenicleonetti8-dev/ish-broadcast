#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime"
CONSUMER="$RUNTIME/eira2_bidirectional_blueprint_consumer_v1.py"
CLOG="$ROOT/eira_probe/bidirectional_consumer_v1.log"
CPID="$ROOT/eira_probe/bidirectional_consumer_v1.pid"
RLOG="$ROOT/eira_probe/canonical_live_recovery.log"

cd "$ROOT"
mkdir -p "$RUNTIME" "$ROOT/eira_probe"

curl -fsSL https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_BIDIRECTIONAL_BLUEPRINT_CONSUMER_V1.py -o "$CONSUMER"
python3 -m py_compile "$CONSUMER"

if [[ -f "$CPID" ]]; then
  p="$(cat "$CPID" 2>/dev/null || true)"
  [[ -n "$p" ]] && kill "$p" 2>/dev/null || true
fi
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true
nohup python3 "$CONSUMER" --root "$ROOT" --interval 2 >>"$CLOG" 2>&1 &
echo $! > "$CPID"
sleep 1
kill -0 "$(cat "$CPID")"

port_ok() { python3 - <<'PY'
import socket
s=socket.socket(); s.settimeout(1)
try:
    s.connect(('127.0.0.1',8782)); print('1')
except Exception:
    print('0')
finally:
    s.close()
PY
}

if [[ "$(port_ok)" != "1" ]]; then
  : > "$RLOG"
  nohup python3 main.py >>"$RLOG" 2>&1 &
  p1=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ "$(port_ok)" == "1" ]] && break
    kill -0 "$p1" 2>/dev/null || break
    sleep 1
  done
fi

if [[ "$(port_ok)" != "1" ]]; then
  nohup python3 -m eira2 --live --root "$ROOT" >>"$RLOG" 2>&1 &
  p2=$!
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    [[ "$(port_ok)" == "1" ]] && break
    kill -0 "$p2" 2>/dev/null || break
    sleep 1
  done
fi

if [[ "$(port_ok)" != "1" ]]; then
  nohup python3 -m eira2 --live >>"$RLOG" 2>&1 &
  p3=$!
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    [[ "$(port_ok)" == "1" ]] && break
    kill -0 "$p3" 2>/dev/null || break
    sleep 1
  done
fi

printf 'EIRA2_CONSUMER_RECOVERY=PASS\n'
printf 'CONSUMER_PID=%s\n' "$(cat "$CPID")"
if [[ "$(port_ok)" == "1" ]]; then
  printf 'EIRA2_HTTP_8782=PASS\n'
else
  printf 'EIRA2_HTTP_8782=FAIL\n'
  tail -n 18 "$RLOG" 2>/dev/null || true
  exit 2
fi
