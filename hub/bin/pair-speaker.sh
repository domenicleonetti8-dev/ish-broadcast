#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 CONTROLLER_MAC SPEAKER_MAC" >&2
    exit 2
fi

broadcast_controller=$(printf '%s' "$1" | tr '[:lower:]-' '[:upper:]:')
broadcast_speaker=$(printf '%s' "$2" | tr '[:lower:]-' '[:upper:]:')
broadcast_mac_pattern='^[0-9A-F][0-9A-F]\(:[0-9A-F][0-9A-F]\)\{5\}$'

printf '%s\n' "$broadcast_controller" | grep -q "$broadcast_mac_pattern" || {
    echo "invalid controller address" >&2
    exit 2
}
printf '%s\n' "$broadcast_speaker" | grep -q "$broadcast_mac_pattern" || {
    echo "invalid speaker address" >&2
    exit 2
}

bluetoothctl --timeout 45 <<EOF
select $broadcast_controller
power on
scan bredr
pair $broadcast_speaker
trust $broadcast_speaker
connect $broadcast_speaker a2dp-sink
scan off
quit
EOF

bluetoothctl --timeout 10 <<EOF | grep -E 'Device |Name:|Alias:|Paired:|Trusted:|Connected:|Audio Sink'
select $broadcast_controller
info $broadcast_speaker
quit
EOF
