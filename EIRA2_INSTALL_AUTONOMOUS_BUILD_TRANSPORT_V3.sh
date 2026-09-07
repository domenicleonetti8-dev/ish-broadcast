#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v3"
CONSUMER="$RUNTIME/eira2_omnidirectional_transport_supervisor.py"
LOG="$ROOT/eira_probe/autonomous_transport_v3.log"
PIDFILE="$ROOT/eira_probe/autonomous_transport_v3.pid"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_1.py
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE="$SERVICE_DIR/eira2-autonomous-transport.service"
WATCHDOG="$RUNTIME/watchdog.sh"

cd "$ROOT"
mkdir -p "$RUNTIME" "$ROOT/eira_probe" "$SERVICE_DIR"

curl -fsSL "$URL" -o "$CONSUMER"
python3 -m py_compile "$CONSUMER"

# Retire every previous transport generation and orphaned deployment worker.
for pf in \
  "$ROOT/eira_probe/bidirectional_consumer_v1.pid" \
  "$ROOT/eira_probe/omnidirectional_transport_v2.pid" \
  "$ROOT/eira_probe/omnidirectional_transport_v2_1.pid" \
  "$PIDFILE"
do
  if [[ -f "$pf" ]]; then
    old="$(cat "$pf" 2>/dev/null || true)"
    [[ -n "$old" ]] && kill "$old" 2>/dev/null || true
  fi
done
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2_1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_supervisor.py' 2>/dev/null || true
pkill -f 'EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py' 2>/dev/null || true
sleep 1

cat > "$WATCHDOG" <<'SH'
#!/usr/bin/env bash
set -u
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v3"
CONSUMER="$RUNTIME/eira2_omnidirectional_transport_supervisor.py"
LOG="$ROOT/eira_probe/autonomous_transport_v3.log"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_1.py
while true; do
  curl -fsSL "$URL" -o "$CONSUMER.next" 2>>"$LOG" && \
    python3 -m py_compile "$CONSUMER.next" 2>>"$LOG" && \
    mv -f "$CONSUMER.next" "$CONSUMER"
  python3 "$CONSUMER" --root "$ROOT" --interval 2 >>"$LOG" 2>&1
  rc=$?
  printf '%s supervisor_exit=%s restarting\n' "$(date -Is)" "$rc" >>"$LOG"
  sleep 2
done
SH
chmod 700 "$WATCHDOG"

cat > "$SERVICE" <<EOF
[Unit]
Description=EIRA2 Autonomous GitHub Build Transport
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$WATCHDOG
Restart=always
RestartSec=2
KillMode=control-group
TimeoutStopSec=15

[Install]
WantedBy=default.target
EOF

MODE=watchdog
if command -v systemctl >/dev/null 2>&1 && systemctl --user daemon-reload >/dev/null 2>&1; then
  systemctl --user disable --now eira2-autonomous-transport.service >/dev/null 2>&1 || true
  systemctl --user enable --now eira2-autonomous-transport.service >/dev/null
  loginctl enable-linger "$USER" >/dev/null 2>&1 || true
  MODE=systemd-user
else
  nohup "$WATCHDOG" >>"$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  if command -v crontab >/dev/null 2>&1; then
    { crontab -l 2>/dev/null | grep -v 'eira2 transport watchdog' || true; echo "@reboot $WATCHDOG # eira2 transport watchdog"; } | crontab -
  fi
fi

sleep 3
if [[ "$MODE" == systemd-user ]]; then
  systemctl --user is-active --quiet eira2-autonomous-transport.service
  PID="$(systemctl --user show -p MainPID --value eira2-autonomous-transport.service)"
else
  PID="$(pgrep -f 'eira2_omnidirectional_transport_supervisor.py' | head -n1 || true)"
  [[ -n "$PID" ]]
fi

printf 'EIRA2_AUTONOMOUS_TRANSPORT_V3=PASS\n'
printf 'MODE=%s\n' "$MODE"
printf 'PID=%s\n' "$PID"
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'RETRY_UNTIL_TERMINAL_SUCCESS=ENABLED\n'
printf 'WATCHER_RESTART_RECOVERY=ENABLED\n'
printf 'WORKER_STALE_RECOVERY=ENABLED\n'
printf 'SELF_REFRESH=ENABLED\n'
printf 'REBOOT_RECOVERY=ENABLED\n'
