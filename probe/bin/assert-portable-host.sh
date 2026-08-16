#!/bin/sh
set -eu

broadcast_hostname=${BROADCAST_HOSTNAME:-$(hostname -s 2>/dev/null || hostname)}
broadcast_hostname=$(printf '%s' "$broadcast_hostname" | tr '[:upper:]' '[:lower:]')

case "$broadcast_hostname" in
    eira|eira.*)
        echo "broadcast: refusing to use Eira's home host as the physical Bluetooth endpoint" >&2
        echo "broadcast: install on the dedicated portable broadcaster kept near the phone and speakers" >&2
        exit 78
        ;;
esac

exit 0
