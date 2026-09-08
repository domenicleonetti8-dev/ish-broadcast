#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve(); sys.path.insert(0,str(ROOT))
TARGET=ROOT/'eira2/neural/organism.py'; EXPECT='9f056a89d292179b924d3431ed5bcde3c3ec1d9940ab43b2af8a95a301e2a620'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
try:
    observed=sha(TARGET)
    if observed!=EXPECT: raise RuntimeError('target_hash_mismatch:'+observed)
    compile(TARGET.read_text(encoding='utf-8'),str(TARGET),'exec')
    import eira2.live as live
    identity=live._verified_live_identity(ROOT,ROOT/'eira2-package-manifest.json')
    config=live.live_config(ROOT,ROOT/'eira2-package-manifest.json',host='127.0.0.1',port=8782)
    containment=live.verify_private_model_containment(runtime_root=ROOT)
    adapter=live.OllamaCandidateAdapter(model='qwen2.5:3b',unix_socket=str(containment.get('unix_socket') or ''))
    t=time.perf_counter(); runtime=live.Eira2Runtime(config,generate=adapter.generate,verify=live.verify_response); elapsed=time.perf_counter()-t
    out={'schema':'eira2_neural_postdeploy_verify_v1','ok':True,'mutates_live':False,'target_sha256':observed,'package_identity_ok':True,'package_tree_sha256':identity[1],'constructor_seconds':round(elapsed,3),'service_count':len(runtime.supervisor._records),'topological_order':runtime.supervisor.topological_order()}
except Exception as e:
    out={'schema':'eira2_neural_postdeploy_verify_v1','ok':False,'mutates_live':False,'error':f'{type(e).__name__}:{e}'}
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out['ok'] else 1)
