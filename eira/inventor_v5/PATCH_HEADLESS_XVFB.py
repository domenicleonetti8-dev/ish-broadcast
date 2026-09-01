#!/usr/bin/env python3
from pathlib import Path
import py_compile

ROOT=Path.cwd()
P=ROOT/'extensions'/'eira_inventor_holographic_lab'/'pipeline.py'
if not P.exists(): raise SystemExit(f'missing:{P}')
s=P.read_text()
old="subprocess.run([blender,'-b','--python',str(py)],check=True)"
new="""\n        import shutil, os\n        cmd=[blender,'-b','--python',str(py)]\n        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):\n            xvfb=shutil.which('xvfb-run')\n            if not xvfb:\n                raise RuntimeError('headless_blender_requires_xvfb_run')\n            cmd=[xvfb,'-a']+cmd\n        subprocess.run(cmd,check=True)\n""".strip()
if old not in s:
    if "headless_blender_requires_xvfb_run" in s:
        print('ALREADY_PATCHED')
    else:
        raise SystemExit('target_call_not_found')
else:
    s=s.replace(old,new,1)
    P.write_text(s)
    print('PATCHED',P)
py_compile.compile(str(P),doraise=True)
print('HEADLESS_XVFB_PATCH_PASS')
