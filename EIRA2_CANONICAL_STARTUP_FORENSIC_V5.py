#!/usr/bin/env python3
from __future__ import annotations
import json, os, signal, socket, subprocess, time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')

def port_open():
    s=socket.socket(); s.settimeout(.5)
    try: s.connect(('127.0.0.1',8782)); return True
    except Exception: return False
    finally: s.close()

def main()->int:
    out={'schema':'eira2_canonical_startup_forensic_v5','ok':True,'controlled_runtime_probe':True,'mutates_source_files':False}
    before=port_open(); out['port_before']=before
    if before:
        out['status']='already_open'; print(json.dumps(out,separators=(',',':'))); return 0
    p=subprocess.Popen(['python3','-m','eira2','--live','--root',str(ROOT)],cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    opened=False; exited=False
    deadline=time.time()+50
    while time.time()<deadline:
        if p.poll() is not None:
            exited=True; break
        if port_open():
            opened=True; break
        time.sleep(.5)
    out['spawned_pid']=p.pid; out['port_opened']=opened; out['exited_early']=exited; out['returncode']=p.poll()
    if opened:
        # Leave a healthy canonical runtime running. Detach output pipes by not waiting.
        out['status']='started_and_preserved'
        print(json.dumps(out,separators=(',',':')))
        return 0
    try:
        os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    try: stdout,stderr=p.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        stdout,stderr=p.communicate(timeout=5)
    out['status']='startup_failed'; out['stdout_tail']=(stdout or '')[-16000:]; out['stderr_tail']=(stderr or '')[-16000:]; out['final_returncode']=p.returncode; out['port_after']=port_open(); out['ok']=False
    print(json.dumps(out,separators=(',',':')))
    return 1
if __name__=='__main__': raise SystemExit(main())
