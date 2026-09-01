import sys,math,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eira_inventor_holographic_lab.compiler import compile_assembly
ROOT=Path(__file__).resolve().parents[1]
def S(c=.8,p="inferred"): return {"provenance":p,"confidence":c}
def T(loc=[0,0,0]): return {"location":loc,"rotation_deg":[0,0,0],"scale":[1,1,1]}
def P(pid,name,g,loc=[0,0,0],source=None): return {"part_id":pid,"name":name,"geometry":g,"transform":T(loc),"source":source or S(),"engineering":{}}
parts=[]
parts.append(P("base","Habitat base",{"kind":"primitive","primitive":"box","dimensions":{"x":8,"y":4.5,"z":.18}},source=S(.9)))
us=np.linspace(0,math.pi,28); vs=np.linspace(-1,1,22); grid=[]
for v in vs:
 row=[]
 for u in us:
  x=4*math.cos(u); z=.18+2.7*math.sin(u); y=2.2*v; taper=math.sqrt(max(0,1-v*v*.12)); row.append([x*taper,y,z*taper])
 grid.append(row)
parts.append(P("shell","Arched transparent habitat shell",{"kind":"surface","grid":grid},source=S(.9)))
for ri,x in enumerate(np.linspace(-3.2,3.2,7)):
 pts=[[x,2.2*math.cos(u),.18+2.7*math.sin(u)] for u in np.linspace(0,math.pi,36)]
 parts.append(P(f"rib{ri}","Structural arch rib",{"kind":"curve","basis":"POLY","points":pts,"radius":.055},source=S(.75)))
parts.append(P("bed_left","Raised crop bed",{"kind":"primitive","primitive":"box","dimensions":{"x":5.5,"y":1.15,"z":.45}},[-.4,-1.35,.32],S(.78)))
parts.append(P("bed_right","Raised crop bed",{"kind":"primitive","primitive":"box","dimensions":{"x":5.5,"y":1.15,"z":.45}},[-.4,1.35,.32],S(.78)))
for pi,(x,y) in enumerate([(-2,-1.35),(-.8,-1.35),(.5,-1.35),(1.8,-1.35),(-1.4,1.35),(0,1.35),(1.4,1.35)]):
 h=1.0+0.25*(pi%3); parts.append(P(f"stem{pi}","Plant stem",{"kind":"curve","basis":"BEZIER","points":[[x,y,.55],[x+.08,y,h],[x,y,h+.35]],"radius":.035},source=S(.72)))
 for li,sgn in enumerate((-1,1)): parts.append(P(f"leaf{pi}_{li}","Plant leaf",{"kind":"curve","basis":"BEZIER","points":[[x,y,h*.8],[x+.45*sgn,y+.15*sgn,h+.15],[x+.75*sgn,y+.3*sgn,h+.05]],"radius":.06},source=S(.65)))
parts.append(P("life_support","Life-support / gas handling module",{"kind":"primitive","primitive":"box","dimensions":{"x":1.0,"y":.7,"z":1.4}},[3.0,0,.8],S(.55,"hypothesized")))
parts.append(P("fan","Ventilation fan rotor",{"kind":"primitive","primitive":"cylinder","dimensions":{"radius":.32,"height":.08}},[2.48,0,1.15],S(.58,"hypothesized")))
joints=[{"joint_id":"fan_spin","kind":"continuous","parent":"life_support","child":"fan","axis":[1,0,0],"speed":6.0}]
a={"assembly_id":"off_world_greenhouse_reference","name":"Off-World Greenhouse Reference","parts":parts,"joints":joints,"hypotheses":[{"claim":"The supplied sketch is interpreted as an arched protected crop habitat with atmosphere control.","source":S(.82)},{"claim":"Gas-mix and biological performance notes remain inventor hypotheses requiring experimental validation.","source":S(.95)}]}
compiled,scene=compile_assembly(a); (ROOT/"artifacts").mkdir(exist_ok=True); (ROOT/"artifacts"/"off_world_greenhouse_ir.json").write_text(json.dumps(compiled,indent=2)); scene.export(ROOT/"artifacts"/"off_world_greenhouse_reference.glb")
print("REFERENCE GREENHOUSE COMPILE PASS",len(parts),"parts",len(joints),"moving joint")
