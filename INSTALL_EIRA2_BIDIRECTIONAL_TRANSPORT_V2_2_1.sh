#!/usr/bin/env bash
set -euo pipefail
USER_NAME="${SUDO_USER:-${USER:-domenicleonetti}}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
BIN="$HOME_DIR/.local/bin/eira2-transport-v2"
STATE="$HOME_DIR/.local/state/eira2-transport-v2"
ROOT="/media/domenicleonetti/easystore/EIRA/LIVE"
RAW="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/057dfa70bdcf35ec27801467f7aa4392f1e9adc4/EIRA2_BIDIRECTIONAL_TRANSPORT_V2_2_1.py"

systemctl stop eira2-bidirectional-transport.service 2>/dev/null || true

PF="$STATE/runtime/worker.pid"
if [ -f "$PF" ]; then
  PID="$(cat "$PF" 2>/dev/null || true)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && [ -r "/proc/$PID/cmdline" ]; then
    CMD="$(tr '\0' ' ' < "/proc/$PID/cmdline")"
    if [[ "$CMD" == *"EIRA2_BIDIRECTIONAL_TRANSPORT_V2_1.py"* ]] && [[ "$CMD" == *"blueprint-once"* ]]; then
      PGID="$(ps -o pgid= -p "$PID" | tr -d ' ')"
      if [[ "$PGID" =~ ^[0-9]+$ ]]; then
        kill -TERM -- "-$PGID" 2>/dev/null || true
        for _ in 1 2 3 4 5; do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
        kill -0 "$PID" 2>/dev/null && kill -KILL -- "-$PGID" 2>/dev/null || true
      fi
    fi
  fi
  rm -f "$PF"
fi

install -d -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.local/bin" "$STATE"
curl -fL "$RAW" -o "$BIN.tmp"
python3 -m py_compile "$BIN.tmp"
install -m 0755 -o "$USER_NAME" -g "$USER_NAME" "$BIN.tmp" "$BIN"
rm -f "$BIN.tmp"

cat >/etc/systemd/system/eira2-bidirectional-transport.service <<EOF
[Unit]
Description=EIRA2 Bidirectional GitHub Transport V2.2.1
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
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now eira2-bidirectional-transport.service
sleep 2
"$BIN" --root "$ROOT" --state "$STATE" status
