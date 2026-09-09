#!/usr/bin/env bash
set -euo pipefail
USER_NAME="${SUDO_USER:-${USER:-domenicleonetti}}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
BIN="$HOME_DIR/.local/bin/eira2-transport-v2"
STATE="$HOME_DIR/.local/state/eira2-transport-v2"
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
RAW="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/877d8066886d3c78779de853655be16dcb8001cd/EIRA2_BIDIRECTIONAL_TRANSPORT_V2_2.py"

systemctl stop eira2-bidirectional-transport.service 2>/dev/null || true
install -d -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.local/bin" "$STATE"
curl -fL "$RAW" -o "$BIN.tmp"
python3 -m py_compile "$BIN.tmp"
install -m 0755 -o "$USER_NAME" -g "$USER_NAME" "$BIN.tmp" "$BIN"
rm -f "$BIN.tmp"

cat >/etc/systemd/system/eira2-bidirectional-transport.service <<EOF
[Unit]
Description=EIRA2 Bidirectional GitHub Transport V2.2
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
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

sudo -u "$USER_NAME" "$BIN" --root "$ROOT" --state "$STATE" baseline --clear-inbox
systemctl daemon-reload
systemctl enable --now eira2-bidirectional-transport.service
sleep 2
systemctl --no-pager --full status eira2-bidirectional-transport.service | sed -n '1,12p'
sudo -u "$USER_NAME" "$BIN" --root "$ROOT" --state "$STATE" status
