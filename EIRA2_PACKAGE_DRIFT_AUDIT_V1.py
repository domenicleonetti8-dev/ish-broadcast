#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MANIFEST = ROOT / 'eira2-package-manifest.json'
EXCLUDED_PARTS = {'.git','var','__pycache__','.pytest_cache','.mypy_cache','build','dist','eira_probe'}
EXCLUDED_SUFFIXES = {'.pyc','.pyo'}


def included(rel: Path) -> bool:
    if rel.name == 'eira2-package-manifest.json':
        return False
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if rel.suffix.casefold() in EXCLUDED_SUFFIXES:
        return False
    return True


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text())
    sealed = {str(r['path']): r for r in payload.get('files', [])}
    current = {}
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(ROOT)
        if not included(rel):
            continue
        current[rel.as_posix()] = {'size': p.stat().st_size, 'sha256': sha(p)}

    changed=[]; missing=[]; unsealed=[]
    for rel,row in sealed.items():
        now=current.get(rel)
        if now is None:
            missing.append(rel)
        elif int(row['size']) != now['size'] or str(row['sha256']) != now['sha256']:
            changed.append({'path':rel,'sealed_size':int(row['size']),'current_size':now['size'],'sealed_sha256':str(row['sha256']),'current_sha256':now['sha256']})
    for rel,now in current.items():
        if rel not in sealed:
            unsealed.append({'path':rel,**now})

    out={'ok':not changed and not missing and not unsealed,'sealed_count':len(sealed),'current_count':len(current),'changed':changed,'missing':missing,'unsealed':unsealed}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
