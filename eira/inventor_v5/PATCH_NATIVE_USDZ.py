#!/usr/bin/env python3
from pathlib import Path
import py_compile

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'

export_code=r'''
from __future__ import annotations
from pathlib import Path
import math,struct,zlib,time

def _safe(s):
    s=''.join(c if c.isalnum() or c=='_' else '_' for c in str(s))
    if not s or s[0].isdigit(): s='p_'+s
    return s

def _v3(v,default):
    q=list(v or default)
    return [float(q[i] if i<len(q) else default[i]) for i in range(3)]

def _rgba(m):
    c=list((m or {}).get('base_color',[0.5,0.5,0.5,1]))
    while len(c)<4:c.append(1.0)
    return [max(0.0,min(1.0,float(x))) for x in c[:4]]

def write_usda(spec,path):
    path=Path(path)
    lines=['#usda 1.0','(','    defaultPrim = "Root"','    metersPerUnit = 1','    upAxis = "Z"',')','','def Xform "Root"','{']
    mats={}
    for p in spec.get('parts',[]):
        m=p.get('material') or {}; key=str(m.get('name') or ('mat_'+_safe(p.get('id','part'))))
        mats.setdefault(key,m)
    if mats:
        lines += ['    def Scope "Looks"','    {']
        for name,m in mats.items():
            r,g,b,a=_rgba(m); rough=float(m.get('roughness',0.45)); metal=float(m.get('metallic',0.0))
            n=_safe(name)
            lines += [f'        def Material "{n}"', '        {', f'            token outputs:surface.connect = </Root/Looks/{n}/Preview.outputs:surface>', f'            def Shader "Preview"', '            {', '                uniform token info:id = "UsdPreviewSurface"', f'                color3f inputs:diffuseColor = ({r:.6f}, {g:.6f}, {b:.6f})', f'                float inputs:opacity = {a:.6f}', f'                float inputs:roughness = {rough:.6f}', f'                float inputs:metallic = {metal:.6f}', '                token outputs:surface', '            }', '        }']
        lines += ['    }']
    for p in spec.get('parts',[]):
        pid=_safe(p.get('id','part')); g=p.get('geometry') or {}; kind=str(g.get('kind') or g.get('method') or 'cube').lower(); prm=g.get('params') or {}; t=p.get('transform') or {}
        tr=_v3(t.get('translate'),[0,0,0]); rot=_v3(t.get('rotate_deg'),[0,0,0]); sc=_v3(t.get('scale'),[1,1,1]); mat=_safe((p.get('material') or {}).get('name') or ('mat_'+pid))
        lines += [f'    def Xform "{pid}"','    {',f'        double3 xformOp:translate = ({tr[0]}, {tr[1]}, {tr[2]})',f'        float3 xformOp:rotateXYZ = ({rot[0]}, {rot[1]}, {rot[2]})',f'        float3 xformOp:scale = ({sc[0]}, {sc[1]}, {sc[2]})','        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]']
        if kind in ('cube','box','primitive'):
            lines += ['        def Cube "Geom"','        {','            double size = 2']
        elif kind=='sphere':
            lines += ['        def Sphere "Geom"','        {',f'            double radius = {float(prm.get("radius",0.5))}']
        elif kind=='cylinder':
            lines += ['        def Cylinder "Geom"','        {','            uniform token axis = "Z"',f'            double radius = {float(prm.get("radius",0.5))}',f'            double height = {float(prm.get("depth",1.0))}']
        elif kind=='cone':
            lines += ['        def Cone "Geom"','        {','            uniform token axis = "Z"',f'            double radius = {float(prm.get("radius1",prm.get("radius",0.5)))}',f'            double height = {float(prm.get("depth",1.0))}']
        else:
            lines += ['        def Cube "Geom"','        {','            double size = 2']
        lines += [f'            rel material:binding = </Root/Looks/{mat}>','        }','    }']
    lines += ['}']
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return path

def package(root_layer,out):
    root_layer=Path(root_layer); out=Path(out)
    data=root_layer.read_bytes(); name=root_layer.name.encode('utf-8'); crc=zlib.crc32(data)&0xffffffff
    tm=time.localtime(); dostime=((tm.tm_hour&31)<<11)|((tm.tm_min&63)<<5)|((tm.tm_sec//2)&31); dosdate=(((tm.tm_year-1980)&127)<<9)|((tm.tm_mon&15)<<5)|(tm.tm_mday&31)
    base=30+len(name)
    pad=(64-(base%64))%64
    extra=(b'' if pad==0 else struct.pack('<HH',0xFFFF,max(0,pad-4))+b'\0'*max(0,pad-4))
    if len(extra)!=pad: extra=b'\0'*pad
    local=struct.pack('<IHHHHHIIIHH',0x04034b50,20,0,0,dostime,dosdate,crc,len(data),len(data),len(name),len(extra))+name+extra
    offset=0
    central=struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,20,20,0,0,dostime,dosdate,crc,len(data),len(data),len(name),0,0,0,0,0,offset)+name
    cd_offset=len(local)+len(data); cd_size=len(central)
    end=struct.pack('<IHHHHIIH',0x06054b50,0,0,1,1,cd_size,cd_offset,0)
    out.write_bytes(local+data+central+end)
    raw=out.read_bytes(); data_start=30+len(name)+len(extra)
    if data_start%64!=0: raise ValueError('usdz_alignment_failed')
    if raw[:4]!=b'PK\x03\x04': raise ValueError('usdz_bad_zip')
    return out
'''

pipeline_code=r'''
from __future__ import annotations
import json,subprocess,shutil,os
from pathlib import Path
from .vision_contract import prompt,parse
from .math_model import expand
from .qa import validate
from .blender_builder import script_for
from .export_usdz import package,write_usda

def call_vision(provider,description,images,prior=None,defects=None):
    r=provider(prompt(description,images,prior,defects))
    if isinstance(r,dict): return r
    if hasattr(r,'text'): r=r.text
    return parse(str(r))

def _blender_cmd(blender,py):
    base=[blender,'-b','--python',str(py)]
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        xvfb=shutil.which('xvfb-run')
        if xvfb: return [xvfb,'-a']+base
    return base

def run_invention(*,description,images,output_dir,vision_provider,blender='blender',max_repairs=4):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); renders=out/'inspection'; renders.mkdir(exist_ok=True)
    spec=call_vision(vision_provider,description,[str(x) for x in images]); defects=[]; history=[]
    for attempt in range(max_repairs+1):
        spec=expand(spec); defects=validate(spec); (out/'invention_spec.json').write_text(json.dumps(spec,indent=2))
        if defects:
            history.append({'attempt':attempt,'phase':'preflight','defects':defects}); spec=call_vision(vision_provider,description,[str(x) for x in images],spec,defects); continue
        glb=out/'model.glb'; py=out/'build_scene.py'; py.write_text(script_for(spec,glb,renders)); subprocess.run(_blender_cmd(blender,py),check=True)
        visual={'task':'inspect_rendered_invention','views':[str(p) for p in sorted(renders.glob('*.png'))],'requirements':['no floating geometry','no broken pipes/wires','no impossible intersections','supports for elevated systems','coherent moving assemblies','reference fidelity','material/detail completeness']}
        vr=vision_provider(visual)
        if hasattr(vr,'text'): vr=vr.text
        if isinstance(vr,str):
            try: vr=parse(vr)
            except Exception: vr={'defects':[{'kind':'vision','issue':'malformed_visual_inspection'}]}
        vdef=(vr or {}).get('defects',[]); history.append({'attempt':attempt,'phase':'visual','defects':vdef})
        if vdef and attempt<max_repairs: spec=call_vision(vision_provider,description,[str(x) for x in images],spec,vdef); continue
        usda=write_usda(spec,out/'model.usda'); usdz=package(usda,out/'model.usdz')
        report={'status':'accepted','attempts':attempt+1,'parts':len(spec.get('parts',[])),'links':len(spec.get('links',[])),'history':history,'glb':str(glb),'usda':str(usda),'usdz':str(usdz),'usd_source':'native_usda_no_pxr'}
        (out/'inspection_report.json').write_text(json.dumps(report,indent=2)); return report
    raise RuntimeError('repair_budget_exhausted:'+json.dumps(defects)[:1200])
'''

(EXT/'export_usdz.py').write_text(export_code,encoding='utf-8')
(EXT/'pipeline.py').write_text(pipeline_code,encoding='utf-8')
py_compile.compile(str(EXT/'export_usdz.py'),doraise=True)
py_compile.compile(str(EXT/'pipeline.py'),doraise=True)
print('NATIVE_USDZ_PATCH_PASS')
