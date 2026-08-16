#!/bin/sh
set -eu

broadcast_config=${1:-/etc/broadcast-hub/config.json}

if ! command -v btmgmt >/dev/null 2>&1; then
    echo "broadcast: btmgmt unavailable; continuing with A2DP service discovery" >&2
    exit 0
fi

broadcast_controller=$(python3 - "$broadcast_config" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream).get("input_controller", ""))
PY
)

if [ -z "$broadcast_controller" ] && command -v bluetoothctl >/dev/null 2>&1; then
    broadcast_controller=$(bluetoothctl list 2>/dev/null | awk '/^Controller / { print $2 }' | sort | sed -n '1p')
fi

if [ -z "$broadcast_controller" ]; then
    echo "broadcast: no Bluetooth controller is available yet" >&2
    exit 0
fi

for broadcast_address_file in /sys/class/bluetooth/hci*/address; do
    [ -f "$broadcast_address_file" ] || continue
    broadcast_address=$(tr '[:lower:]' '[:upper:]' < "$broadcast_address_file")
    [ "$broadcast_address" = "$broadcast_controller" ] || continue
    broadcast_hci=$(basename "$(dirname "$broadcast_address_file")")
    # Major class 0x04 is Audio/Video; minor class 0x14 is Loudspeaker.
    btmgmt --index "$broadcast_hci" class 0x04 0x14 >/dev/null 2>&1 || true
    exit 0
done

echo "broadcast: configured controller $broadcast_controller is not present" >&2
exit 0
