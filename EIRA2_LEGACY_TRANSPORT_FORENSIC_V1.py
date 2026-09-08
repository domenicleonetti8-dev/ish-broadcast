#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess

def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=30,check=False)
    return {'returncode':p.returncode,'stdout':p.stdout[-12000:],'stderr':p.stderr[-4000:]}
out={
 'schema':'eira2_legacy_transport_forensic_v1',
 'ok':True,
 'mutates_live':False,
 'processes':run(['ps','-eo','pid,ppid,lstart,args']),
 'user_units':run(['systemctl','--user','list-units','--all','--type=service','--no-pager','--no-legend']),
 'user_unit_files':run(['systemctl','--user','list-unit-files','--type=service','--no-pager','--no-legend'])
}
print(json.dumps(out,separators=(',',':')))
