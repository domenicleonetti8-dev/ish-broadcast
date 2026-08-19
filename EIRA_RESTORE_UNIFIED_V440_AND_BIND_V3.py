#!/usr/bin/env python3
from __future__ import annotations

import base64
import compileall
import hashlib
import importlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

DEFAULT_LIVE = Path('/media/domenicleonetti/easystore/EIRA/LIVE')
REPO = 'domenicleonetti8-dev/ish-broadcast'
PAYLOAD_COMMIT = '997129230136d4cb224341cd79f5dcb52832f209'
BINDER_COMMIT = '1ae507da346468d06373efbbee599418609a24a8'
ARCHIVE_SHA256 = 'ce0e1b58275d58d9281fcbac8c53f25117587a4d0132bb67393d0c61b507df27'

PARTS = [
    ('chunk00', 20000, '70ed20bde914df4b7f0afedcc1b78bb4d0999e2991b5b2eee3dc02d5a80aa1cb'),
    ('chunk01', 20000, '7383e95c5c8d640686fbd7ef43dc2276418c27c9f3d62fc78399cb2cbf9920b6'),
    ('chunk02', 20000, '6fe65041a373044cf585c5b64325d21aa0f1a26981fb0d5472186b488f359b0e'),
    ('chunk03', 20000, '29e181f170f560c86737cbb8b944f6c9b2e9f4bf07b893d29d29cc2d712653b3'),
    ('chunk04', 20000, 'd8c4372a20d57fecbfc924bc8e07194780d8b77250fedd2d8d4cc753e1a6d360'),
    ('chunk05', 20000, 'd8e5e57caac831e59db38e4e7357935f3fcf8cd55d9b36171e0b9d21fbcda6bf'),
    ('chunk06a', 5000, '23dccfe4fb59ffdb42128febae84f6c41a373cb4f2c0d7951c3615563d88add4'),
    ('chunk06b', 5000, 'f76ee0f923a10e404b733ec8576f8d238c45414aebd42b34889d07394b41d43f'),
    ('chunk06c', 5000, 'e838b62b7f51d97d3af4622e3c4bb76c8aef183ae206b56333fd030f502c6fa5'),
    ('chunk06d', 5000, '5f8956d5d74d2b324a39ad536534ab0abf4755778b2f4027d43e72f695d67bf7'),
    ('chunk07a', 5000, '13ba16face0ea66ba4507c840a51b8d61e443846d3253c131a11638467956b84'),
    ('chunk07b', 5000, '504a7b366c1649f2eaad5137bf12d933a15e6b6c6a03417a4b75fcb90443dbac'),
    ('chunk07c', 3856, 'cb3cc591d0e280558a7cc4ac0c1f8f1bc929fad1b982c9e39478a78feffb5dc7'),
]


def fail(message: str, code: int = 1) -> None:
    print(f'EIRA UNIFIED RESTORE V3: {message}')
    raise SystemExit(code)


def download(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'Eira-v4.4.0-recovery'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def safe_extract(tf: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    members = tf.getmembers()
    for member in members:
        p = PurePosixPath(member.name)
        if p.is_absolute() or '..' in p.parts:
            fail(f'unsafe archive path: {member.name}')
        if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
            fail(f'unsupported archive member: {member.name}')
        resolved = (root / Path(*p.parts)).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            fail(f'archive path escaped staging root: {member.name}')
    tf.extractall(root, members=members)


def main() -> None:
    live = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else DEFAULT_LIVE
    required = [
        live / 'main.py',
        live / 'extensions/omnivenom_mesh_ai/runtime.py',
        live / 'extensions/local_brain/router.py',
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        fail('required existing LIVE component missing: ' + ', '.join(missing))

    print('[1/5] Downloading checksum-sealed Unified Brain v4.4.0')
    encoded_parts: list[bytes] = []
    base = f'https://raw.githubusercontent.com/{REPO}/{PAYLOAD_COMMIT}/_unified_v440_recovery'
    for name, expected_len, expected_sha in PARTS:
        try:
            data = download(f'{base}/{name}')
        except Exception as exc:
            fail(f'download failed for {name}: {type(exc).__name__}: {exc}')
        actual_sha = hashlib.sha256(data).hexdigest()
        if len(data) != expected_len:
            fail(f'{name} length mismatch: {len(data)} != {expected_len}')
        if actual_sha != expected_sha:
            fail(f'{name} checksum mismatch')
        encoded_parts.append(data)

    encoded = b''.join(encoded_parts)
    if len(encoded) != 153856:
        fail(f'joined payload length mismatch: {len(encoded)} != 153856')
    try:
        archive = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        fail(f'base64 decode failed: {type(exc).__name__}: {exc}')
    actual_archive_sha = hashlib.sha256(archive).hexdigest()
    if actual_archive_sha != ARCHIVE_SHA256:
        fail(f'archive checksum mismatch: {actual_archive_sha}')
    if not archive.startswith(b'\xfd7zXZ\x00'):
        fail('decoded payload is not an XZ archive')
    print(f'PAYLOAD_SHA256={actual_archive_sha}')

    print('[2/5] Verifying and extracting')
    with tempfile.TemporaryDirectory(prefix='eira_v440_restore_') as td:
        stage = Path(td)
        archive_path = stage / 'unified_brain_v440.tar.xz'
        archive_path.write_bytes(archive)
        extract_root = stage / 'extract'
        extract_root.mkdir()
        try:
            with tarfile.open(archive_path, mode='r:xz') as tf:
                safe_extract(tf, extract_root)
        except SystemExit:
            raise
        except Exception as exc:
            fail(f'archive extraction failed: {type(exc).__name__}: {exc}')

        source = extract_root / 'extensions/unified_brain_ai'
        if not (source / 'plugin.py').is_file() or not (source / 'manifest.json').is_file():
            fail('verified archive does not contain extensions/unified_brain_ai')
        if not compileall.compile_dir(str(source), quiet=1):
            fail('Unified Brain Python compile check failed before install')

        print('[3/5] Installing Unified Brain')
        target = live / 'extensions/unified_brain_ai'
        backup = None
        if target.exists():
            stamp = time.strftime('%Y%m%d_%H%M%S')
            backup = target.with_name(f'unified_brain_ai.bak_before_v440_restore_{stamp}')
            if backup.exists():
                fail(f'backup path already exists: {backup}')
            target.rename(backup)
        try:
            shutil.copytree(source, target)
        except Exception as exc:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            if backup is not None and backup.exists():
                backup.rename(target)
            fail(f'install failed and was rolled back: {type(exc).__name__}: {exc}')

    print('[4/5] Verifying Unified Brain')
    if not compileall.compile_dir(str(live / 'extensions/unified_brain_ai'), quiet=1):
        fail('installed Unified Brain compile check failed')
    live_s = str(live)
    if live_s not in sys.path:
        sys.path.insert(0, live_s)
    importlib.invalidate_caches()
    for key in list(sys.modules):
        if key == 'extensions.unified_brain_ai' or key.startswith('extensions.unified_brain_ai.'):
            del sys.modules[key]
    try:
        plugin = importlib.import_module('extensions.unified_brain_ai.plugin')
        info = plugin.register()
    except Exception as exc:
        fail(f'Unified Brain import verification failed: {type(exc).__name__}: {exc}')
    version = str(info.get('version') or '')
    if version != '4.4.0':
        fail(f'Unified Brain version mismatch: {version!r}')
    print(f'UNIFIED_VERSION={version}')

    print('[5/5] Binding existing two brains through OmniVenom')
    binder_url = f'https://raw.githubusercontent.com/{REPO}/{BINDER_COMMIT}/EIRA_OMNIVENOM_TWO_BRAIN_BIND_V2.py'
    try:
        binder_data = download(binder_url)
    except Exception as exc:
        fail(f'two-brain binder download failed: {type(exc).__name__}: {exc}')
    with tempfile.TemporaryDirectory(prefix='eira_bind_v2_') as td:
        binder = Path(td) / 'EIRA_OMNIVENOM_TWO_BRAIN_BIND_V2.py'
        binder.write_bytes(binder_data)
        rc = subprocess.run([sys.executable, '-m', 'py_compile', str(binder)]).returncode
        if rc != 0:
            fail('two-brain binder compile check failed')
        rc = subprocess.run([sys.executable, str(binder), str(live)]).returncode
        if rc != 0:
            fail(f'Unified Brain restored, but two-brain bind failed (rc={rc})')

    print('EIRA_UNIFIED_RESTORE_AND_BIND_V3=PASS')
    print('BRAINS=2')
    print('DOMINANT=unified_brain_ai')
    print('TANDEM=local_brain')
    print('OMNIVENOM=connective_web')
    print('VOICE_HANDOFF=main.py:_speak')


if __name__ == '__main__':
    main()
