#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v4"
BOOT="$RUNTIME/boot_watchdog.sh"
SUP="$RUNTIME/eira2_transport_supervisor.py"
HB="$ROOT/eira_probe/transport_runtime_v2_3/heartbeat.json"
LOG="$ROOT/eira_probe/autonomous_transport_v4.log"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE="$SERVICE_DIR/eira2-autonomous-transport-v4.service"
SUP_URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_2.py

cd "$ROOT"
mkdir -p "$RUNTIME" "$SERVICE_DIR" "$ROOT/eira_probe"

cat > "$BOOT" <<'SH'
#!/usr/bin/env bash
set -u
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v4"
SUP="$RUNTIME/eira2_transport_supervisor.py"
NEXT="$SUP.next"
HB="$ROOT/eira_probe/transport_runtime_v2_3/heartbeat.json"
LOG="$ROOT/eira_probe/autonomous_transport_v4.log"
SUP_URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_2.py
HB_STALE=30
HB_GRACE=45
UPDATE_CHECK=10

mkdir -p "$RUNTIME" "$ROOT/eira_probe"
fetch_supervisor() {
  rm -f "$NEXT"
  curl -fsSL "$SUP_URL" -o "$NEXT" 2>>"$LOG" || return 1
  python3 -m py_compile "$NEXT" 2>>"$LOG" || { rm -f "$NEXT"; return 1; }
  if [[ ! -f "$SUP" ]] || ! cmp -s "$NEXT" "$SUP"; then
    mv -f "$NEXT" "$SUP"
    chmod 700 "$SUP"
    return 0
  fi
  rm -f "$NEXT"
  return 2
}

while true; do
  fetch_supervisor || rc=$?
  if [[ ! -f "$SUP" ]]; then
    printf '%s supervisor_unavailable\n' "$(date -Is)" >>"$LOG"
    sleep 3
    continue
  fi
  rm -f "$HB"
  setsid python3 "$SUP" --root "$ROOT" --interval 2 >>"$LOG" 2>&1 &
  child=$!
  started=$(date +%s)
  last_update_check=$started
  printf '%s supervisor_start=%s\n' "$(date -Is)" "$child" >>"$LOG"
  while kill -0 "$child" 2>/dev/null; do
    now=$(date +%s)
    age=$((now-started))
    if (( now-last_update_check >= UPDATE_CHECK )); then
      last_update_check=$now
      if fetch_supervisor; then
        printf '%s supervisor_remote_update restart=%s\n' "$(date -Is)" "$child" >>"$LOG"
        kill -TERM -- "-$child" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-$child" 2>/dev/null || true
        break
      fi
    fi
    if [[ -f "$HB" ]]; then
      mt=$(stat -c %Y "$HB" 2>/dev/null || echo 0)
      stale=$((now-mt))
      if (( stale > HB_STALE )); then
        printf '%s heartbeat_stale=%s restart=%s\n' "$(date -Is)" "$stale" "$child" >>"$LOG"
        kill -TERM -- "-$child" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-$child" 2>/dev/null || true
        break
      fi
    elif (( age > HB_GRACE )); then
      printf '%s heartbeat_missing age=%s restart=%s\n' "$(date -Is)" "$age" "$child" >>"$LOG"
      kill -TERM -- "-$child" 2>/dev/null || true
      sleep 2
      kill -KILL -- "-$child" 2>/dev/null || true
      break
    fi
    sleep 2
  done
  wait "$child" 2>/dev/null || true
  printf '%s supervisor_restart\n' "$(date -Is)" >>"$LOG"
  sleep 2
done
SH
chmod 700 "$BOOT"

systemctl --user disable --now eira2-autonomous-transport.service >/dev/null 2>&1 || true
systemctl --user disable --now eira2-autonomous-transport-v4.service >/dev/null 2>&1 || true
pkill -f 'eira2_bidirectional_blueprint_consumer_v1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2_1.py' 2>/dev/null || true
pkill -f 'eira2_omnidirectional_transport_consumer_v2_2.py' 2>/dev/null || true
pkill -f 'eira2_transport_supervisor.py' 2>/dev/null || true
pkill -f 'EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py' 2>/dev/null || true
sleep 1

cat > "$SERVICE" <<EOF
[Unit]
Description=EIRA2 Clean Autonomous Transport V4
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$BOOT
Restart=always
RestartSec=2
KillMode=control-group
TimeoutStopSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now eira2-autonomous-transport-v4.service
loginctl enable-linger "$USER" >/dev/null 2>&1 || true
sleep 4
systemctl --user is-active --quiet eira2-autonomous-transport-v4.service
PID=$(systemctl --user show -p MainPID --value eira2-autonomous-transport-v4.service)
[[ -n "$PID" && "$PID" != 0 ]]

printf 'EIRA2_CLEAN_TRANSPORT_V4=PASS\n'
printf 'MODE=systemd-user\n'
printf 'PID=%s\n' "$PID"
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'DIRECT_SUPERVISOR_V2_2=ENABLED\n'
printf 'OUTER_WATCHDOG=ENABLED\n'
printf 'HEARTBEAT_KILL_RESTART=ENABLED\n'
printf 'REMOTE_SUPERVISOR_UPDATE_RESTART=ENABLED\n'
printf 'WATCHER_BUILDER_SUPERPROBE_PATH=ENABLED\n'
printf 'REBOOT_RECOVERY=ENABLED\n'
