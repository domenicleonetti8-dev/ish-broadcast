#!/usr/bin/env python3
from __future__ import annotations
import asyncio,json,sys,time,traceback
from dataclasses import replace
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve(); sys.path.insert(0,str(ROOT))
MANIFEST=ROOT/'eira2-package-manifest.json'
PROMPTS=[
 ('greeting','How are you my friend? Answer naturally in one sentence.'),
 ('mechanism','Why does a metal spoon feel colder than a wooden spoon in the same room? Explain the mechanism, not just the answer.'),
 ('analogy','Explain voltage, current, and resistance with a water-system analogy, then say exactly where the analogy breaks down.'),
 ('transfer','If a city traffic network is like a neural network, what corresponds to synapses, inhibition, and plasticity? Give the analogy and two important limits.'),
 ('reasoning','A sealed box contains 3 red balls and 2 blue balls. Two balls are drawn without replacement. What is the probability both are red? Explain briefly.'),
 ('provenance','What components actually participated in producing this answer? Only claim what you can verify from the current runtime path.'),
 ('weird_science','Suppose gravity suddenly became 1% stronger for exactly 30 seconds worldwide. What immediate effects would be measurable, and what dramatic effects would probably NOT happen?')
]
async def main():
    import eira2.live as live
    from eira2.interfaces.ingress import InputKind
    runtime=None; started=False; rows=[]
    out={'schema':'eira2_real_organism_regression_v2','ok':False,'mutates_source_files':False,'runtime_state_activity_expected':True}
    try:
        target,tree=live._verified_live_identity(ROOT,MANIFEST)
        cfg=live.live_config(ROOT,MANIFEST,host='127.0.0.1',port=8782)
        cfg=replace(cfg,voice_enabled=False)
        containment=live.verify_private_model_containment(runtime_root=ROOT)
        adapter=live.OllamaCandidateAdapter(model='qwen2.5:3b',unix_socket=str(containment.get('unix_socket') or ''))
        t=time.perf_counter(); runtime=live.Eira2Runtime(cfg,generate=adapter.generate,verify=live.verify_response); out['construct_seconds']=round(time.perf_counter()-t,3)
        t=time.perf_counter(); await asyncio.wait_for(runtime.start(),timeout=180); out['start_seconds']=round(time.perf_counter()-t,3); started=True
        health=await runtime.supervisor.status(); failed=[]; health_rows={}
        for name,h in health.items():
            state=getattr(getattr(h,'state',None),'value',str(getattr(h,'state','')))
            detail=str(getattr(h,'detail',''))
            health_rows[name]={'state':state,'detail':detail}
            if state=='failed': failed.append(name)
        snap=runtime.registry.snapshot()
        bridges=snap.get('bridges',[]) if isinstance(snap,dict) else []
        nodes=snap.get('nodes',[]) if isinstance(snap,dict) else []
        out.update({'package_tree_sha256':tree,'model':'qwen2.5:3b','model_role':'private_candidate_only','service_count':len(health),'failed_services':failed,'health':health_rows,'registry_node_count':len(nodes),'registry_bridge_count':len(bridges),'conductive_bridge_count':sum(1 for b in bridges if isinstance(b,dict) and b.get('conductive') is True),'registry_bridges':bridges})
        for key,prompt in PROMPTS:
            t=time.perf_counter()
            try:
                result=await asyncio.wait_for(runtime.process(prompt,kind=InputKind.TERMINAL),timeout=180)
                rows.append({'key':key,'prompt':prompt,'ok':True,'seconds':round(time.perf_counter()-t,3),'response':str(result.response)})
            except Exception as e:
                rows.append({'key':key,'prompt':prompt,'ok':False,'seconds':round(time.perf_counter()-t,3),'error':f'{type(e).__name__}:{e}'})
        out['responses']=rows
        out['ok']=not failed and all(r.get('ok') and str(r.get('response') or '').strip() for r in rows)
    except Exception as e:
        out['error']=f'{type(e).__name__}:{e}'; out['traceback']=traceback.format_exc()[-8000:]; out['responses']=rows
    finally:
        if runtime is not None and started:
            try: await asyncio.wait_for(runtime.stop(),timeout=60); out['clean_stop']=True
            except Exception as e: out['clean_stop']=False; out['stop_error']=f'{type(e).__name__}:{e}'
    print(json.dumps(out,separators=(',',':')))
    return 0 if out.get('ok') else 1
raise SystemExit(asyncio.run(main()))
