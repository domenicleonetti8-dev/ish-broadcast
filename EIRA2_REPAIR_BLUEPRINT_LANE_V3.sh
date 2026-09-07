#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"
RUNTIME="$ROOT/eira_probe/transport_runtime"
mkdir -p "$RUNTIME"

curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/0c6f1c5be6211911d2e3068a73d04f5820cf6916/EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V3.py \
  -o "$RUNTIME/eira2_blueprint_deployment_lane_v2.py"
python3 -m py_compile "$RUNTIME/eira2_blueprint_deployment_lane_v2.py"

WORK="/tmp/eira2_blueprint_v3_source"
rm -rf "$WORK"
git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$WORK"
git -C "$WORK" checkout --quiet master

PACKET="/tmp/eira2_live_io_path_v2.json"
curl -fsSL \
  https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/8ed18dd4554752b018341555062366e63bd5f28e/EIRA2_LIVE_IO_PATH_PACKET_V2.json \
  -o "$PACKET"

python3 "$RUNTIME/eira2_blueprint_deployment_lane_v2.py" \
  --root "$ROOT" \
  --packet "$PACKET" \
  --source-repo-root "$WORK"

echo "EIRA2_BLUEPRINT_LANE_V3_REPAIR=PASS"
