#!/usr/bin/env python3
from pathlib import Path
import base64, gzip, hashlib, json, time, urllib.request

ROOT = Path.cwd()
INV = ROOT / 'extensions' / 'eira_inventor_holographic_lab' / 'inventions'
if not INV.is_dir():
    raise SystemExit('FAIL: inventions archive not found')

BASE = 'https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/eira-inventor-v5/eira/inventor_v5/'
PARTS = ['v28_payload.part1.b64', 'v28_payload.part2.b64']
EXPECTED = '1058eaebe4f419dae5c504e8d909a62c7426bb7f1428a23ac083d4e661e46dc1'
NAME = 'EIRA_Off_World_Greenhouse_V28_DEPRESSURIZATION_STORM_CHAMBER.usdz'
FOLDER = INV / 'V28_OFF_WORLD_GREENHOUSE_REFERENCE'

text = ''
for part in PARTS:
    with urllib.request.urlopen(BASE + part, timeout=30) as r:
        text += r.read().decode('utf-8')

# Repair one Unicode lookalike introduced while transporting the compressed payload.
text = text.replace('\u043c', 'm')
text = ''.join(text.split())
try:
    compressed = base64.b64decode(text, validate=True)
    raw = gzip.decompress(compressed)
except Exception as e:
    raise SystemExit(f'FAIL: payload decode failed: {type(e).__name__}: {e}')

sha = hashlib.sha256(raw).hexdigest()
if sha != EXPECTED:
    raise SystemExit(f'FAIL: payload hash mismatch: {sha}')
if len(raw) != 730948 or raw[:2] != b'PK':
    raise SystemExit('FAIL: reconstructed USDZ package validation failed')

FOLDER.mkdir(parents=True, exist_ok=True)
target = FOLDER / 'model.usdz'
target.write_bytes(raw)
meta = {
    'id': 'V28_OFF_WORLD_GREENHOUSE_REFERENCE',
    'status': 'completed',
    'stage': 'imported_reference',
    'title': 'EIRA Off-World Greenhouse V28 - Depressurization Storm Chamber',
    'description': 'Completed Reference / Complexity Benchmark. Exact preserved V28 USDZ greenhouse assembly.',
    'created_at': time.time(),
    'output_dir': str(FOLDER),
    'imported': True,
    'benchmark': 'V28 Completed Reference / Complexity Benchmark',
    'original_filename': NAME,
    'sha256': sha,
    'size_bytes': len(raw),
}
(FOLDER / 'archive.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
print('V28_ARCHIVE_INSTALL_PASS')
print('USDZ:', target)
print('SHA256:', sha)
print('SIZE:', len(raw))
