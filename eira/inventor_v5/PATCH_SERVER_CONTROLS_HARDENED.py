#!/usr/bin/env python3
"""Compatibility shim for the retired broken server-controls patch.

This file intentionally performs no server rewrite. The corrected surgical patch is
PATCH_BUTTONS_AUTOSTART_SURGICAL.py on the same branch.
"""
from pathlib import Path
import runpy
import sys

candidate = Path('/tmp/PATCH_BUTTONS_AUTOSTART_SURGICAL.py')
if candidate.is_file():
    runpy.run_path(str(candidate), run_name='__main__')
    raise SystemExit(0)

print('PATCH_SERVER_CONTROLS_HARDENED_SUPERSEDED')
print('Use PATCH_BUTTONS_AUTOSTART_SURGICAL.py; this compatibility shim is syntax-safe.')
sys.exit(0)
