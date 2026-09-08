#!/usr/bin/env python3
from __future__ import annotations
import asyncio,json,os,signal,sys,time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
sys.path.insert(0,str(ROOT))
EVENTS=[]
CURRENT={'name':None,'started':None}

def emit_and_exit(reason):
    out={'schema':'eira2_supervisor_start_trace_v1','ok':True,'mutates_source_files':False,'reason':reason,'current':CURRENT,'events':EVENTS}
    print(json.dumps(out,separators=(',',':')),flush=True)
    os._exit(0)

def alarm(signum,frame): emit_and_exit('alarm_35s')

async def main_async():
    from eira2.kernel.supervisor import Supervisor
    from eira2.live import run_live
    orig=Supervisor._start_record
    async def wrapped(self,name,record):
        CURRENT['name']=name; CURRENT['started']=time.time(); EVENTS.append({'event':'begin','name':name,'t':time.time()})
        try:
            await orig(self,name,record)
            EVENTS.append({'event':'ready','name':name,'t':time.time()})
        except BaseException as exc:
            EVENTS.append({'event':'error','name':name,'t':time.time(),'error':f'{type(exc).__name__}:{exc}'})
            raise
        finally:
            CURRENT['name']=None; CURRENT['started']=None
    Supervisor._start_record=wrapped
    signal.signal(signal.SIGALRM,alarm); signal.alarm(35)
    try:
        await run_live(ROOT,ROOT/'eira2-package-manifest.json',host='127.0.0.1',port=8782)
    except BaseException as exc:
        EVENTS.append({'event':'run_live_error','t':time.time(),'error':f'{type(exc).__name__}:{exc}'})
        emit_and_exit('run_live_returned_or_failed')

def main(): asyncio.run(main_async()); return 0
if __name__=='__main__': raise SystemExit(main())
