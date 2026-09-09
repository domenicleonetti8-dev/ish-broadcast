#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import sys
import time
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MANIFEST = ROOT / 'eira2-package-manifest.json'
STATE = ROOT / 'eira_probe' / 'text_path_recovery_v1'
RECEIPT = STATE / 'receipt.json'
ALLOWED_CHANGED = {'eira2/evidence/universe_public_library.py'}
EXCLUDED_TOP = {'.git','var','__pycache__','.pytest_cache','.mypy_cache','build','dist','eira_probe'}
IMMUTABLE_SUFFIXES = {'.py','.json','.md','.toml','.yaml','.yml','.txt','.ini','.cfg'}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    os.replace(tmp, path)


def manifest_rows(payload: dict) -> list[dict]:
    for key in ('files','file_rows','entries'):
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    raise RuntimeError('manifest_rows_not_found')


def current_immutable_files() -> dict[str, Path]:
    out = {}
    for p in ROOT.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] in EXCLUDED_TOP:
            continue
        if p.name == MANIFEST.name:
            continue
        if p.suffix.lower() not in IMMUTABLE_SUFFIXES:
            continue
        out[rel.as_posix()] = p
    return out


def compile_python(paths: list[Path]) -> None:
    for p in paths:
        if p.suffix == '.py':
            py_compile.compile(str(p), doraise=True)


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.is_file():
        raise RuntimeError('manifest_missing')

    before = json.loads(MANIFEST.read_text())
    rows = manifest_rows(before)
    sealed = {}
    for row in rows:
        rel = row.get('path') or row.get('relative_path')
        if rel:
            sealed[str(rel)] = row

    current = current_immutable_files()
    missing, changed = [], []
    for rel, row in sealed.items():
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        expected_size = row.get('bytes', row.get('size'))
        expected_sha = row.get('sha256') or row.get('sha')
        actual_size = p.stat().st_size
        actual_sha = sha256(p)
        if expected_size is not None and int(expected_size) != actual_size:
            changed.append({'path':rel,'reason':'size','expected':int(expected_size),'actual':actual_size,'sha256':actual_sha})
        elif expected_sha and str(expected_sha) != actual_sha:
            changed.append({'path':rel,'reason':'sha256','expected':str(expected_sha),'actual':actual_sha})

    unsealed = sorted(set(current) - set(sealed))
    changed_paths = {x['path'] for x in changed}

    audit = {
        'schema':'eira2_text_path_recovery_v1',
        'phase':'audit',
        'unix':time.time(),
        'missing':missing,
        'changed':changed,
        'unsealed':unsealed,
        'sealed_count':len(sealed),
        'current_immutable_count':len(current),
    }
    atomic_json(RECEIPT, audit)

    if missing:
        raise RuntimeError('missing_sealed_files:' + ','.join(missing))
    unexplained = sorted(changed_paths - ALLOWED_CHANGED)
    if unexplained:
        raise RuntimeError('unexplained_changed_files:' + ','.join(unexplained))
    if ALLOWED_CHANGED - changed_paths:
        raise RuntimeError('expected_boot_drift_not_present')

    # Preserve every current immutable file and prove Python syntax before changing identity metadata.
    compile_python(list(current.values()))

    backup = STATE / f'eira2-package-manifest.before.{int(time.time())}.json'
    shutil.copy2(MANIFEST, backup)

    sys.path.insert(0, str(ROOT))
    from eira2.operations import package_identity as pi

    # Use Eira's own canonical manifest writer. Preserve the source commit from the existing seal when supported.
    import inspect
    sig = inspect.signature(pi.write_package_manifest)
    kwargs = {}
    for name in sig.parameters:
        if name in ('root','package_root'):
            kwargs[name] = ROOT
        elif name in ('manifest','manifest_path','path'):
            kwargs[name] = MANIFEST
        elif name in ('source_commit_sha','source_commit','commit_sha'):
            kwargs[name] = before.get('source_commit_sha') or before.get('source_commit') or ''
    pi.write_package_manifest(**kwargs)
    verified = pi.verify_package_manifest(ROOT, MANIFEST)

    after = json.loads(MANIFEST.read_text())
    receipt = {
        'schema':'eira2_text_path_recovery_v1',
        'phase':'reconciled',
        'ok':True,
        'unix':time.time(),
        'backup':str(backup.relative_to(ROOT)),
        'changed_preserved':changed,
        'unsealed_preserved_and_sealed':unsealed,
        'manifest_sha256':sha256(MANIFEST),
        'manifest_file_count':after.get('file_count'),
        'package_tree_sha256':after.get('package_tree_sha256'),
        'verify_result_type':type(verified).__name__,
    }
    atomic_json(RECEIPT, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
