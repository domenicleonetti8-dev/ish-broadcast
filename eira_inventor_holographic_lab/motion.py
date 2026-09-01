from __future__ import annotations
import math

def sample_joint(j,duration_s=5.0,fps=24):
    n=max(2,int(duration_s*fps)+1); kind=j["kind"]; speed=float(j.get("speed",1.0)); amp=float(j.get("amplitude",30.0)); phase=float(j.get("phase",0.0)); states=[]
    for i in range(n):
        t=i/fps
        if kind=="fixed": v=0.0
        elif kind=="continuous": v=speed*t
        elif kind=="oscillating": v=amp*math.sin(speed*t+phase)
        elif kind=="revolute": v=min(float(j.get("max",90)),max(float(j.get("min",0)),speed*t))
        elif kind=="prismatic": v=min(float(j.get("max",1)),max(float(j.get("min",0)),speed*t))
        else: v=0.0
        states.append({"t_s":t,"value":v})
    return states

def compile_motion(assembly,duration_s=5.0,fps=24): return {j.get("joint_id",f"joint_{i}"):sample_joint(j,duration_s,fps) for i,j in enumerate(assembly.get("joints",[]))}
