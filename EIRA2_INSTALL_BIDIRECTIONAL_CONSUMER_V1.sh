#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime"
LOG="$ROOT/eira_probe/bidirectional_consumer_v1.log"
PIDFILE="$ROOT/eira_probe/bidirectional_consumer_v1.pid"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_BIDIRECTIONAL_BLUEPRINT_CONSUMER_V1.py

cd "$ROOT"
mkdir -p "$RUNTIME"

pkill -f 'EIRA2_BLUEPRINT_TRANSPORT_AGENT_V2.py' 2>/dev/null || true
if [[ -f "$PIDFILE" ]]; then
  oldpid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$oldpid" ]] && kill "$oldpid" 2>/dev/null || true
fi
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true

curl -fsSL "$URL" -o "$RUNTIME/eira2_bidirectional_blueprint_consumer_v1.py"
python3 -m py_compile "$RUNTIME/eira2_bidirectional_blueprint_consumer_v1.py"

python3 "$RUNTIME/eira2_bidirectional_blueprint_consumer_v1.py" --root "$ROOT" --once

nohup python3 "$RUNTIME/eira2_bidirectional_blueprint_consumer_v1.py" \
  --root "$ROOT" --interval 2 \
  >>"$LOG" 2>&1 &
echo $! > "$PIDFILE"
sleep 1
kill -0 "$(cat "$PIDFILE")"

printf 'EIRA2_BIDIRECTIONAL_CONSUMER_INSTALL=PASS\n'
printf 'PID=%s\n' "$(cat "$PIDFILE")"
printf 'LOG=%s\n' "$LOG"
printf 'RETURN_PATH=eira2_transport_bus/from_superprobe/deployments\n'
