#!/bin/sh
set -eu

PREFIX="${PREFIX:-/usr/local}"
BINDIR="$PREFIX/bin"
CONFIG_DIR="$HOME/.config/eira"
CONFIG="$CONFIG_DIR/ish-bridge.conf"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v ssh >/dev/null 2>&1; then
    if command -v apk >/dev/null 2>&1; then
        apk add --no-cache openssh-client
    else
        printf '%s\n' "ssh is required" >&2
        exit 1
    fi
fi

mkdir -p "$BINDIR" "$CONFIG_DIR"
install -m 0755 "$SCRIPT_DIR/eira" "$BINDIR/eira"

if [ ! -f "$CONFIG" ]; then
    umask 077
    cat > "$CONFIG" <<'EOF'
# Eira iSH message bridge. No password or private key is stored here.
EIRA_SSH_TARGET=""
EIRA_SSH_PORT="22"
EOF
fi

printf '%s\n' "EIRA_ISH_BRIDGE=INSTALLED"
printf '%s\n' "Configure: $CONFIG"
printf '%s\n' "Verify:    eira --check"
printf '%s\n' "Connect:   eira"
