#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v2_1"
CONSUMER="$RUNTIME/eira2_omnidirectional_transport_consumer_v2_1.py"
LOG="$ROOT/eira_probe/omnidirectional_transport_v2_1.log"
PIDFILE="$ROOT/eira_probe/omnidirectional_transport_v2_1.pid"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_1.py

cd "$ROOT"
mkdir -p "$RUNTIME" "$ROOT/eira_probe"
curl -fsSL "$URL" -o "$CONSUMER"
python3 -m py_compile "$CONSUMER"

for pf in \
  "$ROOT/eira_probe/bidirectional_consumer_v1.pid" \
  "$ROOT/eira_probe/omnidirectional_transport_v2.pid" \
  "$PIDFILE"
do
  if [[ -f "$pf" ]]; then
    old="$(cat "$pf" 2>/dev/null || true)"
    [[ -n "$old" ]] && kill "$old" 2>/dev/null || true
  fi
done
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2_1.py' 2>/dev/null || true

nohup python3 "$CONSUMER" --root "$ROOT" --interval 2 >>"$LOG" 2>&1 &
echo $! > "$PIDFILE"
sleep 2
kill -0 "$(cat "$PIDFILE")"

printf 'EIRA2_TRANSPORT_V2_1=PASS\n'
printf 'PID=%s\n' "$(cat "$PIDFILE")"
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'INSPECTION_PRIORITY=ENABLED\n'
printf 'STARTED_RECEIPTS=ENABLED\n'
printf 'SELF_REFRESH=ENABLED\n'
