from __future__ import annotations

import math, struct, time, zipfile
from pathlib import Path
from typing import Any

GOLDEN = math.pi * (3.0 - math.sqrt(5.0))
SCHEMA = "eira2_luminous_neural_organism_apple_ar_v7"


def _nid(row: dict[str, Any]) -> str:
    return str(row.get("_id") or row.get("id") or "")


def _all(atlas: Any):
    neurons=[dict(x) for x in (atlas.page(cursor=0,limit=5000,include_paths=False).get("neurons") or []) if isinstance(x,dict)]
    fibers=[dict(x) for x in ((atlas.fibers_for(limit=30000) or {}).get("fibers") or []) if isinstance(x,dict)]
    seen={_nid(x) for x in neurons if _nid(x)}
    for f in fibers:
        for key in ("source","target"):
            ident=str(f.get(key) or "")
            if ident and ident not in seen:
                row=atlas.neuron(ident)
                if row: neurons.append(dict(row)); seen.add(ident)
    return neurons,fibers


def _positions(neurons):
    left=[n for n in neurons if n.get("hemisphere")=="left" and not n.get("spine")]
    right=[n for n in neurons if n.get("hemisphere")=="right" and not n.get("spine")]
    mid=[n for n in neurons if n not in left and n not in right]
    out={}
    def side(items,sign):
        total=max(1,len(items))
        for i,row in enumerate(sorted(items,key=_nid)):
            u=(i+.5)/total; z=1-2*u; rr=math.sqrt(max(0,1-z*z)); th=i*GOLDEN+(0 if sign<0 else math.pi/7)
            p=[sign*(.04+.90*abs(rr*math.cos(th))),.94*rr*math.sin(th),.94*z]
            ln=math.sqrt(sum(v*v for v in p)) or 1; shell=.88+.06*((i%13)/12)
            out[_nid(row)]=tuple(v/ln*shell for v in p)
    side(left,-1); side(right,1)
    spine=[r for r in mid if r.get("spine")]; other=[r for r in mid if not r.get("spine")]
    for i,row in enumerate(sorted(spine,key=_nid)):
        t=.5 if len(spine)==1 else i/max(1,len(spine)-1); out[_nid(row)]=(0,0,-.94+1.88*t)
    for i,row in enumerate(sorted(other,key=_nid)):
        a=i*GOLDEN; r=.18+.10*((i%9)/8); out[_nid(row)]=(r*math.cos(a),r*math.sin(a),-.22+.44*((i%17)/16))
    return out


def _group(groups,name):
    return groups.setdefault(name,{"points":[],"counts":[],"indices":[]})

def _oct(groups,name,c,r):
    g=_group(groups,name); b=len(g["points"]); x,y,z=c
    g["points"] += [(x+r,y,z),(x-r,y,z),(x,y+r,z),(x,y-r,z),(x,y,z+r),(x,y,z-r)]
    for f in ((0,2,4),(2,1,4),(1,3,4),(3,0,4),(2,0,5),(1,2,5),(3,1,5),(0,3,5)):
        g["counts"].append(3); g["indices"] += [b+i for i in f]

def _norm(v):
    L=math.sqrt(sum(a*a for a in v)) or 1; return tuple(a/L for a in v)

def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def _prism(groups,name,a,b,r=.0015,sides=6):
    axis=(b[0]-a[0],b[1]-a[1],b[2]-a[2]); L=math.sqrt(sum(v*v for v in axis))
    if L<1e-7:return
    w=_norm(axis); ref=(0,0,1) if abs(w[2])<.85 else (0,1,0); u=_norm(_cross(w,ref)); v=_cross(w,u)
    g=_group(groups,name); base=len(g["points"])
    for p in (a,b):
        for i in range(sides):
            ang=2*math.pi*i/sides; off=tuple(r*(math.cos(ang)*u[k]+math.sin(ang)*v[k]) for k in range(3)); g["points"].append(tuple(p[k]+off[k] for k in range(3)))
    for i in range(sides):
        j=(i+1)%sides; g["counts"].append(4); g["indices"] += [base+i,base+j,base+sides+j,base+sides+i]
    g["counts"].append(sides); g["indices"] += [base+i for i in reversed(range(sides))]
    g["counts"].append(sides); g["indices"] += [base+sides+i for i in range(sides)]


def _material(lines,name,rgb,emit):
    lines += [f'        def Material "{name}" {{',f'            token outputs:surface.connect = </Brain/Looks/{name}/S.outputs:surface>','            def Shader "S" {','                uniform token info:id = "UsdPreviewSurface"',f'                color3f inputs:diffuseColor = ({rgb[0]}, {rgb[1]}, {rgb[2]})',f'                color3f inputs:emissiveColor = ({emit[0]}, {emit[1]}, {emit[2]})','                float inputs:roughness = 0.14','                token outputs:surface','            }','        }']


def write_brain_usda(atlas: Any, path: Path) -> Path:
    neurons,fibers=_all(atlas); pos=_positions(neurons); groups={}; palette=("Azure","Cyan","Violet","Magenta","Gold","White")
    ordered=sorted((r for r in neurons if _nid(r) in pos),key=_nid)
    for i,row in enumerate(ordered):
        ident=_nid(row); p=pos[ident]; mat="Gold" if any(k in ident.casefold() for k in ("core","kernel","supervisor")) else palette[i%len(palette)]
        _oct(groups,mat,p,.014 if row.get("spine") else (.020 if mat=="Gold" else .009))
    for i,f in enumerate(fibers):
        s,t=str(f.get("source") or ""),str(f.get("target") or "")
        if s in pos and t in pos and s!=t: _prism(groups,"Cyan" if f.get("conductive") else "Azure",pos[s],pos[t],.0017 if f.get("conductive") else .0010)
    # spinal current and cognition roots are cosmetic, non-authoritative visual tissue
    spine=[(0,0,-.96+1.92*i/80) for i in range(81)]
    for i in range(80): _prism(groups,"White" if 27<i<53 else "Cyan",spine[i],spine[i+1],.0050)
    for phase,mat in ((0,"Violet"),(math.pi,"Gold")):
        pts=[]
        for i in range(140):
            u=i/139; a=phase+u*math.pi*9; pts.append((.048*math.cos(a),.048*math.sin(a),-.94+1.88*u))
        for i in range(len(pts)-1): _prism(groups,mat,pts[i],pts[i+1],.0021)
    for r,m in ((.18,"Gold"),(.12,"White"),(.065,"Gold")): _oct(groups,m,(0,0,0),r)
    lines=['#usda 1.0','(','    defaultPrim = "Brain"','    metersPerUnit = 1','    upAxis = "Z"',')','','def Xform "Brain" {','    def Scope "Looks" {']
    mats={"Azure":((.02,.32,1),(.05,.56,1)),"Cyan":((.01,.82,1),(.04,1,1)),"Violet":((.36,.02,1),(.66,.10,1)),"Magenta":((1,.02,.64),(1,.08,.82)),"Gold":((1,.45,.01),(1,.86,.04)),"White":((.88,.98,1),(1,1,1))}
    for n,(rgb,e) in mats.items(): _material(lines,n,rgb,e)
    lines += ['    }']
    def pts(v): return ',\n                '.join(f'({x:.6f}, {y:.6f}, {z:.6f})' for x,y,z in v)
    def ints(v): return ',\n                '.join(', '.join(str(x) for x in v[i:i+32]) for i in range(0,len(v),32))
    for n,g in groups.items():
        if not g['points']: continue
        lines += [f'    def Mesh "Mesh_{n}" {{',f'        point3f[] points = [\n                {pts(g["points"])}\n        ]',f'        int[] faceVertexCounts = [\n                {ints(g["counts"])}\n        ]',f'        int[] faceVertexIndices = [\n                {ints(g["indices"])}\n        ]','        uniform token subdivisionScheme = "none"',f'        rel material:binding = </Brain/Looks/{n}>','    }']
    lines += ['}']; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if not ordered: raise ValueError('apple_ar_no_canonical_neurons')
    return path


def package_usdz(root_layer: Path, output: Path) -> Path:
    data=root_layer.read_bytes(); name=root_layer.name.encode(); base=30+len(name); pad=(-base)%64
    if 0<pad<4: pad+=64
    extra=b'' if not pad else struct.pack('<HH',0xFFFF,pad-4)+b'\0'*(pad-4)
    zi=zipfile.ZipInfo(root_layer.name,time.localtime()[:6]); zi.compress_type=zipfile.ZIP_STORED; zi.extra=extra; zi.external_attr=0o644<<16
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as zf: zf.writestr(zi,data)
    with zipfile.ZipFile(output,'r') as zf:
        if zf.testzip() is not None: raise ValueError('apple_ar_usdz_integrity_failed')
        info=zf.infolist()[0]; offset=info.header_offset+30+len(info.filename.encode())+len(info.extra)
        if offset%64: raise ValueError('apple_ar_usdz_alignment_failed')
    return output


def build_brain_usdz(atlas: Any, output: Path) -> Path:
    temp=output.with_suffix('.usda'); write_brain_usda(atlas,temp); result=package_usdz(temp,output)
    try: temp.unlink()
    except OSError: pass
    return result
