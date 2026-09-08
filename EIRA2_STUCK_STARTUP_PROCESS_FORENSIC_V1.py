#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')

def run(cmd):
    p=subprocess.run(cmd,cwd=str(ROOT),text=True,capture_output=True,timeout=20,check=False)
    return {'returncode':p.returncode,'stdout':(p.stdout or '')[-16000:],'stderr':(p.stderr or '')[-8000:]}

def read(path):
    try:return Path(path).read_text(errors='replace')[-16000:]
    except Exception as exc:return f'<{type(exc).__name__}:{exc}>'

def main():
    pgrep=run(['pgrep','-af','python3 -m eira2 --live'])
    pids=[]
    for line in pgrep['stdout'].splitlines():
        try:pids.append(int(line.split(None,1)[0]))
        except:pass
    rows=[]
    for pid in pids:
        base=Path('/proc')/str(pid)
        row={'pid':pid,'status':read(base/'status'),'wchan':read(base/'wchan'),'cmdline':read(base/'cmdline')}
        row['threads']=run(['ps','-L','-p',str(pid),'-o','pid,tid,stat,wchan:32,etime,pcpu,pmem,comm'])
        row['fds']=run(['bash','-lc',f'ls -l /proc/{pid}/fd 2>/dev/null | tail -80'])
        rows.append(row)
    out={'schema':'eira2_stuck_startup_process_forensic_v1','ok':True,'mutates_live':False,'pgrep':pgrep,'processes':rows}
    print(json.dumps(out,separators=(',',':')));return 0
if __name__=='__main__':raise SystemExit(main())
