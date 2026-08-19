#!/usr/bin/env python3
from __future__ import annotations

import base64, hashlib, json, os, pathlib, py_compile, shutil, sys, tarfile, tempfile, time, urllib.request

LIVE=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '/media/domenicleonetti/easystore/EIRA/LIVE').expanduser().resolve()
BASE_COMMIT='8d2158c982adcd87852c65562ee9bc71bbc7864e'
BASE_BRANCH_PATH='_eira_v440_payload'
BASE_TAR_SHA='0d1dc66798b55f38dc762cb6224eaeb03fc186e31e4ad7b2da4453a0cdcb09d0'
FINAL_BRANCH='eira-v4.4.0-dominant-brain-final'
OVERLAYS={
 'omnivenom_bridge.py':'a7a5543c5ff7b93fa0703d6a947043ecb0a2d09114a40e8e26d492ddb15b05cd',
 'dominant_host.py':'eff297fd159d7de6919633412b4fd4f9870822b8a0c2461b3d58d8021d7cb4e9',
 'dominant_runtime.py':'878fb319191e51f5102fef3d99655cafc0d06f9d5b63a66902b5b1b53e0803a6',
}

def die(s): raise SystemExit('EIRA DOMINANT INSTALL: '+s)
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(p): return sha_bytes(pathlib.Path(p).read_bytes())
def get(url,limit):
    req=urllib.request.Request(url,headers={'User-Agent':'Eira-Dominant-Takeover-v4.4.1'})
    with urllib.request.urlopen(req,timeout=60) as r: b=r.read(limit+1)
    if len(b)>limit: die('download size limit exceeded')
    return b

def safe_extract(arc,out,limit=80*1024*1024):
    out.mkdir(parents=True,exist_ok=True); total=0
    with tarfile.open(arc,'r:xz') as tf:
        ms=tf.getmembers()
        if not ms or len(ms)>800: die('base archive member count rejected')
        for m in ms:
            p=pathlib.PurePosixPath(m.name)
            if p.is_absolute() or not p.parts or '..' in p.parts: die('unsafe archive path: '+m.name)
            if m.isdir(): m.mode=0o755
            elif m.isfile():
                if m.mode & 0o7000: die('privileged archive mode: '+m.name)
                total += m.size
                m.mode=0o755 if (m.mode&0o111) else 0o644
            else: die('unsafe archive member: '+m.name)
        if total>limit: die('base archive expansion limit exceeded')
        tf.extractall(out,members=ms)

def verify_base(root):
    man=root/'SHA256SUMS.txt'
    if not man.is_file(): die('base manifest missing')
    lines=[x for x in man.read_text().splitlines() if x.strip()]
    if len(lines)!=300: die(f'expected 300 base manifest entries, got {len(lines)}')
    seen=set()
    for line in lines:
        digest,rel=line.split('  ',1)
        if rel in seen: die('duplicate base manifest path: '+rel)
        seen.add(rel); p=(root/rel).resolve()
        if root.resolve() not in p.parents: die('base manifest path escape: '+rel)
        if not p.is_file() or sha_file(p)!=digest: die('base manifest mismatch: '+rel)
    return len(lines)

def patch_plugin(dst):
    p=dst/'plugin.py'; s=p.read_text()
    if 'DominantEiraHostBridge' not in s:
        s=s.replace('from .live_host_bridge import LiveEiraHostBridge','from .dominant_host import DominantEiraHostBridge')
        s=s.replace('_host = LiveEiraHostBridge()','_host = DominantEiraHostBridge()')
    if '"main_takeover": True' not in s:
        s=s.replace('"direct_core_rewrite": False,','"direct_core_rewrite": False,\n        "main_takeover": True,\n        "legacy_router_used": False,')
    p.write_text(s); py_compile.compile(str(p),doraise=True)

def configure(dst):
    cfg=json.loads((dst/'config.example.json').read_text())
    data=LIVE/'data/unified_brain'; data.mkdir(parents=True,exist_ok=True)
    cfg.setdefault('agency',{}).update({
      'enabled':True,'mode':'bounded_autonomous','state_path':str(data/'experience.sqlite3'),
      'self_generated_goals':True,'post_turn_reflection':True,'safe_autonomous_actions':True,
      'max_open_goals':24,'external_mutation_requires_current_turn_authorization':True,
      'identity_self_rewrite':False,'core_self_rewrite':False})
    cfg.setdefault('memory',{}).update({'enabled':True,'mode':'selective','path':str(data/'memory.sqlite3')})
    cfg.setdefault('audit',{})['path']=str(data/'audit.jsonl')
    cfg.setdefault('receipts',{})['path']=str(data/'receipts.jsonl')
    cfg.setdefault('automations',{})['path']=str(data/'automations.sqlite3')
    cfg.setdefault('knowledge',{})['path']=str(data/'knowledge.sqlite3')
    if isinstance(cfg.get('providers'),dict) and isinstance(cfg['providers'].get('neural_fabric'),dict):
        cfg['providers']['neural_fabric']['enabled']=False
    (dst/'live_config.json').write_text(json.dumps(cfg,indent=2,sort_keys=True)+'\n')

def load_base(work):
    local=os.environ.get('EIRA_DOMINANT_BASE_LOCAL','').strip()
    if local:
        root=pathlib.Path(local).expanduser().resolve()
        verify_base(root); return root
    encoded=b''
    for i in range(5):
        url=f'https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{BASE_COMMIT}/{BASE_BRANCH_PATH}/source.chunk0{i}'
        encoded += get(url,30000)
    try: blob=base64.b64decode(encoded,validate=False)
    except Exception as exc: die('base64 reconstruction failed: '+str(exc))
    if sha_bytes(blob)!=BASE_TAR_SHA: die('sealed v4.4.0 base SHA mismatch')
    arc=work/'base.tar.xz'; arc.write_bytes(blob); out=work/'base'; safe_extract(arc,out)
    root=out/'eira_unified_brain_v4_4_0'
    verify_base(root); return root

def load_overlays(work):
    local=os.environ.get('EIRA_DOMINANT_OVERLAY_LOCAL','').strip()
    out=work/'overlay'; out.mkdir()
    for name,want in OVERLAYS.items():
        if local: b=(pathlib.Path(local)/name).read_bytes()
        else:
            url=f'https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{FINAL_BRANCH}/dominant_overlay/{name}'
            b=get(url,100000)
        if sha_bytes(b)!=want: die('overlay SHA mismatch: '+name)
        (out/name).write_bytes(b)
    return out

if not (LIVE/'main.py').is_file(): die('LIVE/main.py missing')
if not (LIVE/'extensions/omnivenom_mesh_ai').is_dir(): die('OmniVenom is not installed in LIVE/extensions/omnivenom_mesh_ai')

with tempfile.TemporaryDirectory(prefix='eira-dominant-') as td:
    work=pathlib.Path(td); root=load_base(work); overlay=load_overlays(work)
    src=root/'extensions/unified_brain_ai'
    for p in src.rglob('*.py'): py_compile.compile(str(p),doraise=True)
    for p in overlay.glob('*.py'): py_compile.compile(str(p),doraise=True)

    stamp=time.strftime('%Y%m%d-%H%M%S')
    main=LIVE/'main.py'; original_sha=sha_file(main)
    main_backup=LIVE/f'main.py.pre_dominant_takeover.{stamp}'
    shutil.copy2(main,main_backup)
    if sha_file(main_backup)!=original_sha: die('main.py backup verification failed')

    extroot=LIVE/'extensions'; dst=extroot/'unified_brain_ai'; ext_backup=None
    if dst.exists():
        ext_backup=extroot/f'unified_brain_ai.pre_dominant_takeover.{stamp}'
        shutil.move(str(dst),str(ext_backup))
    shutil.copytree(src,dst)
    for p in overlay.glob('*.py'): shutil.copy2(p,dst/p.name)
    patch_plugin(dst); configure(dst)

    launcher='''#!/usr/bin/env python3\nfrom extensions.unified_brain_ai.dominant_runtime import main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'''
    tmp=LIVE/'.main.py.dominant.tmp'; tmp.write_text(launcher); py_compile.compile(str(tmp),doraise=True); os.chmod(tmp,0o755); os.replace(tmp,main)

    sys.path.insert(0,str(LIVE)); os.environ['EIRA_LIVE_ROOT']=str(LIVE); os.environ['EIRA_DOMINANT_TAKEOVER']='1'
    from extensions.unified_brain_ai import plugin
    check=plugin.self_test()
    if not check.get('ok'): die('Unified Brain self-test failed: '+repr(check))
    status=plugin.status()
    if status.get('host',{}).get('legacy_router_used') is not False: die('legacy router was not bypassed')

    data=LIVE/'data/unified_brain'
    receipt={'ok':True,'version':'4.4.1-dominant-takeover','base_verified_files':300,'live':str(LIVE),
      'main_backup':str(main_backup),'main_backup_sha256':original_sha,'extension_backup':str(ext_backup) if ext_backup else None,
      'omnivenom':str(LIVE/'extensions/omnivenom_mesh_ai'),'dominant_brain':str(dst),'legacy_router_authority':False,
      'main_takeover':True,'agency':'bounded_autonomous','voice':'native_endpoint_or_existing_voice_module'}
    rp=data/f'install_receipt_{stamp}.json'; rp.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print('EIRA_DOMINANT_INSTALL=PASS')
    print('MAIN_BACKUP='+str(main_backup)); print('RECEIPT='+str(rp))
