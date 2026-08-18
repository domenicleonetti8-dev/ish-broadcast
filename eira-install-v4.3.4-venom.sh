#!/usr/bin/env bash
set -euo pipefail

VERSION='4.3.4'
REPO='domenicleonetti8-dev/ish-broadcast'
LIVE="${1:-/media/domenicleonetti/easystore/EIRA/LIVE}"
RUNTIME_SHA256='35bbba92ba788058cb563aa2955eb3b687e10919159e972863d62b701dbc48a1'
RUNTIME_SIZE='120600'
ROOT_NAME='eira_unified_brain_v4_3_4'
TMP="$(mktemp -d "${TMPDIR:-/tmp}/eira-v434-venom.XXXXXX")"
cleanup(){ rm -rf -- "$TMP"; }
trap cleanup EXIT INT TERM

[ -d "$LIVE" ] || { echo "EIRA V4.3.4 BLOCKED: LIVE not found: $LIVE" >&2; exit 1; }
[ -f "$LIVE/main.py" ] || { echo "EIRA V4.3.4 BLOCKED: main.py missing" >&2; exit 1; }
[ -f "$LIVE/extensions/local_brain/router.py" ] || { echo "EIRA V4.3.4 BLOCKED: LIVE local_brain router missing; Venom has no verified host binding point" >&2; exit 1; }

printf 'EIRA V4.3.4 VENOM: downloading pinned GitHub runtime objects...\n'
python3 - "$REPO" "$TMP" <<'PY'
from __future__ import annotations
import base64, hashlib, json, os, pathlib, sys, urllib.request
repo, tmp = sys.argv[1:3]
out = pathlib.Path(tmp)
parts = [
('d5e81f4bdaf2e8f3c96f2ca8e8719885ed319724',16000,'b12c3eba84cba14dfe7eae768351994487412b3ae65e57e5ffe4c8dd4d6ffda3'),
('fa87092a15ff4e04e15562a8f4615044f98b9b70',16000,'daa897fa6e0931b9b84b581699cc4d612ad1206dc959fcb04f6c7bc8194fce5e'),
('7212a27fa78245631f5aebb18db8bfcde619bf92',16000,'d18df2efa3fa0de13e78d946335a1bd2cebbeeac79e453c507bd5cbda8cb38e8'),
('3c2ebee2477d705623564687071cb2876d86f318',16000,'4ed10ce834d8a8ec0fb55b91629ea0fa02996bfd122c02adec37e0e5c5abe2ba'),
('61471ec47fdedec8249d6bdb93578f710c3427ef',16000,'f44648764fe4870eb7d8d3f3767957ce2d22df851fd12bacd1a3e158c62928f1'),
('9506f469f1429200af85efc56eb3952c34aa059a',16000,'cede3849e848da83f58cb4374b8d4c12332433d42efe6a3ea4c2573e5dcd8a89'),
('be18922ddb76eef2274d217ed96973e397b08b0f',16000,'3b48773ad4ad119e5d198f9362a0a49a06dab8ff09c73dcf84074e1a1d1bc7f0'),
('13b8091191ac15582867196d3bc5bd576f1b4e4e',16000,'9be4b45886a7e60d1d1c6cf5d416f2cbecb613473817e0f26a23fd215b098897'),
('4c19c2ec5371adf0db1ab7eab6a58f2ac9bac2d2',16000,'fe70a2675d6153f41ac94c9fe138cc8d97c3d0a0314cb8958bb3561c75ccebc6'),
('f376b48ef5de81b0db8b216a40480b8aa97c2345',16000,'b6f49ad308c2447fb245b1a62104783723015887467ef0fbeb366dec305cf430'),
('3ea83d0c1785ce60feaf2ad51826e8a90a5715d6',800,'33ce18ab0c426e8d4c84887b53d09c8f8707d37ea30ee4b3830c2cef00eda4af'),
]
local = os.environ.get('EIRA_V434_BLOB_DIR','').strip()
assembled = bytearray()
for idx,(blob_sha,size,want256) in enumerate(parts):
    if local:
        p=pathlib.Path(local)/f'runtime.b64.part{idx:02d}'
        data=p.read_bytes()
    else:
        url=f'https://api.github.com/repos/{repo}/git/blobs/{blob_sha}'
        req=urllib.request.Request(url,headers={
            'Accept':'application/vnd.github+json',
            'User-Agent':'Eira-v4.3.4-Venom-iSH-installer',
        })
        with urllib.request.urlopen(req,timeout=45) as r:
            obj=json.load(r)
        if obj.get('encoding')!='base64':
            raise SystemExit(f'blob {idx:02d}: unexpected API encoding')
        data=base64.b64decode(obj.get('content',''))
    if len(data)!=size:
        raise SystemExit(f'blob {idx:02d}: size mismatch {len(data)} != {size}')
    got256=hashlib.sha256(data).hexdigest()
    if got256!=want256:
        raise SystemExit(f'blob {idx:02d}: SHA-256 mismatch')
    git=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if git!=blob_sha:
        raise SystemExit(f'blob {idx:02d}: Git blob SHA mismatch')
    assembled.extend(data)
try:
    runtime=base64.b64decode(bytes(assembled),validate=True)
except Exception as exc:
    raise SystemExit(f'runtime Base64 invalid: {exc}')
path=out/'runtime.tar.xz'
path.write_bytes(runtime)
print(f'GITHUB_BLOBS_OK={len(parts)}/{len(parts)}')
PY

python3 - "$TMP/runtime.tar.xz" "$RUNTIME_SIZE" "$RUNTIME_SHA256" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1]); want_size=int(sys.argv[2]); want=sys.argv[3]
b=p.read_bytes()
if len(b)!=want_size: raise SystemExit(f'EIRA V4.3.4 BLOCKED: runtime size {len(b)} != {want_size}')
got=hashlib.sha256(b).hexdigest()
if got!=want: raise SystemExit(f'EIRA V4.3.4 BLOCKED: runtime SHA-256 {got} != {want}')
print('RUNTIME_TRANSPORT_SHA256=PASS')
PY

printf 'EIRA V4.3.4 VENOM: safely extracting runtime...\n'
python3 - "$TMP/runtime.tar.xz" "$TMP/extracted" "$ROOT_NAME" <<'PY'
from __future__ import annotations
import os, pathlib, shutil, sys, tarfile
src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2]); root_name=sys.argv[3]
dst.mkdir(parents=True,exist_ok=False)
base=dst.resolve()
with tarfile.open(src,'r:xz') as tf:
    members=tf.getmembers()
    if not members: raise SystemExit('empty runtime archive')
    for m in members:
        pp=pathlib.PurePosixPath(m.name)
        if pp.is_absolute() or '..' in pp.parts or not pp.parts or pp.parts[0]!=root_name:
            raise SystemExit(f'unsafe archive path: {m.name!r}')
        if not (m.isdir() or m.isfile()):
            raise SystemExit(f'archive special/link entry rejected: {m.name!r}')
        target=(base/pathlib.Path(*pp.parts)).resolve()
        if target!=base and base not in target.parents:
            raise SystemExit(f'archive path escapes root: {m.name!r}')
        if m.isdir():
            target.mkdir(parents=True,exist_ok=True)
            os.chmod(target,0o755)
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists(): raise SystemExit(f'duplicate archive file: {m.name!r}')
        f=tf.extractfile(m)
        if f is None: raise SystemExit(f'cannot read archive file: {m.name!r}')
        with target.open('xb') as out:
            shutil.copyfileobj(f,out)
            out.flush(); os.fsync(out.fileno())
        os.chmod(target,0o755 if (m.mode & 0o111) else 0o644)
print('SAFE_EXTRACTION=PASS')
PY

ROOT="$TMP/extracted/$ROOT_NAME"
[ -d "$ROOT" ] || { echo 'EIRA V4.3.4 BLOCKED: extracted runtime root missing' >&2; exit 1; }

printf 'EIRA V4.3.4 VENOM: verifying 141-file internal runtime manifest...\n'
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/verify_internal_hashes.py"

printf 'EIRA V4.3.4 VENOM: binding LIVE host to Unified Brain transactionally...\n'
PYTHONDONTWRITEBYTECODE=1 bash "$ROOT/deploy/install_pi_extension.sh" "$LIVE"

ROUTER="$LIVE/extensions/local_brain/router.py"
grep -Fq '# === EIRA_VENOM_BIND_V4_3_4_BEGIN ===' "$ROUTER" || {
  echo 'EIRA V4.3.4 BLOCKED: install returned but Venom bind marker is absent' >&2; exit 1;
}
grep -Fq '# === EIRA_VENOM_BIND_V4_3_4_END ===' "$ROUTER" || {
  echo 'EIRA V4.3.4 BLOCKED: Venom bind is incomplete' >&2; exit 1;
}

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/deploy/discover_live_integration.py" "$LIVE" || {
  echo 'EIRA V4.3.4 BLOCKED: post-bind LIVE discovery failed' >&2; exit 1;
}

printf 'EIRA_V4_3_4_GITHUB_INSTALL=PASS\n'
printf 'VENOM_BIND=PASS\n'
printf 'LIVE=%s\n' "$LIVE"
printf 'MAIN_NOT_STARTED=true\n'
