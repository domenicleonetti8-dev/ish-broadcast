#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"
RUNTIME="$ROOT/eira_probe/transport_runtime"
mkdir -p "$RUNTIME"

curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py \
  -o "$RUNTIME/eira2_blueprint_deployment_lane_v4.py"

python3 -m py_compile "$RUNTIME/eira2_blueprint_deployment_lane_v4.py"

TMP_REPO="/tmp/eira2_blueprint_v4_repo"
rm -rf "$TMP_REPO"
git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$TMP_REPO"
git -C "$TMP_REPO" checkout --quiet master

PACKET="$TMP_REPO/eira2_transport_bus/to_superprobe/blueprints/eira2_live_io_path_v3.json"
python3 "$RUNTIME/eira2_blueprint_deployment_lane_v4.py" \
  --root "$ROOT" \
  --packet "$PACKET" \
  --source-repo-root "$TMP_REPO"

echo "EIRA2_BLUEPRINT_LANE_V4_REPAIR=PASS"
