#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, json, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, urllib.request

LIVE=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
def die(s): raise SystemExit('EIRA INSTALL: '+s)
def sha(b): return hashlib.sha256(b).hexdigest()
def get(url,limit=250000):
    req=urllib.request.Request(url,headers={'User-Agent':'Eira-v4.3.7-symbiosis-installer'})
    with urllib.request.urlopen(req,timeout=45) as r: b=r.read(limit+1)
    if len(b)>limit: die('download size limit exceeded')
    return b
def verify_manifest(root,expected=None):
    m=root/'SHA256SUMS.txt'
    if not m.is_file(): die('SHA256SUMS.txt missing')
    lines=[x for x in m.read_text().splitlines() if x.strip()]
    if expected is not None and len(lines)!=expected: die(f'expected {expected} manifest entries, got {len(lines)}')
    seen=set()
    for line in lines:
        d,rel=line.split('  ',1)
        if rel in seen: die('duplicate manifest path: '+rel)
        seen.add(rel); p=(root/rel).resolve()
        if p!=root and root not in p.parents: die('manifest path escape: '+rel)
        if not p.is_file() or sha(p.read_bytes())!=d: die('manifest hash mismatch: '+rel)
    if expected is not None:
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS.txt' and '__pycache__' not in p.parts and not p.name.endswith('.pyc')}
        if actual!=seen: die(f'inventory mismatch missing={sorted(seen-actual)} extra={sorted(actual-seen)}')
    return len(lines)

def safe_extract(arc,out,limit=50*1024*1024):
    out.mkdir(parents=True,exist_ok=True); total=0
    with tarfile.open(arc,'r:xz') as tf:
        ms=tf.getmembers()
        if not ms or len(ms)>600: die('archive member count rejected')
        for m in ms:
            p=pathlib.PurePosixPath(m.name)
            if p.is_absolute() or not p.parts or '..' in p.parts: die('unsafe archive path: '+m.name)
            if m.isdir(): m.mode=0o755
            elif m.isfile():
                if m.mode&0o7000: die('privileged archive mode: '+m.name)
                m.mode=0o755 if (m.mode&0o111) else 0o644; total+=m.size
            else: die('unsafe archive member: '+m.name)
        if total>limit: die('archive expansion limit exceeded')
        tf.extractall(out,members=ms)

def part_bytes(s,name,size,want):
    mirror=os.environ.get('EIRA_RAW_MIRROR_DIR','').strip()
    if mirror: b=(pathlib.Path(mirror)/s['repo']/s['ref']/s['path']/name).read_bytes()
    else: b=get(f"https://raw.githubusercontent.com/{s['repo']}/{s['ref']}/{s['path']}/{name}",size)
    if len(b)!=size or sha(b)!=want: die(f"{s['label']} transport verification failed: {name}")
    return b

def overlay(work,root,s):
    enc=b''.join(part_bytes(s,*p) for p in s['parts'])
    if sha(enc)!=s['b64']: die(s['label']+' combined transport SHA mismatch')
    blob=base64.b64decode(enc,validate=True)
    if sha(blob)!=s['delta']: die(s['label']+' delta SHA mismatch')
    area=work/('overlay-'+s['label']); area.mkdir(); arc=area/'d.tar.xz'; arc.write_bytes(blob); out=area/'x'; safe_extract(arc,out,25*1024*1024)
    metas=list(out.rglob('DELTA_META.json'))
    if len(metas)!=1: die(s['label']+' delta metadata rejected')
    dr=metas[0].parent; meta=json.loads(metas[0].read_text())
    if meta.get('deletes'): die(s['label']+' unexpected delete directives')
    n=0
    for src in sorted(dr.rglob('*')):
        if src==metas[0] or src.is_dir(): continue
        if src.is_symlink() or not src.is_file(): die(s['label']+' unsafe overlay object')
        rel=src.relative_to(dr); dst=(root/rel).resolve()
        if dst!=root and root not in dst.parents: die(s['label']+' overlay escape')
        dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_name(dst.name+'.venomtmp'); shutil.copyfile(src,tmp); os.chmod(tmp,0o755 if os.access(src,os.X_OK) else 0o644); os.replace(tmp,dst); n+=1
    print(f"EIRA v4.3.7: {s['label']} verified overlay files={n}")

if not (LIVE/'main.py').is_file(): die('protected LIVE main.py missing: '+str(LIVE))
if not (LIVE/'extensions/local_brain/router.py').is_file(): die('LIVE local_brain router missing')
sets=[
 {'label':'v4.3.6','repo':'domenicleonetti8-dev/ish-broadcast','ref':'6f3071f0c3faf038bb3fdcac3e69e581eb219a7a','path':'eira-release/v4.3.6','b64':'40489b9e79fab787cd0abb4b1dc7bd6834d359729c31f8d678999980b4433660','delta':'dae0e290ed3a9039e0405ad97e755efd16e99ce1df4768677e23b24f2beaabd6','parts':[('delta435.b64.part00',12000,'2f1759b7f065f6cebe6a1383a7b55aaa0ca135989063aa04735f4ee7133f09d2'),('delta435.b64.part01a',6000,'bd5355228221c2fc6986cfd50a92c3671aa5c595d8046f7c47df3604cadddd9f'),('delta435.b64.part01b0',3000,'aba9f31171139de67118e1c2c840bab5b3105f9324b5afbec9466e8187fee23e'),('delta435.b64.part01b1',3000,'4d915f03fdb3355aa7ea46e3552ba97fa2e02cfb2dd34416e0ab2660f5239fcd'),('delta435.b64.part02',12000,'13df54668288623996f32674938f97f2346d785d4c07f915da2fdc85a0df976e'),('delta435.b64.part03',12000,'a6d7368ae80b626337e060f04d11276e6de4aa85d950233d3e70aef1e2c81b01'),('delta435.b64.part04',2412,'f66e30a7199c6e6b2bcf0013285cc046116e1577a82bdeffdea6c9b576ec2b33')]},
 {'label':'v4.3.7','repo':'domenicleonetti8-dev/ish-broadcast','ref':'eira-release','path':'eira-release/v4.3.7','b64':'c16582589d063f3d917b43cec9f736ab6cefe7ed66e83e56b338ed4451fefdfb','delta':'8446e667fc35c6d80470af37b365b935b4d0c16bb519d53fd48f6a56d72dbb8a','parts':[('delta437.b64.part00',8000,'977f8aab72aa83931981f331feaacab8beeb19be90ed6536da6f2fec48bb7ad6'),('delta437.b64.part01',8000,'d29c4bc4a9440ddbfbad70c66813124fd269104ac9aec72f8eaf06c8fc9088f0'),('delta437.b64.part02',8000,'f2ca2f12823f7b58462154585fa246d352021478e9f12b1d410fdd6986bd34f9'),('delta437.b64.part03',8000,'2d3fc607fde61531936287e93c69919da4b49ea942cee38321328bc6ec47a2eb'),('delta437.b64.part04',8000,'e37231b6ae07ba922db0d3257f7c2ba27abffa7ea8005935046119e6999809d9'),('delta437.b64.part05',5200,'1c09e1725f3412a5025fd35498e4b64dd79533299a59566e9bce187495287445')]}
]
with tempfile.TemporaryDirectory(prefix='eira-v437-') as td:
    work=pathlib.Path(td); root=work/'eira_unified_brain_v4_3_7'
    local=os.environ.get('EIRA_V435_RUNTIME_LOCAL','').strip()
    if local:
        out=work/'base'; safe_extract(pathlib.Path(local),out); roots=[p for p in out.iterdir() if p.is_dir()]
        if len(roots)!=1: die('local v4.3.5 root ambiguity')
        roots[0].rename(root)
    else:
        print('EIRA v4.3.7: reconstructing verified v4.3.5 body from pinned Git source...')
        src=get('https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/82242e979af0e84fcc394f676a1cbce8f45410d3/eira-install-v4.3.5-full-symbiote.sh')
        txt=src.decode(); needle="printf 'EIRA v4.3.5: transactional install"; pos=txt.find(needle)
        if pos<0: die('v4.3.5 export boundary not found')
        exp=work/'export.sh'; exp.write_text(txt[:pos]+'\nrm -rf -- "$EXPORT_ROOT"\ncp -a -- "$ROOT" "$EXPORT_ROOT"\n'); exp.chmod(0o700)
        env=os.environ.copy(); env['EXPORT_ROOT']=str(root); subprocess.run(['bash',str(exp),str(LIVE)],check=True,env=env)
    verify_manifest(root)
    for s in sets: overlay(work,root,s)
    if verify_manifest(root,149)!=149: die('final manifest count failed')
    req=['extensions/unified_brain_ai/venom_bridge.py','extensions/unified_brain_ai/legacy_context.py','extensions/unified_brain_ai/quality.py','extensions/unified_brain_ai/neural_web/scanner.py','extensions/unified_brain_ai/providers/legacy_live.py','deploy/bind_live_venom.py','deploy/discover_live_integration.py','deploy/install_pi_extension.sh']
    for rel in req:
        if not (root/rel).is_file(): die('required symbiosis component missing: '+rel)
    if 'generic_assistant_voice' not in (root/'extensions/unified_brain_ai/quality.py').read_text(): die('global generic-response integrity gate missing')
    if 'EIRA_VENOM_BIND_V4_3_7_BEGIN' not in (root/'deploy/bind_live_venom.py').read_text(): die('v4.3.7 bind missing')
    if not any('EIRA_LIVE_SYMBIOTE' in p.read_text(errors='ignore') for p in (root/'extensions/unified_brain_ai/neural_web').glob('*.py')): die('whole-LIVE symbiote scanner missing')
    before=sha((LIVE/'main.py').read_bytes()); print('EIRA v4.3.7: transactional whole-Eira symbiosis install...')
    subprocess.run(['bash',str(root/'deploy/install_pi_extension.sh'),str(LIVE)],check=True)
    if sha((LIVE/'main.py').read_bytes())!=before: die('protected main.py changed')
    router=(LIVE/'extensions/local_brain/router.py').read_text()
    if router.count('EIRA_VENOM_BIND_V4_3_7_BEGIN')!=1 or '_VENOM_SAFE_HOST_FALLBACK_V4_3_7' not in router: die('installed Venom bind invalid')
    cp=subprocess.run([sys.executable,str(root/'deploy/discover_live_integration.py'),str(LIVE)],check=True,text=True,capture_output=True); obj=json.loads(cp.stdout); blob=json.dumps(obj,sort_keys=True)
    for term in ['4.3.7','full_symbiotic_fabric_v2']:
        if term not in blob: die('discovery missing '+term)
    for key in ['bound','host_preserved','safe_host_fallback']:
        if f'"{key}": true' not in blob: die('discovery did not prove '+key+'=true')
    if '"main_rewrite_required": false' not in blob: die('discovery did not prove main_rewrite_required=false')
print('EIRA v4.3.7: VERIFIED SYMBIOSIS-COMPLETE INSTALL')
print('LIVE:',LIVE)
