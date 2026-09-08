from __future__ import annotations
import json, os, sqlite3, time
from pathlib import Path

ROOT=Path(os.environ.get('EIRA_LIVE_ROOT','/media/domenicleonetti/easystore/EIRA/LIVE')).resolve()
BASE=ROOT/'eira_probe'/'universe_library'
VAULT=BASE/'source_vault'
DB=VAULT/'source_index.sqlite3'
OUT=BASE/'tiny_library_heartbeat.json'

def snap():
    out={'schema':'eira2_tiny_library_heartbeat_v1','ts':time.time(),'ok':True,'mutates_live':False}
    try:
        db=sqlite3.connect(f'file:{DB}?mode=ro',uri=True,timeout=3)
        out['works']=int(db.execute('SELECT COUNT(*) FROM works').fetchone()[0])
        out['documents']=int(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0])
        out['works_by_source']={str(a):int(b) for a,b in db.execute('SELECT source_name,COUNT(*) FROM works GROUP BY source_name')}
        db.close()
    except Exception as e:
        out['ok']=False; out['db_error']=f'{type(e).__name__}:{e}'
    texts=VAULT/'project_gutenberg'/'texts'
    out['gutenberg_extracted_text_files']=sum(1 for _ in texts.rglob('*.txt')) if texts.is_dir() else 0
    return out

def main():
    while True:
        data=snap(); tmp=OUT.with_suffix('.tmp'); tmp.write_text(json.dumps(data,sort_keys=True)); os.replace(tmp,OUT); print(json.dumps(data,sort_keys=True),flush=True); time.sleep(2)

if __name__=='__main__': main()
