from __future__ import annotations
import ast, hashlib, json, os, sys
from pathlib import Path

ROOT = Path(os.environ.get('EIRA_LIVE_ROOT','/media/domenicleonetti/easystore/EIRA/LIVE')).resolve()
SOURCE = ROOT / 'eira_probe' / 'transport_runtime_v6' / 'repo' / 'EIRA2_UNIVERSE_LIBRARY_FULL_REPLACEMENT_V2.py'
EXPECTED_TARGET = 'eira2/evidence/universe_library.py'

def literal(name: str):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f'literal_missing:{name}')

def main():
    if not SOURCE.is_file(): raise RuntimeError(f'source_missing:{SOURCE}')
    target=literal('TARGET'); payload=literal('NEW')
    if target!=EXPECTED_TARGET: raise RuntimeError(f'target_mismatch:{target}')
    compile(payload,target,'exec')
    ns={'__name__':'eira2_universe_library_payload_qualification'}
    exec(compile(payload,target,'exec'),ns,ns)
    result=ns['self_test_25x2']()
    out={
      'schema':'eira2_universe_library_exact_checkout_25x2_v3',
      'source_path':str(SOURCE),
      'wrapper_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
      'payload_sha256':hashlib.sha256(payload.encode('utf-8')).hexdigest(),
      'target':target,
      'qualification':result,
      'pass':bool(result.get('pass') and result.get('clean_passes')==50 and result.get('total')==50 and result.get('distinct_tests')==25 and result.get('rounds')==2),
      'mutates_live':False
    }
    print(json.dumps(out,indent=2,sort_keys=True))
    raise SystemExit(0 if out['pass'] else 1)
if __name__=='__main__': main()
