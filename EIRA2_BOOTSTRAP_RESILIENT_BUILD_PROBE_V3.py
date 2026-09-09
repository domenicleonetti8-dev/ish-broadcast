#!/usr/bin/env python3
from pathlib import Path
import hashlib,subprocess,urllib.request
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
PIN='f64a274dfa8424f786b20566e7bb58bc21694762'
SUP_PIN='9cb3d6fddaa21e2cdb2f8dd9afbb4a5002d84a88'
BASE='https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast'
FILES=[
 (f'{BASE}/{PIN}/EIRA2_ORIN_BUILD_PROBE_V3_RESILIENT.py',ROOT/'tools'/'eira2_orin_build_probe.py',True),
 (f'{BASE}/{SUP_PIN}/EIRA2_ORIN_BUILD_PROBE_SUPERVISOR_V3_ROLLBACK.py',ROOT/'eira_probe'/'eira2_orin_build_probe_supervisor_v3.py',True),
 (f'{BASE}/{SUP_PIN}/EIRA2_ORIN_BUILD_PROBE_SUPERVISOR_V3.service',Path.home()/'.config/systemd/user/eira2-orin-build-probe.service',False),
]
for url,dst,is_py in FILES:
 data=urllib.request.urlopen(url,timeout=30).read()
 if is_py: compile(data.decode('utf-8'),str(dst),'exec')
 dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.is_file():
  bak=dst.with_name(dst.name+'.before_resilient_probe_v3')
  if not bak.exists(): bak.write_bytes(dst.read_bytes())
 tmp=dst.with_name(dst.name+'.tmp'); tmp.write_bytes(data); tmp.replace(dst)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','eira2-orin-build-probe.service'],check=True)
subprocess.run(['systemctl','--user','restart','eira2-orin-build-probe.service'],check=True)
q=subprocess.run(['systemctl','--user','is-active','eira2-orin-build-probe.service'],capture_output=True,text=True)
print('BUILD_PROBE_V3_RESILIENT='+('PASS' if q.stdout.strip()=='active' else 'FAIL'))
