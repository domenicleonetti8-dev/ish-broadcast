from __future__ import annotations
import copy, numpy as np
import trimesh
from .contracts import validate_assembly, ContractError
from .geometry import mesh_from_geometry
from .science import preflight
from .motion import compile_motion

def compile_assembly(assembly):
    a=copy.deepcopy(assembly); validate_assembly(a)
    a["calculated_quantities"]=preflight(a); a["motion_tracks"]=compile_motion(a)
    scene=trimesh.Scene(); cache={}
    for p in a["parts"]:
        g=p["geometry"]
        if g["kind"] in {"instance","boolean"}: continue
        m=mesh_from_geometry(g); apply_transform(m,p.get("transform",{})); cache[p["part_id"]]=m; scene.add_geometry(m,node_name=p["part_id"],geom_name=p["part_id"])
    for p in a["parts"]:
        g=p["geometry"]
        if g["kind"]=="instance":
            src=cache.get(g["source_part_id"])
            if src is None: raise ContractError("instance source missing")
            m=src.copy(); apply_transform(m,p.get("transform",{})); cache[p["part_id"]]=m; scene.add_geometry(m,node_name=p["part_id"],geom_name=p["part_id"])
        elif g["kind"]=="boolean":
            raise ContractError("boolean requires configured exact boolean backend")
    return a,scene

def apply_transform(m,t):
    loc=np.array(t.get("location",[0,0,0]),float); rot=np.radians(np.array(t.get("rotation_deg",[0,0,0]),float)); sc=np.array(t.get("scale",[1,1,1]),float)
    M=np.eye(4); M[:3,:3]=trimesh.transformations.euler_matrix(*rot,"sxyz")[:3,:3] @ np.diag(sc); M[:3,3]=loc; m.apply_transform(M)
