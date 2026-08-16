#!/bin/sh
set -eu

broadcast_uid=${1:-$(id -u)}
broadcast_user_status="/run/user/$broadcast_uid/broadcast-hub/status.json"
broadcast_bluez_status="/run/broadcast-hub/bluez-status.json"

for broadcast_status in "$broadcast_bluez_status" "$broadcast_user_status"; do
    if [ ! -r "$broadcast_status" ]; then
        echo "$broadcast_status: unavailable"
        continue
    fi
    echo "$broadcast_status"
    python3 -m json.tool "$broadcast_status"
done
