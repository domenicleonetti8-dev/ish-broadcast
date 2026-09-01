from __future__ import annotations
import math
import numpy as np
import trimesh
from .contracts import validate_geometry

def mesh_from_geometry(g):
    validate_geometry(g); k=g["kind"]
    if k=="primitive": return primitive(g)
    if k=="mesh": return trimesh.Trimesh(vertices=np.array(g["vertices"],float),faces=np.array(g["faces"],int),process=False)
    if k=="extrude": return extrude(g)
    if k=="revolve": return revolve(g)
    if k=="sweep": return sweep(g)
    if k=="loft": return loft(g)
    if k=="surface": return surface(g)
    if k=="curve": return curve_tube(g)
    if k=="compound": return trimesh.util.concatenate([mesh_from_geometry(x) for x in g["operations"]])
    raise ValueError(f"geometry kind {k} requires assembly context")

def primitive(g):
    p=g["primitive"]; d=g.get("dimensions",{})
    if p=="box": return trimesh.creation.box([d.get("x",1),d.get("y",1),d.get("z",1)])
    if p=="cylinder": return trimesh.creation.cylinder(radius=d.get("radius",.5),height=d.get("height",1),sections=int(d.get("segments",48)))
    if p=="sphere": return trimesh.creation.icosphere(subdivisions=int(d.get("subdivisions",3)),radius=d.get("radius",.5))
    if p=="cone": return trimesh.creation.cone(radius=d.get("radius",.5),height=d.get("height",1),sections=int(d.get("segments",48)))
    if p=="torus": return trimesh.creation.torus(major_radius=d.get("major_radius",1),minor_radius=d.get("minor_radius",.2),major_sections=int(d.get("major_segments",64)),minor_sections=int(d.get("minor_segments",24)))
    if p=="capsule": return trimesh.creation.capsule(height=d.get("height",1),radius=d.get("radius",.25),count=[16,32])
    if p=="plane": return trimesh.creation.box([d.get("x",1),d.get("y",1),max(d.get("z",.002),.0005)])
    raise ValueError(f"unsupported primitive:{p}")

def extrude(g):
    prof=np.array(g["profile"],float)
    if prof.shape[1]==3: prof=prof[:,:2]
    vec=np.array(g["vector"],float); h=np.linalg.norm(vec)
    if h<1e-12: raise ValueError("extrude vector is zero")
    n=len(prof)
    local=np.vstack([np.c_[prof,np.zeros(n)],np.c_[prof,np.full(n,h)]])
    faces=[]
    for i in range(1,n-1): faces += [[0,i,i+1],[n,n+i+1,n+i]]
    for i in range(n):
        j=(i+1)%n; faces += [[i,j,n+j],[i,n+j,n+i]]
    m=trimesh.Trimesh(local,np.array(faces),process=False)
    T=trimesh.geometry.align_vectors([0,0,1],vec/h)
    if T is not None: m.apply_transform(T)
    return m

def revolve(g):
    prof=np.array(g["profile"],float)
    if prof.shape[1]==3: prof=prof[:,[0,2]]
    axis=_unit(np.array(g.get("axis",[0,0,1]),float))
    ang=math.radians(float(g.get("angle_deg",360))); seg=max(8,int(g.get("segments",64))); us=np.linspace(0,ang,seg+1); verts=[]
    for u in us:
        c,s=math.cos(u),math.sin(u)
        for r,z in prof: verts.append([r*c,r*s,z])
    n=len(prof); faces=[]
    for a in range(seg):
        for i in range(n-1):
            x=a*n+i; y=x+n; faces += [[x,y,y+1],[x,y+1,x+1]]
    m=trimesh.Trimesh(np.array(verts),np.array(faces),process=False)
    T=trimesh.geometry.align_vectors([0,0,1],axis)
    if T is not None: m.apply_transform(T)
    return m

def _unit(v):
    v=np.asarray(v,float); n=float(np.linalg.norm(v))
    if n<1e-12: raise ValueError("zero-length vector in path")
    return v/n

def _initial_frame(t):
    t=_unit(t)
    refs=(np.array([0.,0.,1.]),np.array([0.,1.,0.]),np.array([1.,0.,0.]))
    ref=min(refs,key=lambda r:abs(float(np.dot(t,r))))
    n=_unit(np.cross(t,ref)); b=_unit(np.cross(t,n)); return n,b

def _rotate_about_axis(v,axis,angle):
    axis=_unit(axis); v=np.asarray(v,float)
    c=math.cos(angle); s=math.sin(angle)
    return v*c + np.cross(axis,v)*s + axis*np.dot(axis,v)*(1-c)

def _parallel_transport(prev_t,new_t,prev_n):
    """Transport a frame normal with minimal twist between neighboring path tangents."""
    a=_unit(prev_t); b=_unit(new_t); cross=np.cross(a,b); cn=float(np.linalg.norm(cross)); dot=float(np.clip(np.dot(a,b),-1,1))
    if cn<1e-10:
        n=prev_n-b*np.dot(prev_n,b)
        if np.linalg.norm(n)<1e-10: return _initial_frame(b)
        n=_unit(n); return n,_unit(np.cross(b,n))
    axis=cross/cn; angle=math.atan2(cn,dot); n=_rotate_about_axis(prev_n,axis,angle); n=n-b*np.dot(n,b)
    if np.linalg.norm(n)<1e-10: return _initial_frame(b)
    n=_unit(n); return n,_unit(np.cross(b,n))

def _path_tangents(path):
    path=np.asarray(path,float); tang=[]
    for i in range(len(path)):
        if i==0: d=path[1]-path[0]
        elif i==len(path)-1: d=path[-1]-path[-2]
        else: d=path[i+1]-path[i-1]
        tang.append(_unit(d))
    return tang

def sweep(g):
    prof=np.array(g["profile"],float)
    if prof.shape[1]==3: prof=prof[:,:2]
    path=np.array(g["path"],float)
    tang=_path_tangents(path); n,b=_initial_frame(tang[0]); frames=[(n,b)]
    for i in range(1,len(path)):
        n,b=_parallel_transport(tang[i-1],tang[i],n); frames.append((n,b))
    rings=[]
    for p,(n,b) in zip(path,frames): rings.append(np.array([p+n*x+b*y for x,y in prof]))
    verts=np.vstack(rings); m=len(prof); faces=[]
    for r in range(len(path)-1):
        for i in range(m):
            j=(i+1)%m; a=r*m+i; b0=r*m+j; c=(r+1)*m+j; d=(r+1)*m+i; faces += [[a,b0,c],[a,c,d]]
    return trimesh.Trimesh(verts,np.array(faces),process=False)

def _signed_area_xy(sec):
    a=np.array(sec,float); x=a[:,0]; y=a[:,1]; return .5*np.sum(x*np.roll(y,-1)-y*np.roll(x,-1))
def _align_section(ref,sec):
    ref=np.array(ref,float); sec=np.array(sec,float)
    if np.sign(_signed_area_xy(ref)) != np.sign(_signed_area_xy(sec)): sec=sec[::-1]
    costs=[np.sum((ref-np.roll(sec,k,axis=0))**2) for k in range(len(sec))]; return np.roll(sec,int(np.argmin(costs)),axis=0)
def loft(g):
    secs=[np.array(s,float) for s in g["sections"]]
    for i in range(1,len(secs)): secs[i]=_align_section(secs[i-1],secs[i])
    verts=np.vstack(secs); m=len(secs[0]); faces=[]
    for r in range(len(secs)-1):
        for i in range(m):
            j=(i+1)%m; a=r*m+i; b=r*m+j; c=(r+1)*m+j; d=(r+1)*m+i; faces += [[a,b,c],[a,c,d]]
    return trimesh.Trimesh(verts,np.array(faces),process=False)

def surface(g):
    grid=np.array(g["grid"],float); rows,cols=grid.shape[:2]; verts=grid.reshape(-1,3); faces=[]
    for r in range(rows-1):
        for c in range(cols-1):
            a=r*cols+c; b=a+1; d=(r+1)*cols+c; e=d+1; faces += [[a,b,e],[a,e,d]]
    return trimesh.Trimesh(verts,np.array(faces),process=False)

def curve_tube(g):
    pts=np.array(g["points"],float); rad=float(g.get("radius",.01)); meshes=[]
    for a,b in zip(pts[:-1],pts[1:]):
        v=b-a; L=np.linalg.norm(v)
        if L<1e-9: continue
        m=trimesh.creation.cylinder(radius=rad,height=L,sections=int(g.get("segments",16))); T=trimesh.geometry.align_vectors([0,0,1],v/L)
        if T is not None: m.apply_transform(T)
        m.apply_translation((a+b)/2); meshes.append(m)
    if not meshes: raise ValueError("curve has no non-zero segments")
    return trimesh.util.concatenate(meshes)
