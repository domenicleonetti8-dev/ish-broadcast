#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"

RUNTIME="$ROOT/eira_probe/transport_runtime"
mkdir -p "$RUNTIME"

curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/63e8833a669025d3e97fce901c25c7d598902c57/EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V2.py \
  -o "$RUNTIME/eira2_blueprint_deployment_lane_v2.py"

curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/00981a5771c105c6aa657ec36fe27e20a09faa06/EIRA2_BLUEPRINT_TRANSPORT_AGENT_V2.py \
  -o "$RUNTIME/eira2_blueprint_transport_agent_v2.py"

python3 -m py_compile \
  "$RUNTIME/eira2_blueprint_deployment_lane_v2.py" \
  "$RUNTIME/eira2_blueprint_transport_agent_v2.py"

python3 "$RUNTIME/eira2_blueprint_transport_agent_v2.py" --root "$ROOT"

PIDFILE="$RUNTIME/blueprint_transport_v2.pid"
if [[ -f "$PIDFILE" ]]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
fi

nohup python3 "$RUNTIME/eira2_blueprint_transport_agent_v2.py" \
  --root "$ROOT" --watch --interval 30 \
  > "$RUNTIME/blueprint_transport_v2.log" 2>&1 < /dev/null &
echo $! > "$PIDFILE"

echo "EIRA2_BLUEPRINT_LANE_V2_INSTALL=PASS"
echo "AGENT_PID=$(cat "$PIDFILE")"
echo "LANE=$RUNTIME/eira2_blueprint_deployment_lane_v2.py"
echo "AGENT=$RUNTIME/eira2_blueprint_transport_agent_v2.py"
