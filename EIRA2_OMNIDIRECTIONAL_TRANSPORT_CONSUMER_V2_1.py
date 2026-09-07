#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
RUNTIME=ROOT/'eira_probe'/'transport_runtime_v2_3'
TARGET=RUNTIME/'eira2_omnidirectional_transport_consumer_v2_2.py'
URL='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V2_2.py'
RUNTIME.mkdir(parents=True,exist_ok=True)
p=subprocess.run(['curl','-fsSL',URL,'-o',str(TARGET)],text=True,capture_output=True,timeout=120)
if p.returncode: raise SystemExit('transport_v22_fetch_failed:'+p.stderr[-800:])
p=subprocess.run([sys.executable,'-m','py_compile',str(TARGET)],text=True,capture_output=True,timeout=120)
if p.returncode: raise SystemExit('transport_v22_compile_failed:'+p.stderr[-1200:])
os.execv(sys.executable,[sys.executable,str(TARGET),*sys.argv[1:]])
