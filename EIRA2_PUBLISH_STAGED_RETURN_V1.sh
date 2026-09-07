#!/usr/bin/env bash
set -euo pipefail

ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
cd "$ROOT"

SRC_BASE="$ROOT/eira_probe/transport_outbox/from_superprobe"
LATEST="$(find "$SRC_BASE" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
[ -n "$LATEST" ] || { echo "NO_STAGED_RETURN"; exit 1; }
STAMP="$(basename "$LATEST")"

WORK="/tmp/eira2_transport_publish"
rm -rf "$WORK"
git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$WORK"
cd "$WORK"
git checkout --quiet master

dest="eira2_transport_bus/from_superprobe/$STAMP"
mkdir -p "$dest"
cp -a "$LATEST"/. "$dest"/

count="$(find "$dest" -maxdepth 1 -type f | wc -l | tr -d ' ')"
[ "$count" -gt 0 ] || { echo "RETURN_EMPTY"; exit 1; }

git add "$dest"
if git diff --cached --quiet; then
  echo "RETURN_ALREADY_PUBLISHED=$dest"
  exit 0
fi

git -c user.name='EIRA Transport Bridge' \
    -c user.email='eira-transport@localhost' \
    commit --quiet -m "Publish Superprobe return $STAMP"

git push --quiet origin master

echo "EIRA2_RETURN_PUBLISH=PASS"
echo "GITHUB_PATH=$dest"
echo "FILES=$count"
