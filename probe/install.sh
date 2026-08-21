#!/bin/sh
set -eu

broadcast_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
broadcast_destdir=
broadcast_user=${SUDO_USER:-}
broadcast_input_controller=
broadcast_install_packages=yes
broadcast_enable_services=yes
broadcast_dry_run=no
broadcast_portable_confirmed=no

usage() {
    echo "usage: $0 [--portable] [--user USER] [--input-controller MAC] [--destdir PATH] [--no-packages] [--no-enable] [--dry-run]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --user)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            broadcast_user=$2
            shift 2
            ;;
        --input-controller)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            broadcast_input_controller=$(printf '%s' "$2" | tr '[:lower:]-' '[:upper:]:' )
            shift 2
            ;;
        --destdir)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            broadcast_destdir=$2
            broadcast_install_packages=no
            broadcast_enable_services=no
            shift 2
            ;;
        --no-packages)
            broadcast_install_packages=no
            shift
            ;;
        --no-enable)
            broadcast_enable_services=no
            shift
            ;;
        --dry-run)
            broadcast_dry_run=yes
            shift
            ;;
        --portable)
            broadcast_portable_confirmed=yes
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ -z "$broadcast_user" ] || [ "$broadcast_user" = root ]; then
    if [ -n "$broadcast_destdir" ]; then
        broadcast_user=broadcast
    else
        broadcast_user=$(getent passwd 1000 | cut -d: -f1 || true)
    fi
fi

case "$broadcast_user" in
    ''|*[!A-Za-z0-9_.-]*)
        echo "a valid non-root probe user is required; pass --user USER" >&2
        exit 2
        ;;
esac

if [ -n "$broadcast_input_controller" ]; then
    broadcast_mac_pattern='^[0-9A-F][0-9A-F]\(:[0-9A-F][0-9A-F]\)\{5\}$'
    printf '%s\n' "$broadcast_input_controller" | grep -q "$broadcast_mac_pattern" || {
        echo "invalid input controller address" >&2
        exit 2
    }
fi

if [ -z "$broadcast_destdir" ] && [ "$(id -u)" -ne 0 ]; then
    echo "run this installer as root (sudo)" >&2
    exit 1
fi

if [ -z "$broadcast_destdir" ]; then
    if [ "$broadcast_portable_confirmed" != yes ]; then
        echo "refusing live install: pass --portable on the dedicated broadcaster that travels with the phone and speakers" >&2
        exit 2
    fi
    "$broadcast_script_dir/bin/assert-portable-host.sh"
fi

if [ -n "$broadcast_destdir" ]; then
    case "$broadcast_destdir" in
        /*) ;;
        *) echo "--destdir must be absolute" >&2; exit 2 ;;
    esac
fi

if [ -n "${BROADCAST_PROBE_HOME:-}" ]; then
    broadcast_home=$BROADCAST_PROBE_HOME
elif [ -n "$broadcast_destdir" ]; then
    broadcast_home="/home/$broadcast_user"
else
    broadcast_home=$(getent passwd "$broadcast_user" | cut -d: -f6 || true)
fi

case "$broadcast_home" in
    /*) ;;
    *) echo "cannot resolve home directory for $broadcast_user" >&2; exit 2 ;;
esac

echo "Broadcast probe install"
echo "  endpoint: broadcast"
echo "  service user: $broadcast_user"
echo "  home: $broadcast_home"
echo "  input controller: ${broadcast_input_controller:-auto-detect}"
echo "  destination root: ${broadcast_destdir:-/}"

if [ "$broadcast_dry_run" = yes ]; then
    exit 0
fi

if [ "$broadcast_install_packages" = yes ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
        bluez \
        pipewire \
        pipewire-audio \
        pipewire-pulse \
        wireplumber \
        libspa-0.2-bluetooth \
        python3 \
        python3-dbus \
        python3-gi
fi

broadcast_lib="$broadcast_destdir/usr/local/lib/broadcast-probe"
broadcast_bin="$broadcast_destdir/usr/local/bin"
broadcast_etc="$broadcast_destdir/etc/broadcast-probe"
broadcast_system_units="$broadcast_destdir/etc/systemd/system"
broadcast_user_units="$broadcast_destdir/etc/systemd/user"
broadcast_user_config="$broadcast_destdir$broadcast_home/.config/wireplumber"

install -d -m 0755 \
    "$broadcast_lib" \
    "$broadcast_bin" \
    "$broadcast_etc" \
    "$broadcast_system_units" \
    "$broadcast_user_units" \
    "$broadcast_user_config/wireplumber.conf.d" \
    "$broadcast_user_config/bluetooth.lua.d"

install -m 0644 "$broadcast_script_dir/broadcast_common.py" "$broadcast_lib/broadcast_common.py"
install -m 0755 "$broadcast_script_dir/broadcast_bluez.py" "$broadcast_lib/broadcast_bluez.py"
install -m 0755 "$broadcast_script_dir/broadcast_probe.py" "$broadcast_lib/broadcast_probe.py"
install -m 0755 "$broadcast_script_dir/bin/assert-portable-host.sh" "$broadcast_lib/assert-portable-host.sh"
install -m 0755 "$broadcast_script_dir/bin/prepare-controller-class.sh" "$broadcast_lib/prepare-controller-class.sh"
install -m 0755 "$broadcast_script_dir/bin/pair-speaker.sh" "$broadcast_bin/broadcast-pair-speaker"
install -m 0755 "$broadcast_script_dir/bin/broadcast-status.sh" "$broadcast_bin/broadcast-status"
install -m 0644 "$broadcast_script_dir/systemd/broadcast-bluetooth.service" "$broadcast_system_units/broadcast-bluetooth.service"
install -m 0644 "$broadcast_script_dir/systemd/broadcast-probe.service" "$broadcast_user_units/broadcast-probe.service"
install -m 0644 "$broadcast_script_dir/config/wireplumber-0.5.conf" "$broadcast_user_config/wireplumber.conf.d/90-broadcast.conf"
install -m 0644 "$broadcast_script_dir/config/wireplumber-0.4.lua" "$broadcast_user_config/bluetooth.lua.d/90-broadcast.lua"

if [ ! -e "$broadcast_etc/config.json" ]; then
    install -m 0644 "$broadcast_script_dir/config/broadcast-probe.json" "$broadcast_etc/config.json"
fi

if [ -n "$broadcast_input_controller" ]; then
    python3 - "$broadcast_etc/config.json" "$broadcast_input_controller" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
value["input_controller"] = sys.argv[2]
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o644)
os.replace(temporary, path)
PY
fi

if [ -z "$broadcast_destdir" ]; then
    broadcast_group=$(id -gn "$broadcast_user")
    chown "$broadcast_user:$broadcast_group" \
        "$broadcast_user_config/wireplumber.conf.d/90-broadcast.conf" \
        "$broadcast_user_config/bluetooth.lua.d/90-broadcast.lua"
    chown -R "$broadcast_user:$broadcast_group" "$broadcast_user_config/wireplumber.conf.d" "$broadcast_user_config/bluetooth.lua.d"
fi

if [ "$broadcast_enable_services" = yes ]; then
    systemctl daemon-reload
    systemctl enable --now bluetooth.service
    systemctl enable --now broadcast-bluetooth.service

    broadcast_uid=$(id -u "$broadcast_user")
    loginctl enable-linger "$broadcast_user"
    systemctl start "user@$broadcast_uid.service"

    broadcast_user_systemctl() {
        runuser -u "$broadcast_user" -- env \
            XDG_RUNTIME_DIR="/run/user/$broadcast_uid" \
            DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$broadcast_uid/bus" \
            systemctl --user "$@"
    }

    broadcast_user_systemctl daemon-reload
    for broadcast_unit in pipewire.socket pipewire-pulse.socket wireplumber.service; do
        broadcast_user_systemctl enable "$broadcast_unit" >/dev/null 2>&1 || true
        broadcast_user_systemctl restart "$broadcast_unit"
    done
    broadcast_user_systemctl enable --now broadcast-probe.service
fi

echo "Broadcast probe installed. Status command: broadcast-status"
