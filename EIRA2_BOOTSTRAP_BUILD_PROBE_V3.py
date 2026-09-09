#!/usr/bin/env python3
from pathlib import Path
import subprocess, urllib.request

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
PIN='6a8b8cf035b22247d9943252ba264ecd1d6f528a'
BASE=f'https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{PIN}'
SUP=ROOT/'eira_probe'/'eira2_orin_build_probe_supervisor_v3.py'
UNIT=Path.home()/'.config/systemd/user/eira2-orin-build-probe.service'

SUP.parent.mkdir(parents=True,exist_ok=True)
UNIT.parent.mkdir(parents=True,exist_ok=True)
for src,dst in [
    ('EIRA2_ORIN_BUILD_PROBE_SUPERVISOR_V3_ROLLBACK.py',SUP),
    ('EIRA2_ORIN_BUILD_PROBE_SUPERVISOR_V3.service',UNIT),
]:
    data=urllib.request.urlopen(f'{BASE}/{src}',timeout=30).read()
    if src.endswith('.py'):
        compile(data.decode('utf-8'),str(dst),'exec')
    tmp=dst.with_name(dst.name+'.tmp')
    tmp.write_bytes(data)
    tmp.replace(dst)

subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','eira2-orin-build-probe.service'],check=True)
print('BUILD_PROBE_V3_BOOTSTRAP=PASS')
