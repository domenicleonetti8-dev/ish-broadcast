#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,shutil,sys,time,textwrap
from pathlib import Path

LIVE=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
EXT=LIVE/'extensions'/'eira_inventor_holographic_lab'
STAMP=time.strftime('%Y%m%d_%H%M%S')

def sha(p):
    if not p.exists(): return None
    h=hashlib.sha256();
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def put(rel,s):
    p=EXT/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(textwrap.dedent(s).lstrip(),encoding='utf-8')

def main():
    if not (LIVE/'extensions').is_dir(): raise SystemExit(f'not_eira_live:{LIVE}')
    core=LIVE/'main.py'; before=sha(core)
    archive=EXT/'inventions'
    preserved=None
    if archive.exists():
        preserved=LIVE/'extensions'/f'.inventor_archive_{STAMP}'
        if preserved.exists(): shutil.rmtree(preserved)
        shutil.copytree(archive,preserved)
    if EXT.exists():
        backup=LIVE/'extensions'/f'eira_inventor_holographic_lab.backup_{STAMP}'
        shutil.move(str(EXT),str(backup))
        print('BACKUP:',backup)
    EXT.mkdir(parents=True)
    put('__init__.py', """
from .pipeline import run_invention
__all__=['run_invention']
""")
    put('manifest.json', """
{
  "name":"eira_inventor_holographic_lab",
  "version":"5.1.0",
  "isolation":"extension-only",
  "entrypoint":"pipeline:run_invention",
  "outputs":["usdz","glb","inspection_report","invention_spec"],
  "benchmark":"V28 greenhouse complexity/continuity reference",
  "completion":"closed-loop build-inspect-repair-validate"
}
""")
    put('schema.py', r"""
from __future__ import annotations
from dataclasses import dataclass,field,asdict
from typing import Any
@dataclass
class Evidence:
    kind:str; source:str; confidence:float=1.0; notes:str=''
@dataclass
class Part:
    id:str; kind:str; geometry:dict; transform:dict=field(default_factory=dict); material:dict=field(default_factory=dict)
    parent:str|None=None; interfaces:list[dict]=field(default_factory=list); evidence:list[dict]=field(default_factory=list)
    engineering:dict=field(default_factory=dict); tags:list[str]=field(default_factory=list)
@dataclass
class Link:
    kind:str; source:str; target:str; path:list[list[float]]=field(default_factory=list); attrs:dict=field(default_factory=dict)
@dataclass
class InventionSpec:
    title:str; purpose:str=''; units:str='m'; parts:list[dict]=field(default_factory=list); links:list[dict]=field(default_factory=list)
    constraints:list[dict]=field(default_factory=list); assumptions:list[dict]=field(default_factory=list); equations:list[dict]=field(default_factory=list)
    source_images:list[str]=field(default_factory=list); provenance:dict=field(default_factory=dict)
    def dict(self): return asdict(self)
""")
    put('vision_contract.py', r"""
from __future__ import annotations
import json
SYSTEM='''You are the visual engineering interpreter for a generalized invention-to-3D system. Convert drawings/photos/descriptions into ONE JSON invention specification. Separate observed facts, user requirements, inferred design, and generative completion. Never claim an inferred dimension/material as observed. Build coherent geometry and connections, not decorative floating parts. Include supports, interfaces, routing endpoints, clearances, repeated structures, joints, controls, power/fluid/air/data paths where applicable. Prefer mathematically defined primitives, paths, extrusions, arrays and meshes. Output JSON only.'''

def prompt(description,images,prior=None,defects=None):
    return SYSTEM+'\nDESCRIPTION:\n'+description+'\nIMAGES:\n'+json.dumps(images)+'\nPRIOR:\n'+json.dumps(prior or {})+'\nDEFECTS:\n'+json.dumps(defects or [])

def parse(raw):
    s=raw.strip(); a=s.find('{'); b=s.rfind('}')
    if a<0 or b<a: raise ValueError('vision_no_json')
    x=json.loads(s[a:b+1])
    if not isinstance(x,dict) or not isinstance(x.get('parts',[]),list): raise ValueError('vision_bad_spec')
    return x
""")
    put('math_model.py', r"""
from __future__ import annotations
import math,copy

def v3(x,d=(0,0,0)):
    q=list(x or d); return [float(q[i] if i<len(q) else 0) for i in range(3)]
def expand(spec,max_parts=20000):
    out=[]
    for p in spec.get('parts',[]):
        pat=p.get('pattern') or {}; kind=pat.get('kind')
        if kind=='linear':
            n=max(1,int(pat.get('count',1))); step=v3(pat.get('step'))
            for i in range(n):
                q=copy.deepcopy(p); q.pop('pattern',None); q['id']=f"{p.get('id','part')}_{i:04d}"; t=q.setdefault('transform',{}); t['translate']=[a+i*b for a,b in zip(v3(t.get('translate')),step)]; out.append(q)
        elif kind=='grid':
            cnt=pat.get('count',[1,1,1]); step=pat.get('step',[[1,0,0],[0,1,0],[0,0,1]])
            for i in range(int(cnt[0])):
              for j in range(int(cnt[1])):
               for k in range(int(cnt[2])):
                q=copy.deepcopy(p); q.pop('pattern',None); q['id']=f"{p.get('id','part')}_{i}_{j}_{k}"; base=v3(q.setdefault('transform',{}).get('translate'))
                q['transform']['translate']=[base[a]+i*v3(step[0])[a]+j*v3(step[1])[a]+k*v3(step[2])[a] for a in range(3)]; out.append(q)
        elif kind=='radial':
            n=max(1,int(pat.get('count',1))); c=v3(pat.get('center')); r=float(pat.get('radius',1)); axis=str(pat.get('axis','z')).lower()
            for i in range(n):
                ang=2*math.pi*i/n; q=copy.deepcopy(p); q.pop('pattern',None); q['id']=f"{p.get('id','part')}_{i:04d}"; pos=[c[0]+r*math.cos(ang),c[1]+r*math.sin(ang),c[2]]
                if axis=='y': pos=[c[0]+r*math.cos(ang),c[1],c[2]+r*math.sin(ang)]
                if axis=='x': pos=[c[0],c[1]+r*math.cos(ang),c[2]+r*math.sin(ang)]
                q.setdefault('transform',{})['translate']=pos; out.append(q)
        else: out.append(copy.deepcopy(p))
        if len(out)>max_parts: raise ValueError('expanded_part_limit')
    z=copy.deepcopy(spec); z['parts']=out; return z
""")
    put('qa.py', r"""
from __future__ import annotations
import math

def finite3(v): return isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,(int,float)) and math.isfinite(float(x)) for x in v)
def validate(spec):
    defects=[]; ids=set()
    parts=spec.get('parts',[])
    for p in parts:
        i=str(p.get('id','')).strip()
        if not i or i in ids: defects.append({'kind':'identity','part':i,'issue':'missing_or_duplicate_id'})
        ids.add(i); g=p.get('geometry') or {}; method=g.get('method') or g.get('kind')
        if not method: defects.append({'kind':'geometry','part':i,'issue':'missing_geometry'})
        t=p.get('transform') or {}; tr=t.get('translate',[0,0,0]); sc=t.get('scale',[1,1,1])
        if not finite3(tr): defects.append({'kind':'transform','part':i,'issue':'bad_translate'})
        if not finite3(sc) or any(float(x)<=0 for x in sc): defects.append({'kind':'transform','part':i,'issue':'bad_scale'})
    for e in spec.get('links',[]):
        a=e.get('source'); b=e.get('target')
        if a not in ids or b not in ids: defects.append({'kind':'connectivity','link':e,'issue':'missing_endpoint'})
        if a==b: defects.append({'kind':'connectivity','link':e,'issue':'self_link'})
    for p in parts:
        tags=set(map(str,p.get('tags',[]))); eng=p.get('engineering') or {}; i=p.get('id')
        if ('rotating' in tags or p.get('kind') in ('turbine','fan','rotor')) and not (eng.get('axis') or eng.get('joint')):
            defects.append({'kind':'mechanical','part':i,'issue':'moving_part_missing_axis_or_joint'})
        if 'elevated' in tags and 'self_supporting' not in tags and not any(e.get('target')==i and e.get('kind') in ('supports','attached_to') for e in spec.get('links',[])):
            defects.append({'kind':'structural','part':i,'issue':'elevated_part_missing_support'})
    return defects
""")
    put('blender_builder.py', r"""
from __future__ import annotations
import json,math

def script_for(spec,out_glb,render_dir):
    data=json.dumps(spec)
    return f'''import bpy,math,json,os\nfrom mathutils import Vector\nS=json.loads({data!r})\nOUT={str(out_glb)!r}; RD={str(render_dir)!r}\nos.makedirs(RD,exist_ok=True)\nbpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)\ndef mat(m):\n n=str(m.get("name","mat")); x=bpy.data.materials.get(n) or bpy.data.materials.new(n); c=m.get("base_color",[.5,.5,.5,1]); x.diffuse_color=tuple((c+[1,1,1,1])[:4]); x.metallic=float(m.get("metallic",0)); x.roughness=float(m.get("roughness",.45)); return x\ndef add(p):\n g=p.get("geometry") or {{}}; k=(g.get("kind") or g.get("method") or "cube").lower(); prm=g.get("params") or {{}}\n if k in ("cube","box","primitive"):\n  bpy.ops.mesh.primitive_cube_add(); o=bpy.context.object\n elif k=="cylinder": bpy.ops.mesh.primitive_cylinder_add(vertices=int(prm.get("vertices",32)),radius=float(prm.get("radius",.5)),depth=float(prm.get("depth",1))); o=bpy.context.object\n elif k=="sphere": bpy.ops.mesh.primitive_uv_sphere_add(segments=int(prm.get("segments",32)),ring_count=int(prm.get("rings",16)),radius=float(prm.get("radius",.5))); o=bpy.context.object\n elif k=="cone": bpy.ops.mesh.primitive_cone_add(vertices=int(prm.get("vertices",32)),radius1=float(prm.get("radius1",.5)),radius2=float(prm.get("radius2",0)),depth=float(prm.get("depth",1))); o=bpy.context.object\n elif k=="torus": bpy.ops.mesh.primitive_torus_add(major_radius=float(prm.get("major_radius",.5)),minor_radius=float(prm.get("minor_radius",.1))); o=bpy.context.object\n else: bpy.ops.mesh.primitive_cube_add(); o=bpy.context.object\n o.name=str(p.get("id","part")); t=p.get("transform") or {{}}; o.location=tuple(t.get("translate",[0,0,0])); o.rotation_euler=tuple(math.radians(float(x)) for x in t.get("rotate_deg",[0,0,0])); o.scale=tuple(t.get("scale",[1,1,1])); o.data.materials.append(mat(p.get("material") or {{}}))\nfor p in S.get("parts",[]): add(p)\nP={{o.name:o for o in bpy.context.scene.objects}}\ndef seg(a,b,name,r=.02):\n a,b=Vector(a),Vector(b); d=b-a; L=d.length\n if L<1e-6:return\n bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=r,depth=L,location=(a+b)/2); o=bpy.context.object; o.name=name; o.rotation_mode="QUATERNION"; o.rotation_quaternion=d.to_track_quat("Z","Y")\nfor j,e in enumerate(S.get("links",[])):\n pts=e.get("path") or []; A=P.get(str(e.get("source"))); B=P.get(str(e.get("target")))\n if not pts and A and B: pts=[list(A.location),list(B.location)]\n elif pts and A and B: pts=[list(A.location)]+pts+[list(B.location)]\n for q in range(len(pts)-1): seg(pts[q],pts[q+1],f"link_{{j}}_{{q}}",float((e.get("attrs") or {{}}).get("radius",.02)))\nbpy.context.scene.render.engine="BLENDER_EEVEE_NEXT"\nobjs=[o for o in bpy.context.scene.objects if o.type=="MESH"]\nif objs:\n xs=[];ys=[];zs=[]\n for o in objs:\n  for c in o.bound_box:\n   w=o.matrix_world@Vector(c); xs.append(w.x);ys.append(w.y);zs.append(w.z)\n ctr=Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,(min(zs)+max(zs))/2)); size=max(max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs),1)\nelse: ctr=Vector((0,0,0)); size=5\nviews=[("front",(0,-1,0)),("rear",(0,1,0)),("left",(-1,0,0)),("right",(1,0,0)),("top",(0,0,1)),("iso1",(1,-1,.7)),("iso2",(-1,-1,.7)),("iso3",(1,1,.7))]\nfor n,d in views:\n bpy.ops.object.camera_add(location=ctr+Vector(d).normalized()*size*2.2); c=bpy.context.object; c.data.lens=52; c.rotation_euler=((ctr-c.location).to_track_quat("-Z","Y")).to_euler(); bpy.context.scene.camera=c; bpy.context.scene.render.resolution_x=768; bpy.context.scene.render.resolution_y=768; bpy.context.scene.render.filepath=os.path.join(RD,n+".png"); bpy.ops.render.render(write_still=True); bpy.data.objects.remove(c,do_unlink=True)\nbpy.ops.export_scene.gltf(filepath=OUT,export_format="GLB")\ntry: bpy.ops.wm.usd_export(filepath=os.path.splitext(OUT)[0]+".usdc")\nexcept Exception as e: print("USD_EXPORT_WARNING",e)\n'''
""")
    put('export_usdz.py', r"""
from __future__ import annotations
import zipfile
from pathlib import Path

def package(usdc,out):
    usdc=Path(usdc); out=Path(out)
    if not usdc.exists(): raise FileNotFoundError(usdc)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as z: z.write(usdc,arcname='model.usdc')
    with zipfile.ZipFile(out,'r') as z:
        if z.namelist()!=['model.usdc'] or z.getinfo('model.usdc').compress_type!=zipfile.ZIP_STORED: raise ValueError('bad_usdz_package')
    return out
""")
    put('pipeline.py', r"""
from __future__ import annotations
import json,subprocess
from pathlib import Path
from .vision_contract import prompt,parse
from .math_model import expand
from .qa import validate
from .blender_builder import script_for
from .export_usdz import package

def call_vision(provider,description,images,prior=None,defects=None):
    r=provider(prompt(description,images,prior,defects))
    if isinstance(r,dict): return r
    if hasattr(r,'text'): r=r.text
    return parse(str(r))

def run_invention(*,description,images,output_dir,vision_provider,blender='blender',max_repairs=4):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); renders=out/'inspection'; renders.mkdir(exist_ok=True)
    spec=call_vision(vision_provider,description,[str(x) for x in images]); defects=[]; history=[]
    for attempt in range(max_repairs+1):
        spec=expand(spec); defects=validate(spec); (out/'invention_spec.json').write_text(json.dumps(spec,indent=2))
        if defects:
            history.append({'attempt':attempt,'phase':'preflight','defects':defects}); spec=call_vision(vision_provider,description,[str(x) for x in images],spec,defects); continue
        glb=out/'model.glb'; py=out/'build_scene.py'; py.write_text(script_for(spec,glb,renders)); subprocess.run([blender,'-b','--python',str(py)],check=True)
        visual={'task':'inspect_rendered_invention','views':[str(p) for p in sorted(renders.glob('*.png'))],'requirements':['no floating geometry','no broken pipes/wires','no impossible intersections','supports for elevated systems','coherent moving assemblies','reference fidelity','material/detail completeness']}
        vr=vision_provider(visual)
        if hasattr(vr,'text'): vr=vr.text
        if isinstance(vr,str):
            try: vr=parse(vr)
            except Exception: vr={'defects':[{'kind':'vision','issue':'malformed_visual_inspection'}]}
        vdef=(vr or {}).get('defects',[]); history.append({'attempt':attempt,'phase':'visual','defects':vdef})
        if vdef and attempt<max_repairs: spec=call_vision(vision_provider,description,[str(x) for x in images],spec,vdef); continue
        usdc=out/'model.usdc'
        if not usdc.exists(): raise RuntimeError('blender_did_not_export_usd')
        usdz=package(usdc,out/'model.usdz'); report={'status':'accepted','attempts':attempt+1,'parts':len(spec.get('parts',[])),'links':len(spec.get('links',[])),'history':history,'glb':str(glb),'usdz':str(usdz)}
        (out/'inspection_report.json').write_text(json.dumps(report,indent=2)); return report
    raise RuntimeError('repair_budget_exhausted:'+json.dumps(defects)[:1200])
""")
    put('SELF_TEST.py', r"""
from math_model import expand
from qa import validate
s={'parts':[{'id':'rib','kind':'structure','geometry':{'kind':'cylinder','params':{'radius':.03,'depth':2}},'transform':{'translate':[0,0,0],'scale':[1,1,1]},'pattern':{'kind':'linear','count':100,'step':[.2,0,0]}}],'links':[]}
x=expand(s); assert len(x['parts'])==100; assert validate(x)==[]; print('EIRA_INVENTOR_V5_SELF_TEST_PASS',len(x['parts']))
""")
    if preserved and preserved.exists(): shutil.copytree(preserved,EXT/'inventions',dirs_exist_ok=True)
    after=sha(core)
    if before!=after: raise SystemExit('CORE_HASH_CHANGED_ABORT')
    import py_compile
    for p in EXT.glob('*.py'): py_compile.compile(str(p),doraise=True)
    subprocess_ok=os.system(f"cd {EXT} && {sys.executable} SELF_TEST.py")
    if subprocess_ok: raise SystemExit('SELF_TEST_FAILED')
    print('INSTALL_PASS:',EXT)
    print('CORE_SHA256:',after)
    print('VERSION:5.1.0 closed-loop generalized invention -> inspected USDZ')
if __name__=='__main__': main()
