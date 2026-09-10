#!/usr/bin/env python3
from __future__ import annotations
import json, os, runpy, threading, time
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
V3_HEARTBEAT=ROOT/'eira_probe'/'orin_build_probe_v3'/'heartbeat.json'
V1_COMPAT_HEARTBEAT=ROOT/'eira_probe'/'orin_build_probe_v1'/'heartbeat.json'
V1_DORMANT=ROOT/'eira_probe'/'orin_build_probe_v1'/'DORMANT.json'
V31=ROOT/'eira_probe'/'orin_build_probe_versions'/'probe_984bef79101a2fa2.py'

def atom(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    os.replace(tmp,path)

def mirror():
    while True:
        try:
            src=json.loads(V3_HEARTBEAT.read_text()) if V3_HEARTBEAT.is_file() else {}
            atom(V1_COMPAT_HEARTBEAT,{
                'schema':'eira2_build_probe_v3_supervisor_v2_compat_v1',
                'ok':bool(src.get('ok',True)),
                'phase':'v3_compat:'+str(src.get('phase','starting')),
                'pid':0,
                'v3_pid':src.get('pid'),
                'v1_dormant':V1_DORMANT.is_file(),
                'unix':time.time(),
            })
        except Exception:
            pass
        time.sleep(2.0)

if not V31.is_file():
    raise SystemExit('verified_v31_candidate_missing')
threading.Thread(target=mirror,name='v3-supervisor-v2-compat',daemon=True).start()
runpy.run_path(str(V31),run_name='__main__')
