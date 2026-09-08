#!/usr/bin/env python3
from __future__ import annotations
import cProfile,io,json,pstats,sys,time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve(); sys.path.insert(0,str(ROOT))
MANIFEST=ROOT/'eira2-package-manifest.json'
import eira2.live as live
try:
    target,_=live._verified_live_identity(ROOT,MANIFEST)
    config=live.live_config(ROOT,MANIFEST,host='127.0.0.1',port=8782)
    containment=live.verify_private_model_containment(runtime_root=ROOT)
    adapter=live.OllamaCandidateAdapter(model='qwen2.5:3b',unix_socket=str(containment.get('unix_socket') or ''))
    pr=cProfile.Profile(); t=time.perf_counter(); pr.enable()
    runtime=live.Eira2Runtime(config,generate=adapter.generate,verify=live.verify_response)
    pr.disable(); elapsed=time.perf_counter()-t
    s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats('cumulative').print_stats(45)
    out={'schema':'eira2_runtime_constructor_profile_v1','ok':True,'mutates_live':False,'elapsed_seconds':round(elapsed,3),'service_count':len(runtime.supervisor._records),'profile_top':s.getvalue()}
except Exception as e:
    out={'schema':'eira2_runtime_constructor_profile_v1','ok':False,'mutates_live':False,'error':f'{type(e).__name__}:{e}'}
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out['ok'] else 1)
