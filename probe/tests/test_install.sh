#!/bin/sh
set -eu

broadcast_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
broadcast_stage=$(mktemp -d)
trap 'rm -rf "$broadcast_stage"' EXIT HUP INT TERM

BROADCAST_PROBE_HOME=/home/tester sh "$broadcast_root/probe/install.sh" \
    --destdir "$broadcast_stage" \
    --user tester \
    --input-controller 00:11:22:33:44:55

test -x "$broadcast_stage/usr/local/lib/broadcast-probe/broadcast_probe.py"
test -x "$broadcast_stage/usr/local/lib/broadcast-probe/broadcast_bluez.py"
test -x "$broadcast_stage/usr/local/lib/broadcast-probe/assert-portable-host.sh"
test -x "$broadcast_stage/usr/local/bin/broadcast-pair-speaker"
test -f "$broadcast_stage/etc/systemd/system/broadcast-bluetooth.service"
test -f "$broadcast_stage/etc/systemd/user/broadcast-probe.service"
test -f "$broadcast_stage/home/tester/.config/wireplumber/wireplumber.conf.d/90-broadcast.conf"
test -f "$broadcast_stage/home/tester/.config/wireplumber/bluetooth.lua.d/90-broadcast.lua"
grep -q 'assert-portable-host.sh' "$broadcast_stage/etc/systemd/system/broadcast-bluetooth.service"
grep -q 'assert-portable-host.sh' "$broadcast_stage/etc/systemd/user/broadcast-probe.service"
grep -q 'class 0x04 0x05' "$broadcast_stage/usr/local/lib/broadcast-probe/prepare-controller-class.sh"

BROADCAST_HOSTNAME=broadcast-pocket sh "$broadcast_root/probe/bin/assert-portable-host.sh"
if BROADCAST_HOSTNAME=eira sh "$broadcast_root/probe/bin/assert-portable-host.sh" >/dev/null 2>&1; then
    echo "portable-host guard accepted Eira" >&2
    exit 1
fi
if BROADCAST_HOSTNAME=EIRA.local sh "$broadcast_root/probe/bin/assert-portable-host.sh" >/dev/null 2>&1; then
    echo "portable-host guard accepted Eira's qualified hostname" >&2
    exit 1
fi
sh "$broadcast_root/probe/install.sh" --help | grep -q -- '--portable'

python3 - "$broadcast_stage/etc/broadcast-probe/config.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
assert value["device_name"] == "broadcast"
assert value["input_controller"] == "00:11:22:33:44:55"
assert value["max_outputs"] == 10
value["speaker_priority"] = ["10:20:30:40:50:60"]
path.write_text(json.dumps(value) + "\n", encoding="utf-8")
PY

# A second install must preserve operator-owned speaker configuration.
BROADCAST_PROBE_HOME=/home/tester sh "$broadcast_root/probe/install.sh" \
    --destdir "$broadcast_stage" \
    --user tester \
    --input-controller 00:11:22:33:44:55 >/dev/null

python3 - "$broadcast_stage/etc/broadcast-probe/config.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
assert value["speaker_priority"] == ["10:20:30:40:50:60"]
PY

echo "test_install: PASS"
