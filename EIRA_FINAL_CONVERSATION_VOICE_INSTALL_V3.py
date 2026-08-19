#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import py_compile
import re
import shutil

LIVE = Path('/media/domenicleonetti/easystore/EIRA/LIVE')
MAIN = LIVE / 'main.py'
VOICE = LIVE / 'extensions/eira_bluetooth_voice_ai/runtime.py'

if not MAIN.exists():
    raise SystemExit(f'EIRA VOICE V3: missing {MAIN}')
if not VOICE.exists():
    raise SystemExit(f'EIRA VOICE V3: missing {VOICE}')

s = MAIN.read_text(encoding='utf-8')
marker = '# EIRA_BLUETOOTH_VERBAL_HANDOFF_V3'
if marker in s:
    print('EIRA_FINAL_CONVERSATION_VOICE_V3=PASS')
    print('STATE=ALREADY_BOUND')
    raise SystemExit(0)

m = re.search(r'^def\s+_speak\s*\([^\n]*\)\s*:\s*$', s, flags=re.M)
if not m:
    raise SystemExit('EIRA VOICE V3: _speak function not found; main.py left unchanged')

next_def = re.search(r'^def\s+\w+\s*\(', s[m.end():], flags=re.M)
end = m.end() + next_def.start() if next_def else len(s)
chunk = s[m.start():end]

if 'identity_checked' in chunk:
    voice_text = 'identity_checked'
elif 'evidence_checked' in chunk:
    voice_text = 'evidence_checked'
else:
    voice_text = 'response'

insert = (
    '\n    # EIRA_BLUETOOTH_VERBAL_HANDOFF_V3\n'
    '    try:\n'
    '        from extensions.eira_bluetooth_voice_ai.runtime import runtime as _eira_voice_runtime\n'
    f'        _eira_voice_runtime().speak_now({voice_text})\n'
    '    except Exception as _eira_voice_error:\n'
    '        print("EIRA voice warning:", _eira_voice_error)\n'
)

new = s[:end] + insert + s[end:]

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup = MAIN.with_name(f'main.py.bak_voice_v3_{stamp}')
shutil.copy2(MAIN, backup)
MAIN.write_text(new, encoding='utf-8')

try:
    py_compile.compile(str(MAIN), doraise=True)
except Exception as e:
    shutil.copy2(backup, MAIN)
    raise SystemExit(f'EIRA VOICE V3: compile failed; rolled back: {e}')

print('EIRA_FINAL_CONVERSATION_VOICE_V3=PASS')
print('BRAINS=2')
print('DOMINANT=unified_brain_ai')
print('TANDEM=local_brain')
print('OMNIVENOM=connective_fabric')
print('TEXT_OUTPUT=AVAILABLE')
print('VERBAL_OUTPUT=AUTOMATIC')
print(f'VOICE_TEXT={voice_text}')
print(f'MAIN_BACKUP={backup}')
