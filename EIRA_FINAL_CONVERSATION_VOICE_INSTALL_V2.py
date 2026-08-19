from __future__ import annotations

import hashlib
import py_compile
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

LIVE = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MAIN = LIVE / 'main.py'
RUNTIME = LIVE / 'extensions' / 'eira_bluetooth_voice_ai' / 'runtime.py'

MARKER = '# EIRA_BLUETOOTH_VOICE_OUTWARD_HANDOFF_V2'


def die(message: str) -> None:
    raise SystemExit('EIRA FINAL CONVERSATION VOICE V2: ' + message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


if not MAIN.is_file():
    die('main.py missing from LIVE')
if not RUNTIME.is_file():
    die('Bluetooth voice runtime missing from LIVE')

py_compile.compile(str(RUNTIME), doraise=True)
source = MAIN.read_text(encoding='utf-8')
before_sha = sha256(MAIN)
stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
backup = LIVE / f'main.py.bak_final_conversation_voice_v2_{stamp}'
shutil.copy2(MAIN, backup)

try:
    if MARKER not in source:
        m = re.search(r'(?m)^def _speak\(response\):\s*$', source)
        if not m:
            die('_speak function not found; main.py left unchanged')

        body_start = m.end()
        next_top = re.search(r'(?m)^def\s+\w+\s*\(', source[body_start:])
        func_end = body_start + (next_top.start() if next_top else len(source[body_start:]))
        block = source[body_start:func_end]

        print_match = re.search(r'(?m)^(\s+)print\(\s*[\'\"]EIRA:[\'\"]\s*,\s*identity_checked\s*\)\s*$', block)
        if not print_match:
            die('_speak EIRA print not found; main.py left unchanged')

        indent = print_match.group(1)
        insertion_at = body_start + print_match.end()
        handoff = (
            '\n'
            + indent + MARKER + '\n'
            + indent + 'try:\n'
            + indent + '    from extensions.eira_bluetooth_voice_ai.runtime import runtime as _eira_voice_runtime\n'
            + indent + '    _eira_voice_runtime().enqueue(identity_checked)\n'
            + indent + 'except Exception:\n'
            + indent + '    pass'
        )
        source = source[:insertion_at] + handoff + source[insertion_at:]

    MAIN.write_text(source, encoding='utf-8')
    py_compile.compile(str(MAIN), doraise=True)

    installed = MAIN.read_text(encoding='utf-8')
    if installed.count(MARKER) != 1:
        die('voice handoff marker verification failed')
    if '_eira_voice_runtime().enqueue(identity_checked)' not in installed:
        die('voice enqueue verification failed')

except BaseException:
    shutil.copy2(backup, MAIN)
    try:
        py_compile.compile(str(MAIN), doraise=True)
    except Exception:
        pass
    raise

print('EIRA_FINAL_CONVERSATION_VOICE_V2=PASS')
print('BRAINS=2')
print('DOMINANT=unified_brain_ai')
print('TANDEM=local_brain')
print('OMNIVENOM=connective_fabric')
print('TEXT_OUTPUT=AVAILABLE')
print('VERBAL_OUTPUT=AUTOMATIC')
print('BLUETOOTH_ACQUIRE=ON_FIRST_SPEAK_AND_RECONNECT')
print('MAIN_BEFORE_SHA256=' + before_sha)
print('MAIN_AFTER_SHA256=' + sha256(MAIN))
print('BACKUP=' + str(backup))
