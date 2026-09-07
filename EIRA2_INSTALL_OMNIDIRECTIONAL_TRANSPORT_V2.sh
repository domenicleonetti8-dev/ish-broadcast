#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v2"
CONSUMER="$RUNTIME/eira2_omnidirectional_transport_consumer_v2.py"
LOG="$ROOT/eira_probe/omnidirectional_transport_v2.log"
PIDFILE="$ROOT/eira_probe/omnidirectional_transport_v2.pid"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2.py

cd "$ROOT"
mkdir -p "$RUNTIME" "$ROOT/eira_probe"
curl -fsSL "$URL" -o "$CONSUMER"
python3 -m py_compile "$CONSUMER"

if [[ -f "$ROOT/eira_probe/bidirectional_consumer_v1.pid" ]]; then
  old="$(cat "$ROOT/eira_probe/bidirectional_consumer_v1.pid" 2>/dev/null || true)"
  [[ -n "$old" ]] && kill "$old" 2>/dev/null || true
fi
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true
if [[ -f "$PIDFILE" ]]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$old" ]] && kill "$old" 2>/dev/null || true
fi
pkill -f 'eira2_omnidirectional_transport_consumer_v2.py' 2>/dev/null || true

nohup python3 "$CONSUMER" --root "$ROOT" --interval 2 >>"$LOG" 2>&1 &
echo $! > "$PIDFILE"
sleep 2
kill -0 "$(cat "$PIDFILE")"

printf 'EIRA2_TRANSPORT_V2=PASS\n'
printf 'PID=%s\n' "$(cat "$PIDFILE")"
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'SELF_REFRESH=ENABLED\n'
