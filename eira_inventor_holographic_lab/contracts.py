from __future__ import annotations
import math

PROVENANCE = {"observed","stated","calculated","inferred","assumed","hypothesized","unresolved"}
GEOMETRY_KINDS = {"primitive","mesh","curve","extrude","revolve","sweep","loft","surface","instance","boolean","compound"}
JOINT_KINDS = {"fixed","revolute","continuous","oscillating","prismatic","keyframed","coupled"}

class ContractError(ValueError): pass

def finite(x):
    try: return math.isfinite(float(x))
    except Exception: return False

def vec(v, n=3, name="vector"):
    if not isinstance(v,(list,tuple)) or len(v)!=n or not all(finite(x) for x in v): raise ContractError(f"{name} must be {n} finite numbers")
    return [float(x) for x in v]

def validate_source(src):
    if not isinstance(src,dict): raise ContractError("source must be object")
    p=src.get("provenance","unresolved")
    if p not in PROVENANCE: raise ContractError(f"invalid provenance:{p}")
    c=src.get("confidence",0.0)
    if not finite(c) or not 0<=float(c)<=1: raise ContractError("confidence must be 0..1")

def _profile(p, name):
    if not isinstance(p,list) or len(p)<2: raise ContractError(f"{name} requires >=2 points")
    for i,x in enumerate(p): vec(x, len(x), f"{name}[{i}]")

def validate_geometry(g):
    if not isinstance(g,dict): raise ContractError("geometry must be object")
    k=g.get("kind")
    if k not in GEOMETRY_KINDS: raise ContractError(f"unsupported geometry kind:{k}")
    if k=="primitive":
        if g.get("primitive") not in {"box","cylinder","sphere","cone","torus","plane","capsule"}: raise ContractError("unsupported primitive")
        dims=g.get("dimensions",{})
        if not isinstance(dims,dict) or any((not finite(v) or float(v)<=0) for v in dims.values()): raise ContractError("primitive dimensions must be positive finite")
    elif k=="mesh":
        vs=g.get("vertices",[]); fs=g.get("faces",[])
        if len(vs)<3 or not fs: raise ContractError("mesh requires vertices and faces")
        for i,v in enumerate(vs): vec(v,3,f"vertex[{i}]")
        for i,f in enumerate(fs):
            if not isinstance(f,list) or len(f)<3 or any(not isinstance(j,int) or j<0 or j>=len(vs) for j in f): raise ContractError(f"invalid face[{i}]")
    elif k=="curve":
        pts=g.get("points",[])
        if len(pts)<2: raise ContractError("curve requires >=2 points")
        for i,p in enumerate(pts): vec(p,3,f"point[{i}]")
        if g.get("basis","POLY") not in {"POLY","BEZIER","NURBS"}: raise ContractError("curve basis unsupported")
    elif k=="extrude": _profile(g.get("profile",[]),"profile"); vec(g.get("vector",[]),3,"extrude vector")
    elif k=="revolve":
        _profile(g.get("profile",[]),"profile"); vec(g.get("axis",[]),3,"axis"); ang=g.get("angle_deg",360)
        if not finite(ang) or not 0<float(ang)<=360: raise ContractError("revolve angle invalid")
    elif k=="sweep":
        _profile(g.get("profile",[]),"profile"); path=g.get("path",[])
        if len(path)<2: raise ContractError("sweep path requires >=2 points")
        for i,p in enumerate(path): vec(p,3,f"path[{i}]")
    elif k=="loft":
        sections=g.get("sections",[])
        if len(sections)<2: raise ContractError("loft requires >=2 sections")
        count=None
        for i,s in enumerate(sections):
            _profile(s,f"section[{i}]"); count=len(s) if count is None else count
            if len(s)!=count: raise ContractError("loft sections must have matching point counts")
    elif k=="surface":
        grid=g.get("grid",[])
        if len(grid)<2 or any(not isinstance(r,list) or len(r)<2 for r in grid): raise ContractError("surface grid invalid")
        width=len(grid[0])
        if any(len(r)!=width for r in grid): raise ContractError("surface grid ragged")
        for r in grid:
            for p in r: vec(p,3,"surface point")
    elif k=="instance":
        if not g.get("source_part_id"): raise ContractError("instance requires source_part_id")
    elif k=="boolean":
        if g.get("operation") not in {"UNION","DIFFERENCE","INTERSECT"}: raise ContractError("boolean operation invalid")
        if len(g.get("operands",[]))<2: raise ContractError("boolean requires operands")
    elif k=="compound":
        ops=g.get("operations",[])
        if not ops: raise ContractError("compound requires operations")
        for op in ops: validate_geometry(op)

def validate_part(p):
    if not isinstance(p,dict): raise ContractError("part must be object")
    for x in ("part_id","name"):
        if not str(p.get(x,"")).strip(): raise ContractError(f"part missing {x}")
    validate_geometry(p.get("geometry")); t=p.get("transform",{})
    vec(t.get("location",[0,0,0]),3,"location"); vec(t.get("rotation_deg",[0,0,0]),3,"rotation"); vec(t.get("scale",[1,1,1]),3,"scale")
    if any(abs(x)<1e-12 for x in t.get("scale",[1,1,1])): raise ContractError("singular scale")
    validate_source(p.get("source",{"provenance":"unresolved","confidence":0}))

def validate_joint(j, part_ids):
    if j.get("kind") not in JOINT_KINDS: raise ContractError("joint kind invalid")
    a=j.get("parent"); b=j.get("child")
    if a not in part_ids or b not in part_ids or a==b: raise ContractError("joint references invalid")
    vec(j.get("axis",[0,0,1]),3,"joint axis")
    if j.get("kind") in {"revolute","continuous","oscillating","prismatic"} and sum(abs(float(x)) for x in j.get("axis",[]))<1e-12: raise ContractError("joint axis zero")

def validate_assembly(a):
    if not isinstance(a,dict): raise ContractError("assembly must be object")
    parts=a.get("parts",[])
    if not parts: raise ContractError("assembly requires parts")
    ids=[]
    for p in parts: validate_part(p); ids.append(p["part_id"])
    if len(ids)!=len(set(ids)): raise ContractError("duplicate part_id")
    for j in a.get("joints",[]): validate_joint(j,set(ids))
    for q in a.get("quantities",[]): validate_source(q.get("source",{"provenance":"unresolved","confidence":0}))
    return True
