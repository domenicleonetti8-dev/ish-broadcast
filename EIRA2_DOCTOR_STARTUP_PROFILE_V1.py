#!/usr/bin/env python3
from __future__ import annotations
import cProfile, io, json, os, pstats, signal, socket, subprocess, sys, time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
sys.path.insert(0,str(ROOT))

def port_open():
    s=socket.socket(); s.settimeout(.5)
    try:s.connect(('127.0.0.1',8782));return True
    except Exception:return False
    finally:s.close()

def canonical_pids():
    p=subprocess.run(['pgrep','-af','python3 -m eira2 --live'],text=True,capture_output=True,check=False)
    rows=[]
    for line in p.stdout.splitlines():
        parts=line.split(None,1)
        if len(parts)==2 and 'python3 -m eira2 --live' in parts[1]: rows.append((int(parts[0]),parts[1]))
    return rows

def alarm_handler(signum,frame): raise TimeoutError('doctor_profile_alarm')

def main():
    out={'schema':'eira2_doctor_startup_profile_v1','ok':True,'mutates_source_files':False}
    if not port_open():
        retired=[]
        for pid,cmd in canonical_pids():
            try:
                os.kill(pid,signal.SIGTERM); retired.append({'pid':pid,'cmd':cmd})
            except ProcessLookupError: pass
        time.sleep(2)
        out['retired_unhealthy_live_processes']=retired
    from eira2.operations.full_doctor import full_audit_project
    prof=cProfile.Profile(); signal.signal(signal.SIGALRM,alarm_handler); signal.alarm(20)
    started=time.time(); exc=None
    try:
        prof.enable(); report=full_audit_project(ROOT,state_path=ROOT/'var'/'state.json',run_external_checks=False)
        out['audit_completed']=True; out['audit_ok']=report.ok; out['errors']=report.errors[:20]; out['checks']=report.checks
    except Exception as e:
        exc=f'{type(e).__name__}:{e}'; out['audit_completed']=False; out['audit_error']=exc
    finally:
        prof.disable(); signal.alarm(0)
    s=io.StringIO(); pstats.Stats(prof,stream=s).sort_stats('cumulative').print_stats(35)
    out['elapsed_seconds']=round(time.time()-started,3); out['profile_top']=s.getvalue()[-20000:]
    print(json.dumps(out,separators=(',',':'))); return 0
if __name__=='__main__': raise SystemExit(main())
