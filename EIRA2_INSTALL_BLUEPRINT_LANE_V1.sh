#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"

RUNTIME="$ROOT/eira_probe/transport_runtime"
mkdir -p "$RUNTIME"

curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V1.py \
  -o "$RUNTIME/eira2_blueprint_deployment_lane.py"

curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_BLUEPRINT_TRANSPORT_AGENT_V1.py \
  -o "$RUNTIME/eira2_blueprint_transport_agent.py"

python3 -m py_compile \
  "$RUNTIME/eira2_blueprint_deployment_lane.py" \
  "$RUNTIME/eira2_blueprint_transport_agent.py"

python3 "$RUNTIME/eira2_blueprint_transport_agent.py" --root "$ROOT"

echo "EIRA2_BLUEPRINT_LANE_INSTALL=PASS"
echo "LANE=$RUNTIME/eira2_blueprint_deployment_lane.py"
echo "AGENT=$RUNTIME/eira2_blueprint_transport_agent.py"
