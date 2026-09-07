#!/usr/bin/env bash
set -euo pipefail

ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT="$ROOT/eira_probe/io_path_export/$STAMP"
mkdir -p "$OUT/files"

TARGETS=(
  "tools/eira2_builder_probe.py"
  "tools/eira2_builder_probe_contract.json"
  "eira2/__main__.py"
  "eira2/runtime.py"
  "eira2/live.py"
  "eira2/interfaces/ingress.py"
  "eira2/interfaces/senses.py"
  "eira2/conversation/spine.py"
  "eira2/delivery/gate.py"
  "eira2/delivery/voice.py"
  "eira2/delivery/native_bluetooth_voice.py"
  "tests/test_ingress_to_mouth_path.py"
  "tests/test_end_to_end_mouth_bridge.py"
  "tests/test_streaming_verified_speech.py"
)

python3 - "$ROOT" "$OUT" "${TARGETS[@]}" <<'PY'
import hashlib, json, shutil, sys
from pathlib import Path
root=Path(sys.argv[1]).resolve(); out=Path(sys.argv[2]).resolve(); targets=sys.argv[3:]
rows=[]
for rel in targets:
    src=(root/rel).resolve()
    try: src.relative_to(root)
    except ValueError: raise SystemExit(f"unsafe path: {rel}")
    row={"path":rel,"exists":src.is_file()}
    if src.is_file():
        data=src.read_bytes(); row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        dst=out/"files"/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    rows.append(row)
(out/"inventory.json").write_text(json.dumps({"schema":"eira2_live_io_path_export_v1","files":rows},indent=2)+"\n")
PY

# Read-only qualification; failure is evidence and does not abort export.
set +e
python3 -m pytest -q \
  tests/test_ingress_to_mouth_path.py \
  tests/test_end_to_end_mouth_bridge.py \
  tests/test_streaming_verified_speech.py \
  >"$OUT/qualification.txt" 2>&1
TEST_RC=$?
set -e
printf '{"pytest_returncode":%s}\n' "$TEST_RC" > "$OUT/qualification.json"

WORK="/tmp/eira2_io_export_publish"
rm -rf "$WORK"
git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$WORK"
cd "$WORK"
git checkout --quiet master
DEST="eira2_transport_bus/from_superprobe/io_path/$STAMP"
mkdir -p "$DEST"
cp -a "$OUT"/. "$DEST"/
git add "$DEST"
git -c user.name='EIRA Transport Bridge' -c user.email='eira-transport@localhost' \
  commit --quiet -m "Publish EIRA2 live IO path $STAMP"
git push --quiet origin master

echo "EIRA2_IO_PATH_EXPORT=PASS"
echo "GITHUB_PATH=$DEST"
echo "PYTEST_RC=$TEST_RC"
