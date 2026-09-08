#!/usr/bin/env python3
from __future__ import annotations
import cProfile,pstats,io,json,sys,time,traceback
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve(); sys.path.insert(0,str(ROOT))
out={'schema':'eira2_runtime_constructor_profile_v2','ok':False,'mutates_live':False}
try:
    from eira2.live import live_config, verify_response
    from eira2.operations.model_takeover import verify_private_model_containment
    from eira2.adapters.ollama import OllamaCandidateAdapter
    from eira2.runtime import Eira2Runtime
    cfg=live_config(ROOT,ROOT/'eira2-package-manifest.json',host='127.0.0.1',port=8782)
    cont=verify_private_model_containment(runtime_root=ROOT)
    adapter=OllamaCandidateAdapter(model='qwen2.5:3b',unix_socket=str(cont.get('unix_socket') or ''))
    pr=cProfile.Profile(); t=time.perf_counter(); pr.enable()
    runtime=Eira2Runtime(cfg,generate=adapter.generate,verify=verify_response)
    pr.disable(); elapsed=time.perf_counter()-t
    s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats('cumulative').print_stats(60)
    out.update(ok=True,elapsed_seconds=round(elapsed,3),service_count=len(getattr(runtime.supervisor,'_records',{})),profile=s.getvalue()[-30000:])
except Exception as e:
    out['error']=f'{type(e).__name__}:{e}'; out['traceback']=traceback.format_exc()[-12000:]
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out.get('ok') else 1)
