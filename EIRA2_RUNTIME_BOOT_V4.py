#!/usr/bin/env python3
from __future__ import annotations
import json, os, socket, subprocess, time, urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
PROBE=ROOT/'eira_probe'
LOG=PROBE/'canonical_live_runtime_v4.log'

def port_open():
    s=socket.socket(); s.settimeout(.5)
    try: s.connect(('127.0.0.1',8782)); return True
    except Exception: return False
    finally: s.close()

def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8782/health',timeout=5) as r:
            raw=r.read(); return {'ok':getattr(r,'status',200)==200,'status':getattr(r,'status',200),'body':raw.decode('utf-8','replace')[:12000]}
    except Exception as exc: return {'ok':False,'error':f'{type(exc).__name__}:{exc}'}

def main()->int:
    import sys
    sys.path.insert(0,str(ROOT))
    from eira2.operations.package_identity import verify_package_manifest
    manifest=verify_package_manifest(ROOT,ROOT/'eira2-package-manifest.json')
    out={'schema':'eira2_runtime_boot_v4','ok':False,'package_tree_sha256':manifest['package_tree_sha256'],'file_count':manifest['file_count']}
    h=health()
    if port_open() and h.get('ok'):
        out.update({'ok':True,'action':'preserve_existing','health':h}); print(json.dumps(out,separators=(',',':'))); return 0
    LOG.parent.mkdir(parents=True,exist_ok=True)
    lf=open(LOG,'ab',buffering=0)
    p=subprocess.Popen(['python3','-m','eira2','--live','--root',str(ROOT)],cwd=str(ROOT),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    deadline=time.time()+75
    last={}
    while time.time()<deadline:
        if p.poll() is not None: break
        if port_open():
            last=health()
            if last.get('ok'):
                out.update({'ok':True,'action':'started','pid':p.pid,'health':last,'log':str(LOG)}); print(json.dumps(out,separators=(',',':'))); return 0
        time.sleep(1)
    try: rc=p.poll()
    except Exception: rc=None
    try: tail=LOG.read_bytes()[-20000:].decode('utf-8','replace')
    except Exception as exc: tail=f'<log_read_failed:{exc}>'
    out.update({'action':'startup_failed','pid':p.pid,'returncode':rc,'health':last,'log_tail':tail,'port_open':port_open()})
    print(json.dumps(out,separators=(',',':'))); return 1
if __name__=='__main__': raise SystemExit(main())
