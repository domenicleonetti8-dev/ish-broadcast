#!/usr/bin/env bash
set -euo pipefail
USER_NAME="${SUDO_USER:-${USER:-domenicleonetti}}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
BIN="$HOME_DIR/.local/bin/eira2-transport-v2"
STATE="$HOME_DIR/.local/state/eira2-transport-v2"
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
RAW="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/9c4c0ad438b23ec9de4a0449c91daec9925c4127/EIRA2_BIDIRECTIONAL_TRANSPORT_V2_2_2.py"

systemctl stop eira2-bidirectional-transport.service || true
install -d -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.local/bin" "$STATE"
curl -fL "$RAW" -o "$BIN.tmp"
python3 -m py_compile "$BIN.tmp"
install -m 0755 -o "$USER_NAME" -g "$USER_NAME" "$BIN.tmp" "$BIN"
rm -f "$BIN.tmp"

cat >/etc/systemd/system/eira2-bidirectional-transport.service <<EOF
[Unit]
Description=EIRA2 Bidirectional GitHub Transport V2.2.2
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$HOME_DIR
ExecStart=/usr/bin/python3 $BIN --root $ROOT --state $STATE daemon --interval 3
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

rm -f "$STATE/runtime/worker.pid"
systemctl daemon-reload
systemctl enable --now eira2-bidirectional-transport.service
sleep 2
"$BIN" --root "$ROOT" --state "$STATE" status
