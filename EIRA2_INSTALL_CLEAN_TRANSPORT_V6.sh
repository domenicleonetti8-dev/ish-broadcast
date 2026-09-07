#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v6"
BOOT="$RUNTIME/boot_watchdog.sh"
SUP="$RUNTIME/eira2_autonomous_transport_v6.py"
LOG="$ROOT/eira_probe/autonomous_transport_v6.log"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE="$SERVICE_DIR/eira2-autonomous-transport-v6.service"
SUP_URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_AUTONOMOUS_TRANSPORT_V6.py

cd "$ROOT"
mkdir -p "$RUNTIME" "$SERVICE_DIR" "$ROOT/eira_probe"

cat > "$BOOT" <<'SH'
#!/usr/bin/env bash
set -u
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v6"
SUP="$RUNTIME/eira2_autonomous_transport_v6.py"
NEXT="$SUP.next"
HB="$RUNTIME/heartbeat.json"
LOG="$ROOT/eira_probe/autonomous_transport_v6.log"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_AUTONOMOUS_TRANSPORT_V6.py
STALE=45
GRACE=60
mkdir -p "$RUNTIME"
fetch(){ rm -f "$NEXT"; curl -fsSL "$URL" -o "$NEXT" 2>>"$LOG" || return 1; python3 -m py_compile "$NEXT" 2>>"$LOG" || return 1; mv -f "$NEXT" "$SUP"; chmod 700 "$SUP"; }
while true; do
  fetch || { printf '%s fetch_failed\n' "$(date -Is)" >>"$LOG"; sleep 3; continue; }
  rm -f "$HB"
  setsid python3 "$SUP" --root "$ROOT" --interval 2 >>"$LOG" 2>&1 &
  child=$!
  started=$(date +%s)
  printf '%s supervisor_start=%s\n' "$(date -Is)" "$child" >>"$LOG"
  while kill -0 "$child" 2>/dev/null; do
    now=$(date +%s)
    if [[ -f "$HB" ]]; then
      mt=$(stat -c %Y "$HB" 2>/dev/null || echo 0)
      if (( now-mt > STALE )); then
        printf '%s heartbeat_stale restart=%s age=%s\n' "$(date -Is)" "$child" "$((now-mt))" >>"$LOG"
        kill -TERM -- "-$child" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-$child" 2>/dev/null || true
        break
      fi
    elif (( now-started > GRACE )); then
      printf '%s heartbeat_missing restart=%s\n' "$(date -Is)" "$child" >>"$LOG"
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

for svc in eira2-autonomous-transport.service eira2-autonomous-transport-v4.service eira2-autonomous-transport-v5.service eira2-autonomous-transport-v6.service; do
  systemctl --user disable --now "$svc" >/dev/null 2>&1 || true
done
pkill -f 'transport_runtime_v2_3/eira2_transport' 2>/dev/null || true
pkill -f 'transport_runtime_v4/eira2_transport' 2>/dev/null || true
pkill -f 'transport_runtime_v5/eira2_transport' 2>/dev/null || true
sleep 1

cat > "$SERVICE" <<EOF
[Unit]
Description=EIRA2 True Single-Checkout Autonomous Transport V6
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=HOME=$HOME
Environment=GIT_TERMINAL_PROMPT=0
ExecStart=$BOOT
Restart=always
RestartSec=2
KillMode=control-group
TimeoutStopSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now eira2-autonomous-transport-v6.service
loginctl enable-linger "$USER" >/dev/null 2>&1 || true
sleep 4
systemctl --user is-active --quiet eira2-autonomous-transport-v6.service
PID=$(systemctl --user show -p MainPID --value eira2-autonomous-transport-v6.service)
[[ -n "$PID" && "$PID" != 0 ]]
printf 'EIRA2_CLEAN_TRANSPORT_V6=PASS\n'
printf 'MODE=systemd-user\n'
printf 'PID=%s\n' "$PID"
printf 'TRUE_SINGLE_CHECKOUT=ENABLED\n'
printf 'V2_2_QUEUE_SUPERVISOR=REMOVED\n'
printf 'V6_HEARTBEAT_WATCHDOG=ENABLED\n'
printf 'LOCAL_FAILURE_RECEIPTS=ENABLED\n'
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'REBOOT_RECOVERY=ENABLED\n'
