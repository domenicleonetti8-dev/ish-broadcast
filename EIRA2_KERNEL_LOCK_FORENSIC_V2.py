from __future__ import annotations
import json, os, pathlib, subprocess, hashlib
ROOT=pathlib.Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
def sha(p):
    try:return hashlib.sha256(p.read_bytes()).hexdigest()
    except:return None
def text(p):
    try:return p.read_text(errors='replace')
    except Exception as e:return f'<ERR:{type(e).__name__}:{e}>'
def ps():
    p=subprocess.run(['ps','-eo','pid=,ppid=,stat=,etimes=,cmd='],text=True,capture_output=True)
    rows=[]
    for line in (p.stdout or '').splitlines():
        low=line.lower()
        if 'eira' in low or 'main.py' in low:
            parts=line.strip().split(None,4)
            if len(parts)>=5: rows.append({'pid':parts[0],'ppid':parts[1],'stat':parts[2],'etimes':parts[3],'cmd':parts[4]})
    return rows
lockpy=ROOT/'eira2/kernel/lock.py'
suppy=ROOT/'eira2/kernel/supervisor.py'
cands=[]
for base in [ROOT/'eira_probe', ROOT/'eira2', ROOT]:
    try:
        for p in base.rglob('*'):
            if not p.is_file(): continue
            n=p.name.lower()
            if ('lock' in n or 'pid' in n or 'instance' in n) and p.stat().st_size < 100000:
                try:
                    rel=p.resolve().relative_to(ROOT).as_posix()
                except: continue
                cands.append({'path':rel,'bytes':p.stat().st_size,'sha256':sha(p),'content':text(p)[:4000]})
            if len(cands)>=80: break
    except Exception: pass
    if len(cands)>=80: break
out={'ok':True,'schema':'eira2_kernel_lock_forensic_v2','mutates_live':False,'root':str(ROOT),'lock_py':{'exists':lockpy.is_file(),'sha256':sha(lockpy),'source':text(lockpy)[:20000]},'supervisor_py':{'exists':suppy.is_file(),'sha256':sha(suppy),'source':text(suppy)[:12000]},'processes':ps(),'lock_candidates':cands}
print(json.dumps(out,separators=(',',':')))
