from pathlib import Path
import json, hashlib, os, time

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
critical=[
    'main.py',
    'eira2',
    'extensions',
    'eira_probe',
    'eira_probe/transport_runtime_v10/EIRA2_AUTONOMOUS_TRANSPORT_V10.py',
]

result={
    'schema':'eira2_live_integrity_readonly_v1',
    'generated_unix':time.time(),
    'root':str(ROOT),
    'mutates_live':False,
    'exists':ROOT.exists(),
    'critical':{},
    'errors':[],
}

try:
    for rel in critical:
        p=ROOT/rel
        result['critical'][rel]={'exists':p.exists(),'is_file':p.is_file(),'is_dir':p.is_dir()}
    files=[]
    py=[]
    zero_py=[]
    for p in ROOT.rglob('*'):
        try:
            if p.is_file():
                files.append(p)
                if p.suffix=='.py':
                    py.append(p)
                    if p.stat().st_size==0:
                        zero_py.append(str(p.relative_to(ROOT)))
        except OSError as e:
            result['errors'].append({'path':str(p),'error':f'{type(e).__name__}:{e}'})
    result['file_count']=len(files)
    result['python_file_count']=len(py)
    result['zero_byte_python_files']=zero_py
    result['ok']=bool(result['exists'] and result['critical']['main.py']['exists'] and not result['errors'])
except OSError as e:
    result['ok']=False
    result['errors'].append({'path':str(ROOT),'error':f'{type(e).__name__}:{e}'})

print(json.dumps(result,sort_keys=True))
