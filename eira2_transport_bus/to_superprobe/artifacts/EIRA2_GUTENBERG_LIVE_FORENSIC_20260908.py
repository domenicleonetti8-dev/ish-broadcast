from __future__ import annotations
import json, os, subprocess
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
OUT={'schema':'eira2_gutenberg_live_forensic_v1','read_only':True}

def text(p:Path):
    try: return p.read_text(errors='replace')
    except Exception as e: return f'ERROR:{type(e).__name__}:{e}'

def method_block(path:Path, name:str):
    s=text(path)
    if s.startswith('ERROR:'): return s
    lines=s.splitlines(); start=None
    for i,l in enumerate(lines):
        if l.lstrip().startswith(f'def {name}('): start=i; break
    if start is None: return 'NOT_FOUND'
    out=[]; indent=len(lines[start])-len(lines[start].lstrip())
    for j in range(start, min(len(lines), start+140)):
        l=lines[j]
        if j>start and l.strip() and (len(l)-len(l.lstrip()))<=indent and l.lstrip().startswith('def '): break
        out.append(f'{j+1}: {l}')
    return '\n'.join(out)

u=ROOT/'eira2/evidence/universe_public_library.py'
g=ROOT/'eira2/evidence/gutenberg_refresh.py'
st=ROOT/'eira_probe/universe_library/gutenberg_refresh_state.json'
log=ROOT/'eira_probe/universe_library/mass_stock_gutenberg.log'
idxlog=ROOT/'eira_probe/universe_library/gutenberg_index.log'
bulk=ROOT/'eira_probe/universe_library/source_vault/project_gutenberg/bulk/txt-files.tar.zip'
OUT['paths']={k:{'exists':p.exists(),'size':p.stat().st_size if p.exists() and p.is_file() else None} for k,p in {'library_source':u,'refresh_source':g,'refresh_state':st,'stock_log':log,'index_log':idxlog,'bulk_archive':bulk}.items()}
OUT['refresh_state']=text(st)
OUT['download_method']=method_block(u,'download_gutenberg_full_text_archive')
OUT['extract_method']=method_block(u,'extract_gutenberg_full_text_archive')
OUT['catalog_method']=method_block(u,'ingest_gutenberg_catalog')
OUT['run_due']=method_block(g,'run_due')
for key,p in [('stock_log_tail',log),('index_log_tail',idxlog)]:
    t=text(p); OUT[key]='\n'.join(t.splitlines()[-80:])
try:
    ps=subprocess.run(['ps','-eo','pid,etime,stat,cmd'],capture_output=True,text=True,timeout=5)
    OUT['processes']='\n'.join(x for x in ps.stdout.splitlines() if 'universe_library' in x or 'gutenberg' in x)
except Exception as e: OUT['processes']=f'ERROR:{type(e).__name__}:{e}'
print(json.dumps(OUT,indent=2,sort_keys=True))
