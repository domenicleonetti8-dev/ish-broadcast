from __future__ import annotations
import math

def _dist(a,b): return math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))

def build_diagram_layer(assembly):
    """Creates explicit diagram primitives for dimensions, force vectors, flow paths and interfaces."""
    items=[]
    for d in assembly.get("dimensions",[]) or []:
        a=d.get("a"); b=d.get("b")
        if isinstance(a,list) and isinstance(b,list) and len(a)==3 and len(b)==3:
            val=d.get("value",_dist(a,b)); units=d.get("units",assembly.get("units","m"))
            items.append({"kind":"dimension","id":d.get("dimension_id",f"dim_{len(items)}"),"a":a,"b":b,"label":d.get("label",f"{val:.4g} {units}"),"source":d.get("source",{"provenance":"calculated","confidence":1.0})})
    for p in assembly.get("parts",[]):
        pid=p["part_id"]; e=p.get("engineering",{}) or {}; origin=(p.get("transform",{}) or {}).get("location",[0,0,0])
        fv=e.get("force_vector_N")
        if isinstance(fv,list) and len(fv)==3:
            items.append({"kind":"vector","id":f"force_{pid}","origin":origin,"vector":fv,"label":f"Force {math.sqrt(sum(float(x)**2 for x in fv)):.3g} N","semantic":"force"})
        for port in p.get("ports",[]) or []:
            pos=port.get("position",origin); direction=port.get("direction",[0,0,1])
            items.append({"kind":"port","id":port.get("port_id",f"port_{pid}_{len(items)}"),"position":pos,"direction":direction,"label":port.get("name",port.get("type","port")),"semantic":port.get("type","interface")})
    for f in assembly.get("flows",[]) or []:
        pts=f.get("path",[])
        if isinstance(pts,list) and len(pts)>=2:
            items.append({"kind":"flow","id":f.get("flow_id",f"flow_{len(items)}"),"path":pts,"label":f.get("label",f.get("medium","flow")),"medium":f.get("medium","unknown"),"rate":f.get("rate")})
    return {"items":items,"count":len(items)}
