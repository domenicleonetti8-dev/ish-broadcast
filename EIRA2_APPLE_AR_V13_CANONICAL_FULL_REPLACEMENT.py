from __future__ import annotations

import math
import time
import zipfile
from pathlib import Path
from typing import Any

SCHEMA = "eira2_living_neural_organism_v13_apple_ar_safe"
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


class _Mesh:
    def __init__(self, name: str) -> None:
        self.name = name
        self.points: list[tuple[float, float, float]] = []
        self.counts: list[int] = []
        self.indices: list[int] = []

    def face(self, pts: list[tuple[float, float, float]]) -> None:
        base = len(self.points)
        self.points.extend(pts)
        self.counts.append(len(pts))
        self.indices.extend(range(base, base + len(pts)))


def _vadd(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _vsub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _vmul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _norm(a):
    length = math.sqrt(_dot(a, a))
    return (0.0, 0.0, 1.0) if length < 1e-9 else (a[0]/length, a[1]/length, a[2]/length)


_ICO_V = [
    (-1,1.618,0),(1,1.618,0),(-1,-1.618,0),(1,-1.618,0),
    (0,-1,1.618),(0,1,1.618),(0,-1,-1.618),(0,1,-1.618),
    (1.618,0,-1),(1.618,0,1),(-1.618,0,-1),(-1.618,0,1),
]
_ICO_V = [_norm(v) for v in _ICO_V]
_ICO_F = [
    (0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),(1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),
    (3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),(4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1),
]


def _soma(bucket: _Mesh, center, radius: float) -> None:
    base = len(bucket.points)
    bucket.points.extend([_vadd(center, _vmul(v, radius)) for v in _ICO_V])
    for f in _ICO_F:
        bucket.counts.append(3)
        bucket.indices.extend([base + f[0], base + f[1], base + f[2]])


def _tube(bucket: _Mesh, a, b, r0: float, r1: float | None = None, sides: int = 6) -> None:
    if r1 is None:
        r1 = r0
    d = _vsub(b, a)
    length = math.sqrt(_dot(d, d))
    if length < 1e-6:
        return
    w = _norm(d)
    ref = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (0.0, 1.0, 0.0)
    u = _norm(_cross(w, ref))
    v = _norm(_cross(w, u))
    ring_a, ring_b = [], []
    for i in range(sides):
        ang = 2.0 * math.pi * i / sides
        dv = _vadd(_vmul(u, math.cos(ang)), _vmul(v, math.sin(ang)))
        ring_a.append(_vadd(a, _vmul(dv, r0)))
        ring_b.append(_vadd(b, _vmul(dv, r1)))
    base = len(bucket.points)
    bucket.points.extend(ring_a + ring_b)
    for i in range(sides):
        j = (i + 1) % sides
        bucket.counts.append(4)
        bucket.indices.extend([base+i, base+j, base+sides+j, base+sides+i])


def _box(bucket: _Mesh, center, scale) -> None:
    x,y,z = center; sx,sy,sz = scale
    pts = [
        (x-sx,y-sy,z-sz),(x+sx,y-sy,z-sz),(x+sx,y+sy,z-sz),(x-sx,y+sy,z-sz),
        (x-sx,y-sy,z+sz),(x+sx,y-sy,z+sz),(x+sx,y+sy,z+sz),(x-sx,y+sy,z+sz),
    ]
    for f in ((0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(4,0,3,7)):
        bucket.face([pts[i] for i in f])


def _sphere_mesh(bucket: _Mesh, radius: float, lat_steps: int = 12, lon_steps: int = 24, squash=(1.0,1.0,1.0)) -> None:
    pts = [(0.0,0.0,radius*squash[2])]
    for lat in range(1, lat_steps):
        phi = math.pi * lat / lat_steps
        sp, cp = math.sin(phi), math.cos(phi)
        for lon in range(lon_steps):
            th = 2.0 * math.pi * lon / lon_steps
            pts.append((radius*sp*math.cos(th)*squash[0], radius*sp*math.sin(th)*squash[1], radius*cp*squash[2]))
    south = len(pts)
    pts.append((0.0,0.0,-radius*squash[2]))
    base = len(bucket.points)
    bucket.points.extend(pts)
    for lon in range(lon_steps):
        a=base+1+lon; b=base+1+(lon+1)%lon_steps
        bucket.counts.append(3); bucket.indices.extend([base,a,b])
    rings=lat_steps-1
    for r in range(rings-1):
        b0=base+1+r*lon_steps; b1=base+1+(r+1)*lon_steps
        for lon in range(lon_steps):
            a=b0+lon; c=b0+(lon+1)%lon_steps; d=b1+(lon+1)%lon_steps; e=b1+lon
            bucket.counts.append(4); bucket.indices.extend([a,c,d,e])
    last=base+1+(rings-1)*lon_steps
    for lon in range(lon_steps):
        a=last+lon; b=last+(lon+1)%lon_steps
        bucket.counts.append(3); bucket.indices.extend([a,base+south,b])


def _fmt_pts(points):
    return ",\n                ".join(f"({x:.6f}, {y:.6f}, {z:.6f})" for x,y,z in points)


def _fmt_ints(values, width: int = 30):
    return ",\n                ".join(", ".join(str(v) for v in values[i:i+width]) for i in range(0, len(values), width))


def write_brain_usda(atlas: Any, path: Path) -> Path:
    palette = {
        "Azure":((0.008,0.30,1.00),(0.03,0.65,1.00)),
        "Cyan":((0.003,0.82,1.00),(0.04,1.00,1.00)),
        "Violet":((0.38,0.01,1.00),(0.75,0.05,1.00)),
        "Magenta":((1.00,0.01,0.62),(1.00,0.08,0.88)),
        "Rose":((1.00,0.03,0.28),(1.00,0.14,0.42)),
        "Amber":((1.00,0.22,0.003),(1.00,0.66,0.02)),
        "Gold":((1.00,0.48,0.008),(1.00,0.95,0.05)),
        "White":((0.90,0.99,1.00),(1.00,1.00,1.00)),
        "FleshOuter":((0.025,0.090,0.240),(0.015,0.100,0.300)),
        "FleshMid":((0.120,0.025,0.260),(0.220,0.040,0.500)),
        "FleshInner":((0.020,0.240,0.340),(0.020,0.420,0.600)),
        "PoleSeal":((0.020,0.20,0.50),(0.060,0.55,0.95)),
    }
    meshes = {name:_Mesh(name) for name in palette}
    nodes=[]
    specs=[(520,0.94,0.0078),(300,0.82,0.0065),(140,0.69,0.0055)]
    colors=["Azure","Cyan","Violet","Magenta","Rose","Amber","Gold","White"]
    for shell,(count,radius,base_size) in enumerate(specs):
        for i in range(count):
            u=(i+0.5)/count; z=1.0-2.0*u; rr=math.sqrt(max(0.0,1.0-z*z)); theta=i*GOLDEN+shell*0.47
            x=radius*rr*math.cos(theta); y=radius*rr*math.sin(theta); zz=radius*z
            x += (-1.0 if x<0 else 1.0)*0.020*(1.0-abs(z))
            p=(x,y,zz); material=colors[(i*5+shell*2)%len(colors)]
            size=base_size*(2.8 if i%(31-shell*4)==0 else 1.6 if i%13==0 else 1.0)
            _soma(meshes[material],p,size)
            nodes.append((f"n{shell}_{i}",p,material,shell))
    seen=set()
    for shell in range(3):
        subset=[n for n in nodes if n[3]==shell]
        near_count=4 if shell==0 else 3
        for idx,n in enumerate(subset):
            near=sorted(((math.dist(n[1],q[1]),q) for q in subset if q[0]!=n[0]), key=lambda x:x[0])[:near_count]
            for rank,(_,q) in enumerate(near):
                key=tuple(sorted((n[0],q[0])))
                if key in seen: continue
                seen.add(key)
                a=n[1]; c=q[1]; m=tuple((a[k]+c[k])/2 for k in range(3)); ml=math.sqrt(_dot(m,m)) or 1.0
                bend=(0.008+rank*0.003)*(-1 if (idx+rank)%2 else 1)
                ctrl=tuple(m[k]+m[k]/ml*bend for k in range(3)); r=0.0011 if shell==0 else 0.0009
                _tube(meshes[n[2]],a,ctrl,r,r*0.78,6); _tube(meshes[n[2]],ctrl,c,r*0.78,r*0.55,6)
    outer=[n for n in nodes if n[3]==0]; middle=[n for n in nodes if n[3]==1]; inner=[n for n in nodes if n[3]==2]
    for stride,src,dst,ma,mb in ((6,outer,middle,"Cyan","Violet"),(5,middle,inner,"Magenta","Azure")):
        for i,n in enumerate(src[::stride]):
            q=min(dst,key=lambda x:math.dist(n[1],x[1])); _tube(meshes[ma if i%2==0 else mb],n[1],q[1],0.00095,0.00065,6)
    left=[n for n in outer if n[1][0]<-0.14]; right=[n for n in outer if n[1][0]>0.14]
    for j in range(72):
        a=left[(j*11)%len(left)][1]; q=min(right,key=lambda n:abs(n[1][1]-a[1])+abs(n[1][2]-a[2]))[1]
        c1=(a[0]*0.35,a[1]*0.76,a[2]*0.76); c2=(q[0]*0.35,q[1]*0.76,q[2]*0.76); mat="Gold" if j%5==0 else "Cyan" if j%2==0 else "Magenta"
        _tube(meshes[mat],a,c1,0.0014,0.0017,6); _tube(meshes[mat],c1,c2,0.0017,0.0017,6); _tube(meshes[mat],c2,q,0.0017,0.0014,6)
    for r,mat in ((0.18,"Amber"),(0.13,"Gold"),(0.085,"White"),(0.045,"Amber")):
        total=60 if r>0.08 else 30
        for i in range(total):
            u=(i+0.5)/total; z=1-2*u; rr=math.sqrt(max(0,1-z*z)); th=i*GOLDEN
            _soma(meshes[mat],(r*rr*math.cos(th),r*rr*math.sin(th),r*z),0.013 if r>0.08 else 0.011)
        _soma(meshes[mat],(0,0,0),r*0.40)
    for j in range(36):
        az=2*math.pi*j/36; elev=-0.62+1.24*((j%11)/10); rr=math.sqrt(max(0.08,1-elev*elev)); t=(0.64*rr*math.cos(az),0.64*rr*math.sin(az),0.64*elev)
        c1=_vmul(t,0.28); c2=_vmul(t,0.62); mat="Amber" if j%3==0 else "Gold"
        _tube(meshes[mat],(0,0,0),c1,0.0050,0.0038,7); _tube(meshes[mat],c1,c2,0.0038,0.0024,7); _tube(meshes[mat],c2,t,0.0024,0.0008,7)
    spine=[(0,0,-0.97+1.94*i/79) for i in range(80)]
    for i in range(len(spine)-1): _tube(meshes["White" if 28<i<52 else "Cyan"],spine[i],spine[i+1],0.0048,0.0048,8)
    for phase,mat in ((0,"Violet"),(math.pi,"Gold")):
        pts=[(0.048*math.cos(phase+t*math.pi*9.5),0.048*math.sin(phase+t*math.pi*9.5),-0.94+1.88*t) for t in (i/119 for i in range(120))]
        for i in range(len(pts)-1): _tube(meshes[mat],pts[i],pts[i+1],0.0021,0.0021,6)
    for floor in range(5):
        z=-0.12+floor*0.06; r=0.19+floor*0.024
        for k in range(24):
            a=2*math.pi*k/24+floor*0.13; p=(r*math.cos(a),r*math.sin(a),z); _box(meshes["Gold" if k%6==0 else "Azure"],p,(0.0045,0.0075,0.0027))
        ring=[(r*math.cos(2*math.pi*k/32),r*math.sin(2*math.pi*k/32),z) for k in range(32)]
        for k in range(32): _tube(meshes["Gold" if floor%2==0 else "Cyan"],ring[k],ring[(k+1)%32],0.0014,0.0014,6)
    _sphere_mesh(meshes["FleshOuter"],0.985,12,24,(1,1,1))
    _sphere_mesh(meshes["FleshMid"],0.865,12,24,(1,1,0.985))
    _sphere_mesh(meshes["FleshInner"],0.745,12,24,(1,1,0.970))
    _sphere_mesh(meshes["PoleSeal"],0.235,8,16,(1,1,0.10))
    # A second cap is translated in USDA as a separate mesh copy below.
    lines=["#usda 1.0","(",'    defaultPrim = "Brain"',"    metersPerUnit = 1",'    upAxis = "Z"',"    startTimeCode = 0","    endTimeCode = 3600","    timeCodesPerSecond = 30",")","",'def Xform "Brain"',"{",
           '    custom string eira:visualSchema = "eira2_living_neural_organism_v13_apple_ar_safe"',
           '    custom string eira:activityAuthority = "EIRA2 NeuralActivity/evidenced execution trace"',
           '    custom string eira:activityVisual = "canonical_runtime_electrical_path_highlighting"',
           '    float3 xformOp:rotateXYZ.timeSamples = { 0:(0,0,0), 900:(90,180,90), 1800:(180,360,180), 2700:(270,540,270), 3600:(360,720,360) }',
           '    uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]','    def Scope "Looks"','    {']
    for name,(rgb,emit) in palette.items():
        opacity=0.09 if name=="FleshOuter" else 0.06 if name=="FleshMid" else 0.045 if name=="FleshInner" else 0.18 if name=="PoleSeal" else 1.0
        lines += [f'        def Material "{name}"',"        {",f'            token outputs:surface.connect = </Brain/Looks/{name}/S.outputs:surface>','            def Shader "S"',"            {",'                uniform token info:id = "UsdPreviewSurface"',f'                color3f inputs:diffuseColor = ({rgb[0]:.6f}, {rgb[1]:.6f}, {rgb[2]:.6f})',f'                color3f inputs:emissiveColor = ({emit[0]:.6f}, {emit[1]:.6f}, {emit[2]:.6f})',f'                float inputs:opacity = {opacity:.6f}',"                float inputs:roughness = 0.14","                token outputs:surface","            }","        }"]
    lines += ["    }"]
    for name,bucket in meshes.items():
        if not bucket.points: continue
        if name=="PoleSeal":
            for label,z in (("NorthPoleSeal",0.955),("SouthPoleSeal",-0.955)):
                lines += [f'    def Xform "{label}"',"    {",f'        double3 xformOp:translate = (0,0,{z:.6f})','        uniform token[] xformOpOrder = ["xformOp:translate"]',f'        def Mesh "{name}Tissue"',"        {",'            uniform token subdivisionScheme = "none"','            point3f[] points = [',f'                {_fmt_pts(bucket.points)}',"            ]",'            int[] faceVertexCounts = [',f'                {_fmt_ints(bucket.counts)}',"            ]",'            int[] faceVertexIndices = [',f'                {_fmt_ints(bucket.indices)}',"            ]",f'            rel material:binding = </Brain/Looks/{name}>',"        }","    }"]
        else:
            lines += [f'    def Mesh "{name}Tissue"',"    {",'        uniform token subdivisionScheme = "none"','        point3f[] points = [',f'                {_fmt_pts(bucket.points)}',"        ]",'        int[] faceVertexCounts = [',f'                {_fmt_ints(bucket.counts)}',"        ]",'        int[] faceVertexIndices = [',f'                {_fmt_ints(bucket.indices)}',"        ]",f'        rel material:binding = </Brain/Looks/{name}>',"    }"]
    lines += ["}"]
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return path


def package_usdz(root_layer: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True,exist_ok=True)
    info=zipfile.ZipInfo(root_layer.name,time.localtime()[:6])
    info.compress_type=zipfile.ZIP_STORED
    info.external_attr=0o644 << 16
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_STORED,allowZip64=False) as archive:
        archive.writestr(info,root_layer.read_bytes())
    with zipfile.ZipFile(output,"r") as archive:
        if archive.testzip() is not None or len(archive.infolist()) != 1 or archive.infolist()[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("apple_ar_v13_package_validation_failed")
    return output


def build_brain_usdz(atlas: Any, output: Path) -> Path:
    usda=output.with_suffix(".usda")
    write_brain_usda(atlas,usda)
    return package_usdz(usda,output)
