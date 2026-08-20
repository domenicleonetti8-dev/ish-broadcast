#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/bin" "$TMP/home/.config/eira"

cat > "$TMP/bin/ssh" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > "$EIRA_MOCK_ARGS"
EOF
chmod +x "$TMP/bin/ssh"

cat > "$TMP/home/.config/eira/ish-bridge.conf" <<'EOF'
EIRA_SSH_TARGET="testuser@testhost"
EIRA_SSH_PORT="2222"
EOF

export HOME="$TMP/home"
export PATH="$TMP/bin:$PATH"
export EIRA_MOCK_ARGS="$TMP/args"

sh -n "$ROOT/eira"
sh -n "$ROOT/install.sh"
sh -n "$ROOT/bootstrap.sh"

"$ROOT/eira" --check
grep -qx -- '-T' "$TMP/args"
grep -qx -- '2222' "$TMP/args"
grep -qx -- 'testuser@testhost' "$TMP/args"
grep -q -- 'python3 -m py_compile main.py' "$TMP/args"

"$ROOT/eira" --connect
grep -qx -- '-tt' "$TMP/args"
grep -q -- 'exec python3 main.py' "$TMP/args"

rm -f "$HOME/.config/eira/ish-bridge.conf"
if "$ROOT/eira" --check >/dev/null 2>&1; then
    echo 'missing-config test unexpectedly passed' >&2
    exit 1
fi

mkdir -p "$TMP/install-home"
HOME="$TMP/install-home" PREFIX="$TMP/prefix" "$ROOT/install.sh" >/dev/null
test -x "$TMP/prefix/bin/eira"
test -f "$TMP/install-home/.config/eira/ish-bridge.conf"
grep -q 'EIRA_SSH_TARGET=""' "$TMP/install-home/.config/eira/ish-bridge.conf"

printf '%s\n' 'EIRA_ISH_BRIDGE_MOCK_TESTS=PASS'
