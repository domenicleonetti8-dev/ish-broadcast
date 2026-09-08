#!/usr/bin/env python3
from __future__ import annotations
import json, time, traceback, sys
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve(); sys.path.insert(0,str(ROOT))
out={'schema':'eira2_prestart_milestone_probe_v1','ok':False,'mutates_live':False,'milestones':[]}
def step(name,fn):
    t=time.monotonic()
    try:
        v=fn(); out['milestones'].append({'name':name,'ok':True,'seconds':round(time.monotonic()-t,3),'type':type(v).__name__}); return v
    except Exception as e:
        out['milestones'].append({'name':name,'ok':False,'seconds':round(time.monotonic()-t,3),'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()[-8000:]}); raise
try:
    from eira2.package import verify_package_manifest
    from eira2.live import live_config, _verified_live_identity
    from eira2.operations.model_takeover import verify_private_model_containment
    from eira2.adapters.ollama import OllamaCandidateAdapter
    from eira2.runtime import Eira2Runtime
    from eira2.live import verify_response
    manifest=ROOT/'eira2-package-manifest.json'
    ident=step('verified_live_identity',lambda:_verified_live_identity(ROOT,manifest))
    config=step('live_config',lambda:live_config(ROOT,manifest,host='127.0.0.1',port=8782))
    containment=step('verify_private_model_containment',lambda:verify_private_model_containment(runtime_root=ROOT))
    sock=str(containment.get('unix_socket') or '')
    adapter=step('ollama_adapter_construct',lambda:OllamaCandidateAdapter(model='qwen2.5:3b',unix_socket=sock))
    runtime=step('eira2_runtime_construct',lambda:Eira2Runtime(config,generate=adapter.generate,verify=verify_response))
    out['service_count']=len(getattr(runtime.supervisor,'_records',{}))
    out['ok']=True
except Exception as e:
    out['error']=f'{type(e).__name__}:{e}'
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out.get('ok') else 1)
