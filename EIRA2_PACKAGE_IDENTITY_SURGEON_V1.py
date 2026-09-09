#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MANIFEST = ROOT / 'eira2-package-manifest.json'
TARGET = 'eira2/evidence/universe_public_library.py'
RETIRE = [
    'tools/eira2_voice_path_completion.py',
    'tools/eira2_provision_canonical_voice_asset.py',
    'tools/eira2_flashcube_connect.py',
]
EXCLUDED_PARTS = {'.git','var','__pycache__','.pytest_cache','.mypy_cache','build','dist','eira_probe'}
EXCLUDED_SUFFIXES = {'.pyc','.pyo'}
IMMUTABLE_SUFFIXES = {'.py','.pyi','.toml','.json','.yaml','.yml','.ini','.cfg','.md','.js','.mjs','.cjs','.html','.css','.sh','.service'}
IMMUTABLE_NAMES = {'main.py','pyproject.toml'}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode('utf-8')


def included(rel: Path) -> bool:
    if rel.name == MANIFEST.name:
        return False
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if rel.suffix.casefold() in EXCLUDED_SUFFIXES:
        return False
    return True


def immutable(rel: Path) -> bool:
    return rel.name in IMMUTABLE_NAMES or rel.suffix.casefold() in IMMUTABLE_SUFFIXES


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + '.new')
    tmp.write_text(text, encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main() -> int:
    if not MANIFEST.is_file():
        raise SystemExit('PACKAGE_SURGEON=FAIL manifest_missing')

    payload = json.loads(MANIFEST.read_text(encoding='utf-8'))
    rows = payload.get('files')
    if not isinstance(rows, list) or not rows:
        raise SystemExit('PACKAGE_SURGEON=FAIL manifest_rows_invalid')

    sealed = {str(r['path']): r for r in rows}
    if TARGET not in sealed:
        raise SystemExit('PACKAGE_SURGEON=FAIL target_not_sealed')

    changed = []
    missing = []
    for rel, row in sealed.items():
        p = ROOT / rel
        if not p.is_file() or p.is_symlink():
            missing.append(rel)
            continue
        data = p.read_bytes()
        if len(data) != int(row['size']) or sha_bytes(data) != str(row['sha256']):
            changed.append(rel)

    unexpected_changed = [p for p in changed if p != TARGET]
    if missing or unexpected_changed:
        print(json.dumps({'ok':False,'missing':missing,'unexpected_changed':unexpected_changed,'allowed_changed':[p for p in changed if p==TARGET]}, indent=2))
        raise SystemExit('PACKAGE_SURGEON=FAIL unexplained_sealed_drift')

    current_unsealed = []
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(ROOT)
        if not included(rel):
            continue
        r = rel.as_posix()
        if r not in sealed and immutable(rel):
            current_unsealed.append(r)

    allowed_retire = set(RETIRE)
    unexpected_unsealed = [p for p in current_unsealed if p not in allowed_retire]
    if unexpected_unsealed:
        print(json.dumps({'ok':False,'unexpected_unsealed_immutable':unexpected_unsealed,'known_helpers':[p for p in current_unsealed if p in allowed_retire]}, indent=2))
        raise SystemExit('PACKAGE_SURGEON=FAIL unexplained_unsealed_immutable')

    stamp = time.strftime('%Y%m%d_%H%M%S')
    retired_root = ROOT / 'eira_probe' / 'retired_unsealed_helpers' / stamp
    retired = []
    for rel in RETIRE:
        src = ROOT / rel
        if src.is_file():
            dst = retired_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            retired.append({'from':rel,'to':str(dst.relative_to(ROOT))})

    target_path = ROOT / TARGET
    target_data = target_path.read_bytes()
    target_row = sealed[TARGET]
    target_row['size'] = len(target_data)
    target_row['sha256'] = sha_bytes(target_data)

    payload['package_tree_sha256'] = sha_bytes(canonical_bytes(rows))
    payload['file_count'] = len(rows)

    backup = ROOT / 'eira_probe' / f'eira2-package-manifest.before_surgeon.{stamp}.json'
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANIFEST, backup)
    atomic_write(MANIFEST, json.dumps(payload, indent=2, sort_keys=True) + '\n')

    sys.path.insert(0, str(ROOT))
    from eira2.operations.package_identity import verify_package_manifest
    verified = verify_package_manifest(ROOT, MANIFEST)

    compile_targets = [
        ROOT/'eira2/conversation/spine.py',
        ROOT/'eira2/conversation/analysis.py',
        ROOT/'eira2/reasoning/provider.py',
        ROOT/'eira2/runtime.py',
        target_path,
    ]
    for p in compile_targets:
        compile(p.read_text(encoding='utf-8'), str(p), 'exec')

    receipt = {
        'ok': True,
        'schema': 'eira2_package_identity_surgeon_v1',
        'target': TARGET,
        'target_size': len(target_data),
        'target_sha256': sha_bytes(target_data),
        'package_tree_sha256': verified['package_tree_sha256'],
        'file_count': verified['file_count'],
        'manifest_backup': str(backup.relative_to(ROOT)),
        'retired_helpers': retired,
        'cognition_compile': 'PASS',
    }
    out = ROOT/'eira_probe/package_identity_surgeon_v1_receipt.json'
    atomic_write(out, json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
