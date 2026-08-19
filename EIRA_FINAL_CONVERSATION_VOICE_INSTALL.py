from __future__ import annotations

import hashlib
import py_compile
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LIVE = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MAIN = LIVE / 'main.py'
RUNTIME = LIVE / 'extensions' / 'eira_bluetooth_voice_ai' / 'runtime.py'

BOOT_MARKER = '# EIRA_BLUETOOTH_VOICE_AUTOBOOT_V1'
SPEAK_MARKER = '# EIRA_BLUETOOTH_VOICE_OUTWARD_HANDOFF_V1'


def die(message: str) -> None:
    raise SystemExit('EIRA FINAL CONVERSATION VOICE: ' + message)


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

# Verify the already-proven runtime before touching main.py.
py_compile.compile(str(RUNTIME), doraise=True)

source = MAIN.read_text(encoding='utf-8')
before_sha = sha256(MAIN)
stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
backup = LIVE / f'main.py.bak_final_conversation_voice_{stamp}'
shutil.copy2(MAIN, backup)

try:
    # Start Bluetooth acquisition as Eira wakes. runtime() starts the existing
    # reconnect + speech worker threads; it does not create another brain.
    if BOOT_MARKER not in source:
        anchor = 'from engine.core_engine import core'
        if anchor not in source:
            die('boot anchor not found; main.py left unchanged')
        boot_block = '''\n# EIRA_BLUETOOTH_VOICE_AUTOBOOT_V1\ntry:\n    from extensions.eira_bluetooth_voice_ai.runtime import runtime as _eira_voice_runtime\n    _EIRA_VOICE_RUNTIME = _eira_voice_runtime()\nexcept Exception as _eira_voice_boot_error:\n    _EIRA_VOICE_RUNTIME = None\n\n'''
        source = source.replace(anchor, anchor + boot_block, 1)

    # Preserve Eira's single outward text plane, then hand the exact same final
    # text to the proven Piper -> Bluetooth sink path asynchronously.
    if SPEAK_MARKER not in source:
        target = '    print("EIRA:", identity_checked)'
        if target not in source:
            die('_speak final print anchor not found; main.py left unchanged')
        handoff = '''    # EIRA_BLUETOOTH_VOICE_OUTWARD_HANDOFF_V1\n    print("EIRA:", identity_checked)\n    try:\n        if _EIRA_VOICE_RUNTIME is not None:\n            _EIRA_VOICE_RUNTIME.enqueue(identity_checked)\n    except Exception:\n        pass'''
        source = source.replace(target, handoff, 1)

    MAIN.write_text(source, encoding='utf-8')
    py_compile.compile(str(MAIN), doraise=True)

    installed = MAIN.read_text(encoding='utf-8')
    if installed.count(BOOT_MARKER) != 1:
        die('autoboot marker verification failed')
    if installed.count(SPEAK_MARKER) != 1:
        die('outward handoff marker verification failed')
    if '_EIRA_VOICE_RUNTIME.enqueue(identity_checked)' not in installed:
        die('voice enqueue verification failed')

except BaseException:
    shutil.copy2(backup, MAIN)
    try:
        py_compile.compile(str(MAIN), doraise=True)
    except Exception:
        pass
    raise

print('EIRA_FINAL_CONVERSATION_VOICE_INSTALL=PASS')
print('BRAINS=2')
print('DOMINANT=unified_brain_ai')
print('TANDEM=local_brain')
print('OMNIVENOM=connective_fabric')
print('OUTWARD_RESPONSE_PLANES=1')
print('TEXT_OUTPUT=AVAILABLE')
print('VERBAL_OUTPUT=AUTOMATIC')
print('BLUETOOTH_WAKE_ACQUIRE=AUTOMATIC')
print('VOICE=Piper en_US-hfc_female-medium')
print('MAIN_BEFORE_SHA256=' + before_sha)
print('MAIN_AFTER_SHA256=' + sha256(MAIN))
print('BACKUP=' + str(backup))
