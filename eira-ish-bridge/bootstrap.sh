#!/bin/sh
set -eu

REPO="https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast"
REF="${EIRA_BRIDGE_REF:-eira-ish-dictation-bridge-final}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fetch() {
    src="$1"; dst="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$src" -o "$dst"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$dst" "$src"
    else
        printf '%s\n' "curl or wget is required" >&2
        exit 1
    fi
}

BASE="$REPO/$REF/eira-ish-bridge"
fetch "$BASE/eira" "$TMP/eira"
fetch "$BASE/install.sh" "$TMP/install.sh"
chmod 0755 "$TMP/eira" "$TMP/install.sh"
"$TMP/install.sh"
