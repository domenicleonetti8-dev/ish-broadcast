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
HEARTBEAT="$ROOT/eira_probe/transport_runtime_v2_3/heartbeat.json"

cd "$ROOT"
mkdir -p "$RUNTIME" "$ROOT/eira_probe" "$SERVICE_DIR"
curl -fsSL "$URL" -o "$CONSUMER"
python3 -m py_compile "$CONSUMER"

for pf in "$ROOT/eira_probe/bidirectional_consumer_v1.pid" "$ROOT/eira_probe/omnidirectional_transport_v2.pid" "$ROOT/eira_probe/omnidirectional_transport_v2_1.pid" "$PIDFILE"; do
  if [[ -f "$pf" ]]; then old="$(cat "$pf" 2>/dev/null || true)"; [[ -n "$old" ]] && kill "$old" 2>/dev/null || true; fi
done
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2_1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2_2.py' 2>/dev/null || true
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
HEARTBEAT="$ROOT/eira_probe/transport_runtime_v2_3/heartbeat.json"
STALE=45
GRACE=75
while true; do
  curl -fsSL "$URL" -o "$CONSUMER.next" 2>>"$LOG" && python3 -m py_compile "$CONSUMER.next" 2>>"$LOG" && mv -f "$CONSUMER.next" "$CONSUMER"
  rm -f "$HEARTBEAT"
  setsid python3 "$CONSUMER" --root "$ROOT" --interval 2 >>"$LOG" 2>&1 &
  child=$!
  started=$(date +%s)
  printf '%s supervisor_start=%s\n' "$(date -Is)" "$child" >>"$LOG"
  while kill -0 "$child" 2>/dev/null; do
    now=$(date +%s)
    age=$((now-started))
    if [[ -f "$HEARTBEAT" ]]; then
      mt=$(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0)
      stale=$((now-mt))
      if (( stale > STALE )); then
        printf '%s heartbeat_stale=%s killing=%s\n' "$(date -Is)" "$stale" "$child" >>"$LOG"
        kill -TERM -- "-$child" 2>/dev/null || true
        sleep 5
        kill -KILL -- "-$child" 2>/dev/null || true
        break
      fi
    elif (( age > GRACE )); then
      printf '%s heartbeat_missing age=%s killing=%s\n' "$(date -Is)" "$age" "$child" >>"$LOG"
      kill -TERM -- "-$child" 2>/dev/null || true
      sleep 5
      kill -KILL -- "-$child" 2>/dev/null || true
      break
    fi
    sleep 5
  done
  wait "$child" 2>/dev/null || true
  printf '%s supervisor_restart\n' "$(date -Is)" >>"$LOG"
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
  nohup "$WATCHDOG" >>"$LOG" 2>&1 & echo $! > "$PIDFILE"
  if command -v crontab >/dev/null 2>&1; then { crontab -l 2>/dev/null | grep -v 'eira2 transport watchdog' || true; echo "@reboot $WATCHDOG # eira2 transport watchdog"; } | crontab -; fi
fi
sleep 4
if [[ "$MODE" == systemd-user ]]; then
  systemctl --user is-active --quiet eira2-autonomous-transport.service
  PID="$(systemctl --user show -p MainPID --value eira2-autonomous-transport.service)"
else
  PID="$(pgrep -f 'watchdog.sh' | head -n1 || true)"; [[ -n "$PID" ]]
fi
printf 'EIRA2_AUTONOMOUS_TRANSPORT_V3=PASS\n'
printf 'MODE=%s\n' "$MODE"
printf 'PID=%s\n' "$PID"
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'RETRY_UNTIL_TERMINAL_SUCCESS=ENABLED\n'
printf 'WATCHER_RESTART_RECOVERY=ENABLED\n'
printf 'WORKER_STALE_RECOVERY=ENABLED\n'
printf 'SUPERVISOR_HEARTBEAT_WATCHDOG=ENABLED\n'
printf 'SELF_REFRESH=ENABLED\n'
printf 'REBOOT_RECOVERY=ENABLED\n'
