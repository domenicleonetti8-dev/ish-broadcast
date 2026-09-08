#!/usr/bin/env python3
from __future__ import annotations
import json, os, socket, subprocess
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
PROBE=ROOT/'eira_probe'

def tail(path:Path,n=12000):
    try:
        b=path.read_bytes(); return b[-n:].decode('utf-8','replace')
    except Exception as exc:
        return f'<read_failed:{type(exc).__name__}:{exc}>'

def tcp_open():
    s=socket.socket(); s.settimeout(1.0)
    try: s.connect(('127.0.0.1',8782)); return True
    except Exception: return False
    finally: s.close()

def run(cmd):
    p=subprocess.run(cmd,cwd=str(ROOT),text=True,capture_output=True,timeout=20,check=False)
    return {'returncode':p.returncode,'stdout':(p.stdout or '')[-12000:],'stderr':(p.stderr or '')[-6000:]}

def main():
    out={
      'schema':'eira2_runtime_8782_forensic_v4','ok':True,'mutates_live':False,
      'port_8782_open':tcp_open(),
      'recovery_v3_receipt':tail(PROBE/'runtime_8782_recovery_v3.json'),
      'recovery_v3_log':tail(PROBE/'canonical_live_recovery_v3.log',20000),
      'processes':run(['pgrep','-af','python3.*-m eira2|python3.*main.py|eira2']),
      'systemd_transport':run(['systemctl','--user','status','eira2-autonomous-transport-v6.service','--no-pager','-l']),
    }
    print(json.dumps(out,separators=(',',':')))
    return 0
if __name__=='__main__': raise SystemExit(main())
