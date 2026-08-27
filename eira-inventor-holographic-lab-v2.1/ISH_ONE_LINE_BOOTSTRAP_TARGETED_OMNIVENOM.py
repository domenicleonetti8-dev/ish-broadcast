#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, shutil, sys, tempfile, time, urllib.request
from pathlib import Path

SOURCE_COMMIT='dafdf47448f70cc99c74be2d5bb371ac13410dd2'
BASE=f'https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/{SOURCE_COMMIT}/eira-inventor-holographic-lab-v2.1/'
FILES={
'extensions/eira_inventor_holographic_lab/__init__.py':'6f92093a1d6c5dedf7be1f463e0afc571a1490f7a1cf113cc6dee5e45b53a346',
'extensions/eira_inventor_holographic_lab/blender_bridge.py':'ef034ee1f47a94e40a35b6a60b1b340ba527f5df6f41ac68015dd4abf8edcd32',
'extensions/eira_inventor_holographic_lab/engineering3d_bridge.py':'2129433a1ac4c47ec1f3522828fc5fc5fa3f6bb59af4dd6bdd8f5dccb34bda16',
'extensions/eira_inventor_holographic_lab/manifest.json':'930e091732365763222bdfa3f9e6227acf2d08a85f1c1906f497d15859b76fc1',
'extensions/eira_inventor_holographic_lab/omnivenom_node.json':'7652e8ae79da58042262353ed2db06949810c4b5389df1f45b7e365cd15364b7',
'extensions/eira_inventor_holographic_lab/plugin.py':'e420990112f4767d1ea0943c85290fcb86238f1a515e85a732710bce5038872e',
'extensions/eira_inventor_holographic_lab/server.py':'bb9fc1dfb59ff3ebcf4b14396a9c3de7ee5175ef58ee12a760341deb1ee96f76',
'extensions/eira_inventor_holographic_lab/static/index.html':'53ccaa2673f590d91ff62cb409f0d22d4fd1c6ca3c5699a3390dc98f796e0245'}
STAGE=Path(os.environ.get('EIRA_LAB_STAGE',str(Path.home()/'EIRA_INVENTOR_HOLOGRAPHIC_LAB_V2_1'))).expanduser().resolve()
NODE_ID='eira.inventor.holographic_lab'

def die(msg): raise SystemExit('EIRA iSH HOLOGRAPHIC LAB V2.1: '+msg)
def fetch(rel):
    dst=STAGE/rel; dst.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(BASE+rel,headers={'User-Agent':'EIRA-InventorLab-targeted-omnivenom'})
    with urllib.request.urlopen(req,timeout=60) as r: data=r.read(60_000_000)
    got=hashlib.sha256(data).hexdigest()
    if got!=FILES[rel]: die(f'HASH_MISMATCH {rel} {got}')
    dst.write_bytes(data)

for rel in FILES: fetch(rel)
for p in STAGE.rglob('*.py'): compile(p.read_text(encoding='utf-8'),str(p),'exec')
print('ISH_DOWNLOAD=PASS'); print('SOURCE_COMMIT='+SOURCE_COMMIT); print('STAGE='+str(STAGE))

candidates=[]
if os.environ.get('EIRA_LIVE'): candidates.append(Path(os.environ['EIRA_LIVE']).expanduser())
candidates += [Path('/media/domenicleonetti/easystore/EIRA/LIVE'),Path.home()/'EIRA'/'LIVE',Path.cwd()]
live=None
for c in candidates:
    try: c=c.resolve()
    except Exception: continue
    if (c/'extensions'/'omnivenom_mesh_ai'/'runtime.py').is_file() and (c/'extensions'/'unified_brain_ai'/'providers'/'engineering3d.py').is_file(): live=c; break
if live is None:
    print('LIVE_INSTALL=STAGED_ONLY'); print('REASON=No complete EIRA LIVE runtime is present inside this filesystem.'); sys.exit(0)

required=[live/'extensions'/'omnivenom_mesh_ai'/'runtime.py',live/'extensions'/'unified_brain_ai'/'providers'/'engineering3d.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'__init__.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'schema.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'validate.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'exploded.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'export.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'materials.py',live/'extensions'/'unified_brain_ai'/'engineering3d'/'physics.py']
for p in required:
    if not p.is_file(): die('required component missing: '+str(p))

target=live/'extensions'/'eira_inventor_holographic_lab'; source=STAGE/'extensions'/'eira_inventor_holographic_lab'; stamp=time.strftime('%Y%m%d_%H%M%S'); backup=None
main=live/'main.py'; before_main=hashlib.sha256(main.read_bytes()).hexdigest() if main.is_file() else None
if target.exists(): backup=target.with_name(target.name+'.bak_'+stamp); shutil.copytree(target,backup)

try:
    temp=Path(tempfile.mkdtemp(prefix='eira_lab_install_'))/target.name; shutil.copytree(source,temp)
    for p in temp.rglob('*.py'): compile(p.read_text(encoding='utf-8'),str(p),'exec')
    node=json.loads((temp/'omnivenom_node.json').read_text(encoding='utf-8'))
    if node.get('node_id')!=NODE_ID: die('node identity mismatch')
    if target.exists(): shutil.rmtree(target)
    shutil.copytree(temp,target)
    if before_main and hashlib.sha256(main.read_bytes()).hexdigest()!=before_main: die('protected main.py changed')

    sys.path.insert(0,str(live))
    from extensions.eira_inventor_holographic_lab import plugin
    st=plugin.status()
    if st.get('node_id')!=NODE_ID or st.get('core_modified') is not False: die('extension self-test failed')

    from extensions.eira_inventor_holographic_lab.engineering3d_bridge import provider_contract
    contract=provider_contract()
    print('ENGINEERING3D_CAPABILITY='+str(contract.get('capability')))
    print('ENGINEERING3D_ADVERTISED='+json.dumps(contract.get('advertised_capabilities',[]),sort_keys=True))
    if not contract.get('ok'): die('engineering3d contract unresolved: '+json.dumps(contract,default=str))

    from extensions.omnivenom_mesh_ai.runtime import Omnivenom
    mesh=Omnivenom(live)
    before_registered=mesh.registered_systems()
    print('OMNIVENOM_REGISTER_START')
    descriptor=dict(node)
    descriptor.update({
        'path':str(target),
        'entrypoint':'extensions.eira_inventor_holographic_lab.plugin',
        'engineering3d_capability':contract.get('capability'),
        'registration_mode':'targeted_system',
    })
    reg_result=mesh.register_system(NODE_ID,descriptor)
    print('OMNIVENOM_REGISTER_PASS')
    registered=mesh.registered_systems()
    blob=json.dumps(registered,default=str,sort_keys=True)
    if NODE_ID not in blob: die('OmniVenom targeted registration did not persist node')
    print('OMNIVENOM_REGISTERED_SYSTEMS_VERIFY=PASS')
finally:
    try: mesh.close()
    except Exception: pass

print('LIVE_INSTALL=PASS')
print('NODE_ID='+NODE_ID)
print('LIVE='+str(live))
print('ENGINEERING3D_ENTRYPOINT='+str(contract.get('entrypoint')))
print('ENGINEERING3D_SHA256='+str(contract.get('provider_sha256')))
print('ENGINEERING3D_CAPABILITY='+str(contract.get('capability')))
print('CAPABILITY_REQUEST='+str(contract.get('request_type'))+str(contract.get('request_signature')))
print('OMNIVENOM_REGISTRATION=TARGETED_PASS')
print('CORE_MAIN_PRESERVED=true')
print('START=cd '+str(live)+' && python3 -m extensions.eira_inventor_holographic_lab.server --host 127.0.0.1 --port 8787')
