#!/usr/bin/env bash
set -euo pipefail
umask 077
export LC_ALL=C

LIVE="${1:-/media/domenicleonetti/easystore/EIRA/LIVE}"
REPO="domenicleonetti8-dev/ish-broadcast"
PAYLOAD_COMMIT="db10620337bbb45597f657b74adcb4060fa524f3"
PAYLOAD_PATH="eira-release/v4.3.3"
RUNTIME_SHA256="3167bb16215c018ffacd87f6b035eec1a794d7b4df9bc6e92f18c56c499173a6"

fail() {
    printf 'EIRA INSTALL: %s\n' "$*" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v bash >/dev/null 2>&1 || fail "bash is required"
command -v mktemp >/dev/null 2>&1 || fail "mktemp is required"

[ -d "$LIVE" ] || fail "LIVE directory not found: $LIVE"
[ -f "$LIVE/main.py" ] || fail "protected LIVE main.py not found: $LIVE/main.py"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/eira-v433.XXXXXX")"
cleanup() {
    rm -rf -- "$TMP"
}
trap cleanup EXIT HUP INT TERM

printf 'EIRA v4.3.3: downloading pinned verified runtime...\n'
python3 - "$TMP" "$REPO" "$PAYLOAD_COMMIT" "$PAYLOAD_PATH" "$RUNTIME_SHA256" <<'PY'
import base64
import hashlib
import pathlib
import sys
import tarfile
import urllib.request

work = pathlib.Path(sys.argv[1])
repo = sys.argv[2]
commit = sys.argv[3]
payload_path = sys.argv[4]
expected_runtime = sys.argv[5]

parts = [
    ("runtime.b64.part00", "82e837c31de8be39c7a9fed663d6ee08c2d7e4bae616c0ff1e96baf986cf33dc"),
    ("runtime.b64.part01", "7f83a0cff4ba2e151af101d9ad638a9bede4ea23b82670260f493804c7731cce"),
    ("runtime.b64.part02", "9084051db057d8859c3859c8eb996e60901c9441eccea68dae0c8ecde3eddb1e"),
    ("runtime.b64.part03", "e0c2a9bbc0d98112eab21cff862fd4139f093976025dfe6e89bb0ef017aa720f"),
    ("runtime.b64.part04", "67ce0566592ebc0bfbad85e82c406f230544bfe251f15bced15ceb2a552edd02"),
    ("runtime.b64.part05", "64a026fcadf0b2b91859fd93c2ec9f8bdbb856b9f68dc88439eb805cda1ac04c"),
    ("runtime.b64.part06", "8319fb3f2be9ff365483da116d3395d74efce0e64d59f56edc442b0b7b8bf89a"),
    ("runtime.b64.part07", "41199ea7b65d9fa7c51878115c58bed4b98ac193c6a22a4a47a195fcaf49d4a3"),
    ("runtime.b64.part08", "b9af89c7af768f304d3cc9733b240ce872f361edf46980ae9a937669c94473d8"),
    ("runtime.b64.part09", "b71fd3636b25a75a17ac5907fae23186a0f44660926c589fa29e68ad4607e14f"),
]

base = f"https://raw.githubusercontent.com/{repo}/{commit}/{payload_path}"
encoded_parts = []
for name, expected in parts:
    url = f"{base}/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": "Eira-v4.3.3-installer"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = response.read(20001)
    except Exception as exc:
        raise SystemExit(f"EIRA INSTALL: download failed for {name}: {exc}")
    if len(data) > 20000:
        raise SystemExit(f"EIRA INSTALL: oversized payload part rejected: {name}")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise SystemExit(
            f"EIRA INSTALL: SHA-256 mismatch for {name}: expected {expected}, got {actual}"
        )
    encoded_parts.append(data)

try:
    runtime = base64.b64decode(b"".join(encoded_parts), validate=True)
except Exception as exc:
    raise SystemExit(f"EIRA INSTALL: invalid encoded runtime: {exc}")

actual_runtime = hashlib.sha256(runtime).hexdigest()
if actual_runtime != expected_runtime:
    raise SystemExit(
        f"EIRA INSTALL: runtime SHA-256 mismatch: expected {expected_runtime}, got {actual_runtime}"
    )

archive = work / "eira_v4_3_3_pi_runtime_hardened.tar.xz"
archive.write_bytes(runtime)
extract = work / "extract"
extract.mkdir(mode=0o700)
required_root = "eira_unified_brain_v4_3_3"

with tarfile.open(archive, "r:xz") as tf:
    members = tf.getmembers()
    if not members or len(members) > 500:
        raise SystemExit("EIRA INSTALL: runtime archive member count rejected")
    total = 0
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or path.parts[0] != required_root
        ):
            raise SystemExit(f"EIRA INSTALL: unsafe archive path rejected: {member.name!r}")
        if not (member.isdir() or member.isfile()):
            raise SystemExit(f"EIRA INSTALL: unsafe archive member rejected: {member.name!r}")
        if member.mode & 0o6000:
            raise SystemExit(f"EIRA INSTALL: privileged archive mode rejected: {member.name!r}")
        if member.isfile():
            total += member.size
    if total > 50 * 1024 * 1024:
        raise SystemExit("EIRA INSTALL: runtime archive expansion limit exceeded")
    tf.extractall(extract, members=members)

print(f"EIRA v4.3.3: pinned runtime verified: {actual_runtime}")
PY

ROOT="$TMP/extract/eira_unified_brain_v4_3_3"
[ -f "$ROOT/scripts/verify_internal_hashes.py" ] || fail "runtime verifier missing"
[ -f "$ROOT/deploy/install_pi_extension.sh" ] || fail "hardened deployer missing"
[ -f "$ROOT/deploy/discover_live_integration.py" ] || fail "integration discovery missing"

printf 'EIRA v4.3.3: verifying internal runtime manifest...\n'
python3 "$ROOT/scripts/verify_internal_hashes.py"

printf 'EIRA v4.3.3: transactional install into %s...\n' "$LIVE"
bash "$ROOT/deploy/install_pi_extension.sh" "$LIVE"

printf 'EIRA v4.3.3: read-only integration discovery...\n'
python3 "$ROOT/deploy/discover_live_integration.py" "$LIVE"

printf 'EIRA v4.3.3: VERIFIED INSTALL COMPLETE\n'
printf 'LIVE: %s\n' "$LIVE"
