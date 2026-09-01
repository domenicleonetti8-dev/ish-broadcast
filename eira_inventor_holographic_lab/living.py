from __future__ import annotations
import math

def _curve(kind,t,p):
    if kind=="constant": return float(p.get("value",0.0))
    if kind=="sine": return float(p.get("offset",0))+float(p.get("amplitude",1))*math.sin(2*math.pi*float(p.get("frequency_hz",.1))*t+float(p.get("phase_rad",0)))
    if kind=="ramp": return float(p.get("start",0))+float(p.get("rate_per_s",1))*t
    if kind=="pulse":
        period=max(1e-9,float(p.get("period_s",1))); duty=min(1,max(0,float(p.get("duty",.5))))
        return float(p.get("high",1)) if (t%period)/period<duty else float(p.get("low",0))
    return 0.0

def simulate_living_architecture(assembly,duration_s=10.0,fps=12):
    """Samples declared behaviors into a state history. Does not invent behavior.
    Behaviors are declarative and may target transforms, material properties, flow intensity, sensor state, or controller state.
    """
    n=max(2,int(duration_s*fps)+1); history=[]
    behaviors=assembly.get("behaviors",[]) or []
    for i in range(n):
        t=i/fps; frame={"t_s":t,"states":{}}
        for b in behaviors:
            bid=str(b.get("behavior_id","behavior")); target=str(b.get("target","")); variable=str(b.get("variable","value"))
            value=_curve(str(b.get("curve","constant")),t,b)
            frame["states"][bid]={"target":target,"variable":variable,"value":value,"units":b.get("units","")}
        history.append(frame)
    return {"duration_s":duration_s,"fps":fps,"frames":history}
