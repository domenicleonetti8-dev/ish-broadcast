import sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eira_inventor_holographic_lab.contracts import validate_assembly
from eira_inventor_holographic_lab.compiler import compile_assembly

def src(): return {"provenance":"inferred","confidence":.7}
def T(): return {"location":[0,0,0],"rotation_deg":[0,0,0],"scale":[1,1,1]}
def part(g): return {"part_id":"p","name":"p","geometry":g,"transform":T(),"source":src(),"engineering":{}}
def profile(n=8,r=.5,z=0): return [[r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),z] for i in range(n)]
def case(i):
 k=i%10
 if k==0:g={"kind":"primitive","primitive":"box","dimensions":{"x":1,"y":2,"z":3}}
 elif k==1:g={"kind":"mesh","vertices":[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],"faces":[[0,1,2],[0,1,3],[0,2,3],[1,2,3]]}
 elif k==2:g={"kind":"curve","basis":"BEZIER","points":[[0,0,0],[1,0,1],[2,1,1]],"radius":.05}
 elif k==3:g={"kind":"extrude","profile":[[0,0],[1,0],[1,1],[0,1]],"vector":[0,0,1]}
 elif k==4:g={"kind":"revolve","profile":[[.2,0],[.5,.5],[.3,1]],"axis":[0,0,1],"angle_deg":360}
 elif k==5:g={"kind":"sweep","profile":[[.1,0],[0,.1],[-.1,0],[0,-.1]],"path":[[0,0,0],[0,0,1],[.5,0,2],[1,.5,3]]}
 elif k==6:g={"kind":"loft","sections":[profile(8,.4,0),profile(8,.7,1),profile(8,.3,2)]}
 elif k==7:g={"kind":"surface","grid":[[[x,y,.2*math.sin(x+y)] for x in range(4)] for y in range(4)]}
 elif k==8:g={"kind":"compound","operations":[{"kind":"primitive","primitive":"sphere","dimensions":{"radius":.5}},{"kind":"curve","points":[[0,0,0],[0,0,1]],"radius":.05}]}
 else:g={"kind":"primitive","primitive":"cylinder","dimensions":{"radius":.4,"height":1}}
 return {"assembly_id":f"a{i}","name":"regression","parts":[part(g)],"joints":[]}
for i in range(300): validate_assembly(case(i)); compile_assembly(case(i))
print("REGRESSION_300 PASS 300/300")
