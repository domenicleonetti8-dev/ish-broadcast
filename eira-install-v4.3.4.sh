#!/usr/bin/env bash
set -euo pipefail
umask 077
export LC_ALL=C

LIVE="${1:-/media/domenicleonetti/easystore/EIRA/LIVE}"
REPO="domenicleonetti8-dev/ish-broadcast"
PAYLOAD_COMMIT="073f07b577d26d09e9b7aeff8ca5ff486d58c920"
PAYLOAD_PATH="eira-release/v4.3.4"
RUNTIME_SHA256="01bd1ae05d1ecd57d77467016b3bc75372c1e5aec3bdc00714e9c42c30ea84a8"
RUNTIME_SIZE="120108"

fail() { printf 'EIRA V4.3.4 INSTALL: %s\n' "$*" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v bash >/dev/null 2>&1 || fail "bash is required"
command -v mktemp >/dev/null 2>&1 || fail "mktemp is required"
[ -d "$LIVE" ] || fail "LIVE directory not found: $LIVE"
[ -f "$LIVE/main.py" ] || fail "protected LIVE main.py not found: $LIVE/main.py"
[ -f "$LIVE/extensions/local_brain/router.py" ] || fail "LIVE local brain router not found"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/eira-v434.XXXXXX")"
cleanup(){ rm -rf -- "$TMP"; }
trap cleanup EXIT HUP INT TERM

printf 'EIRA v4.3.4 VENOM: downloading immutable verified runtime...\n'
python3 - "$TMP" "$REPO" "$PAYLOAD_COMMIT" "$PAYLOAD_PATH" "$RUNTIME_SHA256" "$RUNTIME_SIZE" <<'PY'
import base64, hashlib, os, pathlib, shutil, sys, tarfile, urllib.request
work=pathlib.Path(sys.argv[1]); repo=sys.argv[2]; commit=sys.argv[3]; payload=sys.argv[4]
expected_runtime=sys.argv[5]; expected_size=int(sys.argv[6])
parts=[
('runtime.b64.part00',16000,'abadd43f9a0c4a6d0ad713d8ec5029bc7407a04482882e9b293012f0b5efae2a'),
('runtime.b64.part01',16000,'fe6b2e1dfa75c83356dbd99c4e292ea052b0904304220d1e3f8009f3dc251072'),
('runtime.b64.part02',16000,'6915493b54144eb6fd8fcdc5d6df6d4afd0cae73eff43ae435f409e0e96b1f8d'),
('runtime.b64.part03',16000,'574ec631c8caaff74a88fc11adf6b1984a77a13ba987dda2ebae180e3be0c3dc'),
('runtime.b64.part04',16000,'345c7e87c8eeed888e6552045e3eabcc15ee90a611c104a272862a75cf85eb5a'),
('runtime.b64.part05',16000,'cce68abefcd2e171aebed487ed332382e82b91fbfb5b3b29c9a960a3bc65e850'),
('runtime.b64.part06',16000,'7691347cf0537927039afefb3671cb50959d2c7771c78e670278659b6e701bb2'),
('runtime.b64.part07',16000,'2500518326301d218166cb6a32779c15ab34d0fc9e4fd36faccc06a69d0d35a0'),
('runtime.b64.part08',16000,'8331eaa42254ce8cdee962a1385b2cb83109c6bec43877d87a95c5ece659ef11'),
('runtime.b64.part09',16000,'14195638ae49715202f30a1ba3426eba9b8305402e0035d7d94fefeee6de58d1'),
('runtime.b64.part10',144,'660b97266d1875c6e3a2a541750a1b7cc791741a6fac30087a50580af5aa4839')]
base=f'https://raw.githubusercontent.com/{repo}/{commit}/{payload}'
encoded=[]
for name,size,sha in parts:
    req=urllib.request.Request(f'{base}/{name}',headers={'User-Agent':'Eira-Venom-v4.3.4-installer'})
    try:
        with urllib.request.urlopen(req,timeout=45) as r: data=r.read(size+1)
    except Exception as exc: raise SystemExit(f'EIRA V4.3.4 INSTALL: download failed for {name}: {exc}')
    if len(data)!=size: raise SystemExit(f'EIRA V4.3.4 INSTALL: size mismatch for {name}: {len(data)} != {size}')
    actual=hashlib.sha256(data).hexdigest()
    if actual!=sha: raise SystemExit(f'EIRA V4.3.4 INSTALL: SHA-256 mismatch for {name}')
    encoded.append(data)
try: runtime=base64.b64decode(b''.join(encoded),validate=True)
except Exception as exc: raise SystemExit(f'EIRA V4.3.4 INSTALL: invalid runtime encoding: {exc}')
if len(runtime)!=expected_size: raise SystemExit(f'EIRA V4.3.4 INSTALL: runtime size mismatch: {len(runtime)} != {expected_size}')
actual=hashlib.sha256(runtime).hexdigest()
if actual!=expected_runtime: raise SystemExit(f'EIRA V4.3.4 INSTALL: runtime SHA-256 mismatch: {actual}')
archive=work/'runtime.tar.xz'; archive.write_bytes(runtime)
root_name='eira_unified_brain_v4_3_4'; extract=work/'extract'; extract.mkdir(mode=0o700)
with tarfile.open(archive,'r:xz') as tf:
    members=tf.getmembers()
    if not members or len(members)>500: raise SystemExit('EIRA V4.3.4 INSTALL: archive member count rejected')
    total=0
    checked=[]
    for m in members:
        p=pathlib.PurePosixPath(m.name)
        if p.is_absolute() or not p.parts or '..' in p.parts or p.parts[0]!=root_name:
            raise SystemExit(f'EIRA V4.3.4 INSTALL: unsafe archive path rejected: {m.name!r}')
        if not (m.isdir() or m.isfile()): raise SystemExit(f'EIRA V4.3.4 INSTALL: unsafe archive member rejected: {m.name!r}')
        if m.isfile():
            if m.mode & 0o7000: raise SystemExit(f'EIRA V4.3.4 INSTALL: privileged file mode rejected: {m.name!r}')
            total += m.size
            if total > 64*1024*1024: raise SystemExit('EIRA V4.3.4 INSTALL: archive expansion limit exceeded')
        checked.append((m,p))
    for m,p in checked:
        target=extract.joinpath(*p.parts)
        if m.isdir():
            target.mkdir(parents=True,exist_ok=True); os.chmod(target,0o755); continue
        target.parent.mkdir(parents=True,exist_ok=True)
        src=tf.extractfile(m)
        if src is None: raise SystemExit(f'EIRA V4.3.4 INSTALL: unreadable archive file: {m.name!r}')
        with src, target.open('xb') as out: shutil.copyfileobj(src,out,1024*1024)
        os.chmod(target,0o755 if (m.mode & 0o111) else 0o644)
print(f'EIRA v4.3.4 VENOM: pinned runtime verified: {actual}')
PY

ROOT="$TMP/extract/eira_unified_brain_v4_3_4"
[ -f "$ROOT/scripts/verify_internal_hashes.py" ] || fail "internal verifier missing"
[ -f "$ROOT/deploy/install_pi_extension.sh" ] || fail "transactional deployer missing"
[ -f "$ROOT/deploy/venom_bind_live.py" ] || fail "Venom LIVE binder missing"

printf 'EIRA v4.3.4 VENOM: verifying 141-file runtime manifest...\n'
python3 "$ROOT/scripts/verify_internal_hashes.py"
printf 'EIRA v4.3.4 VENOM: binding LIVE to Unified Brain transactionally...\n'
bash "$ROOT/deploy/install_pi_extension.sh" "$LIVE"
printf 'EIRA v4.3.4 VENOM: read-only post-bind discovery...\n'
PYTHONPATH="$LIVE" python3 "$ROOT/deploy/discover_live_integration.py" "$LIVE" || printf 'EIRA v4.3.4 VENOM: discovery warning; install receipt remains authoritative.\n' >&2
printf 'EIRA_V4_3_4_VENOM_INSTALL=PASS\nLIVE=%s\nMAIN_NOT_STARTED=true\n' "$LIVE"
