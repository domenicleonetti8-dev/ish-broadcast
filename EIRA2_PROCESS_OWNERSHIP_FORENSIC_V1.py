#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess
PIDS=[2197106,2702069]
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=30,check=False)
    return {'returncode':p.returncode,'stdout':p.stdout[-10000:],'stderr':p.stderr[-3000:]}
rows=[]
for pid in PIDS:
    proc=f'/proc/{pid}'
    row={'pid':pid,'exists':os.path.isdir(proc)}
    if row['exists']:
        for name in ('cmdline','cgroup','status'):
            try:
                raw=open(f'{proc}/{name}','rb').read().replace(b'\0',b' ').decode(errors='replace')
            except Exception as e: raw=f'<{type(e).__name__}:{e}>'
            row[name]=raw[-12000:]
        row['systemctl_user_status']=run(['systemctl','--user','status',str(pid),'--no-pager','-l'])
    rows.append(row)
out={'schema':'eira2_process_ownership_forensic_v1','ok':True,'mutates_live':False,'rows':rows,'port_8782':run(['bash','-lc',"ss -ltnp 2>/dev/null | grep ':8782' || true"]),'health':run(['curl','-sS','--max-time','8','http://127.0.0.1:8782/health'])}
print(json.dumps(out,separators=(',',':')))
