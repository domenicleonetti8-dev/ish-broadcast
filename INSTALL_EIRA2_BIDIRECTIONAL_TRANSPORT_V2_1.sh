#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER:-domenicleonetti}}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
BIN="$HOME_DIR/.local/bin/eira2-transport-v2"
STATE="$HOME_DIR/.local/state/eira2-transport-v2"
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
RAW="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/4e42a53209a9ed932d30ec1c100ddfb325fbbfcf/EIRA2_BIDIRECTIONAL_TRANSPORT_V2_1.py"

install -d -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.local/bin" "$STATE"
curl -fL "$RAW" -o "$BIN.tmp"
python3 -m py_compile "$BIN.tmp"
install -m 0755 -o "$USER_NAME" -g "$USER_NAME" "$BIN.tmp" "$BIN"
rm -f "$BIN.tmp"

cat >/etc/systemd/system/eira2-bidirectional-transport.service <<EOF
[Unit]
Description=EIRA2 Bidirectional GitHub Transport V2.1
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$HOME_DIR
ExecStart=/usr/bin/python3 $BIN --root $ROOT --state $STATE daemon --interval 3
Restart=always
RestartSec=3
KillMode=process
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now eira2-bidirectional-transport.service
sleep 2
systemctl --no-pager --full status eira2-bidirectional-transport.service | sed -n '1,12p'
"$BIN" --root "$ROOT" --state "$STATE" status
