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
    if p=="torus": return trimesh.creation.torus(major_radius=d.get("major_radius",1),minor_radius=d.get("minor_radius",.2),major_sections=64,minor_sections=24)
    if p=="capsule": return trimesh.creation.capsule(height=d.get("height",1),radius=d.get("radius",.25),count=[16,32])
    return trimesh.creation.box([d.get("x",1),d.get("y",1),max(d.get("z",.01),.001)])

def extrude(g):
    prof=np.array(g["profile"],float)
    if prof.shape[1]==3: prof=prof[:,:2]
    h=np.linalg.norm(np.array(g["vector"],float)); n=len(prof)
    verts=np.vstack([np.c_[prof,np.zeros(n)],np.c_[prof,np.full(n,h)]])
    faces=[]
    for i in range(1,n-1): faces += [[0,i,i+1],[n,n+i+1,n+i]]
    for i in range(n):
        j=(i+1)%n; faces += [[i,j,n+j],[i,n+j,n+i]]
    return trimesh.Trimesh(verts,np.array(faces),process=False)

def revolve(g):
    prof=np.array(g["profile"],float)
    if prof.shape[1]==3: prof=prof[:,[0,2]]
    ang=math.radians(float(g.get("angle_deg",360))); seg=max(8,int(g.get("segments",64))); us=np.linspace(0,ang,seg+1); verts=[]
    for u in us:
        c,s=math.cos(u),math.sin(u)
        for r,z in prof: verts.append([r*c,r*s,z])
    n=len(prof); faces=[]
    for a in range(seg):
        for i in range(n-1):
            x=a*n+i; y=x+n; faces += [[x,y,y+1],[x,y+1,x+1]]
    return trimesh.Trimesh(np.array(verts),np.array(faces),process=False)

def _frame(t,prev_n=None):
    t=np.array(t,float); t/=np.linalg.norm(t)
    if prev_n is None:
        ref=np.array([0.,0.,1.]) if abs(t[2])<.9 else np.array([0.,1.,0.]); n=np.cross(t,ref); n/=np.linalg.norm(n)
    else:
        n=prev_n-t*np.dot(prev_n,t)
        if np.linalg.norm(n)<1e-9: return _frame(t,None)
        n/=np.linalg.norm(n)
    b=np.cross(t,n); b/=np.linalg.norm(b); return n,b

def sweep(g):
    prof=np.array(g["profile"],float)
    if prof.shape[1]==3: prof=prof[:,:2]
    path=np.array(g["path"],float); rings=[]; prev_n=None
    for i,p in enumerate(path):
        t=path[min(i+1,len(path)-1)]-path[max(i-1,0)]; n,b=_frame(t,prev_n); prev_n=n; rings.append(np.array([p+n*x+b*y for x,y in prof]))
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
        m=trimesh.creation.cylinder(radius=rad,height=L,sections=16); m.apply_transform(trimesh.geometry.align_vectors([0,0,1],v/L)); m.apply_translation((a+b)/2); meshes.append(m)
    return trimesh.util.concatenate(meshes)
