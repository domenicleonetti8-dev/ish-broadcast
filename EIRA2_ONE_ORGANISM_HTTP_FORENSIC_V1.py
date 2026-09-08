#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')

def run(cmd):
    p=subprocess.run(cmd,cwd=str(ROOT),text=True,capture_output=True,timeout=20,check=False)
    return {'rc':p.returncode,'stdout':(p.stdout or '')[-20000:],'stderr':(p.stderr or '')[-6000:]}

def read(rel,limit=30000):
    p=ROOT/rel
    try:
        return p.read_text(encoding='utf-8',errors='replace')[:limit]
    except Exception as exc:
        return f'<read_failed:{type(exc).__name__}:{exc}>'

def main():
    out={'schema':'eira2_one_organism_http_forensic_v1','ok':True,'mutates_live':False,
         'processes':run(['ps','-eo','pid=,ppid=,stat=,etimes=,cmd=']),
         'listeners':run(['ss','-ltnp']),
         'runtime_py':read('eira2/runtime.py'),
         'live_py':read('eira2/live.py'),
         'main_py':read('eira2/__main__.py'),
         'transport_agent_py':read('tools/eira2_github_transport_agent.py'),
         'transport_v6_py':read('eira_probe/transport_runtime_v6/eira2_autonomous_transport_v6.py')}
    print(json.dumps(out,separators=(',',':')))
    return 0
if __name__=='__main__': raise SystemExit(main())
