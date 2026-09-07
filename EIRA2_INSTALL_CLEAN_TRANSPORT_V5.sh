#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v5"
BOOT="$RUNTIME/boot.sh"
SUP="$RUNTIME/eira2_transport_v5.py"
LOG="$ROOT/eira_probe/autonomous_transport_v5.log"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE="$SERVICE_DIR/eira2-autonomous-transport-v5.service"
SUP_URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_2.py

cd "$ROOT"
mkdir -p "$RUNTIME" "$SERVICE_DIR" "$ROOT/eira_probe"

cat > "$BOOT" <<'SH'
#!/usr/bin/env bash
set -u
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
RUNTIME="$ROOT/eira_probe/transport_runtime_v5"
SUP="$RUNTIME/eira2_transport_v5.py"
NEXT="$SUP.next"
LOG="$ROOT/eira_probe/autonomous_transport_v5.log"
URL=https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_2.py
HB="$RUNTIME/heartbeat.json"
mkdir -p "$RUNTIME"
fetch(){ rm -f "$NEXT"; curl -fsSL "$URL" -o "$NEXT" 2>>"$LOG" || return 1; python3 -m py_compile "$NEXT" 2>>"$LOG" || return 1; mv -f "$NEXT" "$SUP"; chmod 700 "$SUP"; }
while true; do
  fetch || { printf '%s fetch_failed\n' "$(date -Is)" >>"$LOG"; sleep 3; continue; }
  rm -f "$HB"
  EIRA2_TRANSPORT_RUNTIME_V5="$RUNTIME" setsid python3 "$SUP" --root "$ROOT" --interval 2 >>"$LOG" 2>&1 &
  child=$!
  start=$(date +%s)
  while kill -0 "$child" 2>/dev/null; do
    now=$(date +%s)
    mt=$(stat -c %Y "$ROOT/eira_probe/transport_runtime_v2_3/heartbeat.json" 2>/dev/null || echo 0)
    if (( mt>0 && now-mt>90 )); then
      printf '%s stale_heartbeat restart=%s age=%s\n' "$(date -Is)" "$child" "$((now-mt))" >>"$LOG"
      kill -TERM -- "-$child" 2>/dev/null || true; sleep 2; kill -KILL -- "-$child" 2>/dev/null || true; break
    fi
    if (( mt==0 && now-start>120 )); then
      printf '%s missing_heartbeat restart=%s\n' "$(date -Is)" "$child" >>"$LOG"
      kill -TERM -- "-$child" 2>/dev/null || true; sleep 2; kill -KILL -- "-$child" 2>/dev/null || true; break
    fi
    sleep 3
  done
  wait "$child" 2>/dev/null || true
  sleep 2
done
SH
chmod 700 "$BOOT"

systemctl --user disable --now eira2-autonomous-transport.service >/dev/null 2>&1 || true
systemctl --user disable --now eira2-autonomous-transport-v4.service >/dev/null 2>&1 || true
systemctl --user disable --now eira2-autonomous-transport-v5.service >/dev/null 2>&1 || true
pkill -f 'transport_runtime_v2_3/eira2_transport_supervisor.py' 2>/dev/null || true
pkill -f 'transport_runtime_v4/eira2_transport_supervisor.py' 2>/dev/null || true
sleep 1

cat > "$SERVICE" <<EOF
[Unit]
Description=EIRA2 Clean Autonomous Transport V5
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
systemctl --user enable --now eira2-autonomous-transport-v5.service
loginctl enable-linger "$USER" >/dev/null 2>&1 || true
sleep 4
systemctl --user is-active --quiet eira2-autonomous-transport-v5.service
PID=$(systemctl --user show -p MainPID --value eira2-autonomous-transport-v5.service)
[[ -n "$PID" && "$PID" != 0 ]]
printf 'EIRA2_CLEAN_TRANSPORT_V5=PASS\n'
printf 'MODE=systemd-user\n'
printf 'PID=%s\n' "$PID"
printf 'DIRECT_SUPERVISOR=ENABLED\n'
printf 'HOME_EXPLICIT=ENABLED\n'
printf 'NONINTERACTIVE_GIT=ENABLED\n'
printf 'REQUEST_INBOX=eira2_transport_bus/to_superprobe/requests\n'
printf 'RETURN_OUTBOX=eira2_transport_bus/from_superprobe/receipts\n'
printf 'REBOOT_RECOVERY=ENABLED\n'
