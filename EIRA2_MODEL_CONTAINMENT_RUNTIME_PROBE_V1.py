#!/usr/bin/env python3
from __future__ import annotations
import json, time, traceback, subprocess, socket
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()

def cmd(*args):
    p=subprocess.run(list(args),cwd=str(ROOT),text=True,capture_output=True,timeout=20,check=False)
    return {'returncode':p.returncode,'stdout':p.stdout[-12000:],'stderr':p.stderr[-6000:]}

out={'schema':'eira2_model_containment_runtime_probe_v1','ok':False,'mutates_live':False}
try:
    t=time.monotonic()
    from eira2.operations.model_takeover import verify_private_model_containment
    out['import_seconds']=round(time.monotonic()-t,3)
    t=time.monotonic()
    receipt=verify_private_model_containment(runtime_root=ROOT)
    out['verify_seconds']=round(time.monotonic()-t,3)
    out['containment']=receipt
    sock=str(receipt.get('unix_socket') or '')
    out['unix_socket']=sock
    out['socket_exists']=bool(sock and Path(sock).exists())
    out['services']={
      'ollama':cmd('systemctl','--user','status','eira2-ollama.service','--no-pager','-l'),
      'proxy':cmd('systemctl','--user','status','eira2-model-proxy.service','--no-pager','-l'),
    }
    if sock:
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(3)
        try:
            s.connect(sock); out['socket_connect_ok']=True
        except Exception as e:
            out['socket_connect_ok']=False; out['socket_connect_error']=f'{type(e).__name__}:{e}'
        finally:
            s.close()
    out['ok']=True
except Exception as e:
    out['error']=f'{type(e).__name__}:{e}'
    out['traceback']=traceback.format_exc()[-12000:]
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out.get('ok') else 1)
