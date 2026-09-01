from __future__ import annotations
import copy
import numpy as np
import trimesh
from .contracts import validate_assembly, ContractError
from .geometry import mesh_from_geometry
from .science import preflight
from .motion import compile_motion
from .living import simulate_living_architecture
from .diagram import build_diagram_layer

def _mesh_metrics(mesh):
    out={"surface_area_m2":float(mesh.area)}
    try:
        if mesh.is_volume: out["volume_m3"]=abs(float(mesh.volume))
    except Exception: pass
    try:
        out["bounds_m"]=mesh.bounds.tolist(); out["extents_m"]=mesh.extents.tolist(); out["centroid_m"]=mesh.centroid.tolist()
    except Exception: pass
    out["vertices"]=int(len(mesh.vertices)); out["faces"]=int(len(mesh.faces)); out["watertight"]=bool(getattr(mesh,"is_watertight",False))
    return out

def compile_assembly(assembly, duration_s=10.0, fps=24):
    a=copy.deepcopy(assembly); validate_assembly(a)
    scene=trimesh.Scene(); base_cache={}; world_cache={}; metrics={}

    # First compile every concrete geometry in local coordinates, then apply its transform.
    # Keeping local geometry separate is critical for repeated/instanced parts: an instance
    # must not accidentally inherit the source object's world transform.
    for p in a["parts"]:
        g=p["geometry"]
        if g["kind"] in {"instance","boolean"}: continue
        base=mesh_from_geometry(g)
        base_cache[p["part_id"]]=base.copy()
        m=base.copy(); apply_transform(m,p.get("transform",{})); world_cache[p["part_id"]]=m
        metrics[p["part_id"]]=_mesh_metrics(m)
        scene.add_geometry(m,node_name=p["part_id"],geom_name=p["part_id"],metadata={"name":p.get("name"),"system":p.get("system"),"source":p.get("source")})

    # Resolve instances against LOCAL source geometry so copies render at their own declared
    # transforms. This keeps compiler, Blender output and QA spatially consistent.
    for p in a["parts"]:
        g=p["geometry"]
        if g["kind"]=="instance":
            src_id=g["source_part_id"]
            src=base_cache.get(src_id)
            if src is None: raise ContractError("instance source missing or instance-of-instance unsupported")
            m=src.copy(); apply_transform(m,p.get("transform",{})); world_cache[p["part_id"]]=m
            base_cache[p["part_id"]]=src.copy()
            metrics[p["part_id"]]=_mesh_metrics(m)
            scene.add_geometry(m,node_name=p["part_id"],geom_name=p["part_id"],metadata={"name":p.get("name"),"system":p.get("system"),"source":p.get("source")})
        elif g["kind"]=="boolean":
            raise ContractError("boolean requires configured exact boolean backend")

    a["mesh_metrics"]=metrics
    a["calculated_quantities"]=preflight(a,metrics)
    a["motion_tracks"]=compile_motion(a,duration_s=duration_s,fps=fps)
    a["living_simulation"]=simulate_living_architecture(a,duration_s=duration_s,fps=min(fps,12))
    a["diagram_layer"]=build_diagram_layer(a)
    _add_diagram_geometry(scene,a["diagram_layer"])
    a["engineering_summary"]={
        "part_count":len(a["parts"]),"joint_count":len(a.get("joints",[])),"behavior_count":len(a.get("behaviors",[])),
        "diagram_item_count":a["diagram_layer"]["count"],"calculated_quantity_count":len(a["calculated_quantities"]),
        "truth_boundary":"Closed-form preflight calculations and declared dynamic behaviors; not FEA/CFD/certification unless an external solver is explicitly configured."
    }
    return a,scene

def apply_transform(m,t):
    loc=np.array(t.get("location",[0,0,0]),float); rot=np.radians(np.array(t.get("rotation_deg",[0,0,0]),float)); sc=np.array(t.get("scale",[1,1,1]),float)
    M=np.eye(4); M[:3,:3]=trimesh.transformations.euler_matrix(*rot,"sxyz")[:3,:3] @ np.diag(sc); M[:3,3]=loc; m.apply_transform(M)

def _cylinder_between(a,b,r=0.006):
    a=np.asarray(a,float); b=np.asarray(b,float); d=b-a; L=float(np.linalg.norm(d))
    if L<1e-9: return None
    m=trimesh.creation.cylinder(radius=r,height=L,sections=12)
    z=np.array([0.,0.,1.]); u=d/L; axis=np.cross(z,u); dot=float(np.clip(np.dot(z,u),-1,1)); M=np.eye(4)
    if np.linalg.norm(axis)>1e-9:
        axis=axis/np.linalg.norm(axis); ang=np.arccos(dot); M=trimesh.transformations.rotation_matrix(ang,axis)
    elif dot<0: M=trimesh.transformations.rotation_matrix(np.pi,[1,0,0])
    M[:3,3]=(a+b)/2; m.apply_transform(M); return m

def _add_diagram_geometry(scene,layer):
    for it in layer.get("items",[]):
        k=it.get("kind"); iid="diagram__"+str(it.get("id","item"))
        if k=="dimension":
            m=_cylinder_between(it["a"],it["b"],.004)
            if m is not None: scene.add_geometry(m,node_name=iid,geom_name=iid)
        elif k=="vector":
            a=np.asarray(it["origin"],float); v=np.asarray(it["vector"],float); n=float(np.linalg.norm(v))
            if n>1e-9:
                b=a+v/n*.15; m=_cylinder_between(a,b,.006)
                if m is not None: scene.add_geometry(m,node_name=iid,geom_name=iid)
        elif k=="flow":
            pts=it.get("path",[])
            for i in range(len(pts)-1):
                m=_cylinder_between(pts[i],pts[i+1],.005)
                if m is not None: scene.add_geometry(m,node_name=f"{iid}_{i}",geom_name=f"{iid}_{i}")
        elif k=="port":
            m=trimesh.creation.icosphere(subdivisions=1,radius=.018); m.apply_translation(it["position"]); scene.add_geometry(m,node_name=iid,geom_name=iid)
