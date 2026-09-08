from __future__ import annotations
import ast, hashlib, json, os
from pathlib import Path
ROOT=Path(os.environ.get('EIRA_LIVE_ROOT','/media/domenicleonetti/easystore/EIRA/LIVE')).resolve()
SOURCE=ROOT/'eira_probe'/'transport_runtime_v6'/'repo'/'EIRA2_UNIVERSE_LIBRARY_FULL_REPLACEMENT_V3.py'
EXPECTED='eira2/evidence/universe_library.py'
def lit(name):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets): return ast.literal_eval(node.value)
    raise RuntimeError('literal_missing:'+name)
def main():
    if not SOURCE.is_file(): raise RuntimeError('source_missing:'+str(SOURCE))
    target=lit('TARGET'); payload=lit('NEW')
    if target!=EXPECTED: raise RuntimeError('target_mismatch:'+target)
    compile(payload,target,'exec'); ns={'__name__':'eira2_universe_library_payload_qualification'}; exec(compile(payload,target,'exec'),ns,ns)
    result=ns['self_test_25x2'](); passed=bool(result.get('pass') and result.get('clean_passes')==50 and result.get('total')==50 and result.get('distinct_tests')==25 and result.get('rounds')==2)
    out={'schema':'eira2_universe_library_exact_checkout_25x2_v4','target':target,'wrapper_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),'qualification':result,'pass':passed,'mutates_live':False}
    print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if passed else 1)
if __name__=='__main__': main()
