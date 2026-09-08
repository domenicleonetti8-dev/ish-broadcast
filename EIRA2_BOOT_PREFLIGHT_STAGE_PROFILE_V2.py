#!/usr/bin/env python3
from __future__ import annotations
import json,sys,time,traceback
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
sys.path.insert(0,str(ROOT))
MANIFEST=ROOT/'eira2-package-manifest.json'
rows=[]
def stage(name,fn):
    t=time.perf_counter()
    try:
        value=fn(); rows.append({'stage':name,'ok':True,'seconds':round(time.perf_counter()-t,3),'type':type(value).__name__}); return value
    except Exception as e:
        rows.append({'stage':name,'ok':False,'seconds':round(time.perf_counter()-t,3),'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()[-3000:]}); raise
try:
    live=stage('import_eira2_live',lambda:__import__('eira2.live',fromlist=['*']))
    target_tree=stage('verified_live_identity',lambda:live._verified_live_identity(ROOT,MANIFEST))
    config=stage('live_config',lambda:live.live_config(ROOT,MANIFEST,host='127.0.0.1',port=8782))
    containment=stage('verify_private_model_containment',lambda:live.verify_private_model_containment(runtime_root=ROOT))
    socket_path=str(containment.get('unix_socket') or '')
    adapter=stage('ollama_adapter_construct',lambda:live.OllamaCandidateAdapter(model='qwen2.5:3b',unix_socket=socket_path))
    runtime=stage('runtime_construct',lambda:live.Eira2Runtime(config,generate=adapter.generate,verify=live.verify_response))
    out={'schema':'eira2_boot_preflight_stage_profile_v2','ok':True,'mutates_live':False,'rows':rows,'service_count':len(runtime.supervisor._records),'topological_order':runtime.supervisor.topological_order()}
except Exception as e:
    out={'schema':'eira2_boot_preflight_stage_profile_v2','ok':False,'mutates_live':False,'rows':rows,'error':f'{type(e).__name__}:{e}'}
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out['ok'] else 1)
