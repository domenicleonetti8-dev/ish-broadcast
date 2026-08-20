#!/bin/sh
set -eu

EIRA_HOST="${EIRA_HOST:-100.107.25.56}"
EIRA_USER="${EIRA_USER:-root}"
EIRA_DIR="${EIRA_DIR:-/media/domenicleonetti/easystore/EIRA/LIVE}"

if ! command -v ssh >/dev/null 2>&1; then
    if command -v apk >/dev/null 2>&1; then
        apk add --no-cache openssh-client
    else
        echo "ssh is required" >&2
        exit 1
    fi
fi

mkdir -p "$HOME/bin"

cat > "$HOME/bin/eira" <<EOF
#!/bin/sh
set -eu
exec ssh -tt \
  -o ServerAliveInterval=20 \
  -o ServerAliveCountMax=3 \
  ${EIRA_USER}@${EIRA_HOST} \
  "cd '${EIRA_DIR}' && exec python3 main.py"
EOF
chmod +x "$HOME/bin/eira"

cat > "$HOME/bin/eira-check" <<EOF
#!/bin/sh
set -eu
exec ssh \
  -o ConnectTimeout=8 \
  -o ServerAliveInterval=20 \
  ${EIRA_USER}@${EIRA_HOST} \
  "cd '${EIRA_DIR}' && printf 'EIRA_ISH_MESSAGE_BRIDGE=READY\\n'"
EOF
chmod +x "$HOME/bin/eira-check"

PROFILE="$HOME/.profile"
touch "$PROFILE"
if ! grep -F 'export PATH="$HOME/bin:$PATH"' "$PROFILE" >/dev/null 2>&1; then
    printf '\nexport PATH="$HOME/bin:$PATH"\n' >> "$PROFILE"
fi

printf '\nEIRA_ISH_MESSAGE_BRIDGE=INSTALLED\n'
printf 'Connection: %s@%s\n' "$EIRA_USER" "$EIRA_HOST"
printf 'Remote Eira: %s/main.py\n' "$EIRA_DIR"
printf '\nRun:  . ~/.profile\nThen: eira-check\nThen: eira\n'
printf '\nInside Eira, use the normal iPhone keyboard Dictation button. iOS owns the microphone; dictated text is delivered as ordinary terminal input to python3 main.py.\n'
