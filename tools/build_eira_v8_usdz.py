from __future__ import annotations

from pathlib import Path
import hashlib, json, math, time, zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'eira2_transport_bus' / 'to_superprobe' / 'artifacts'
OUT.mkdir(parents=True, exist_ok=True)
USDA = OUT / 'EIRA2_LIVING_NEURAL_ORGANISM_V8.usda'
USDZ = OUT / 'EIRA2_LIVING_NEURAL_ORGANISM_V8.usdz'
REPORT = OUT / 'EIRA2_LIVING_NEURAL_ORGANISM_V8.validation.json'
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def vadd(a,b): return (a[0]+b[0],a[1]+b[1],a[2]+b[2])
def vsub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def vmul(a,s): return (a[0]*s,a[1]*s,a[2]*s)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a):
    l=math.sqrt(dot(a,a))
    return (0,0,1) if l < 1e-9 else (a[0]/l,a[1]/l,a[2]/l)


class Bucket:
    def __init__(self,name):
        self.name=name; self.points=[]; self.counts=[]; self.indices=[]
    def face(self,pts):
        base=len(self.points); self.points.extend(pts); self.counts.append(len(pts)); self.indices.extend(range(base,base+len(pts)))


ICO=[(-1,1.618,0),(1,1.618,0),(-1,-1.618,0),(1,-1.618,0),(0,-1,1.618),(0,1,1.618),(0,-1,-1.618),(0,1,-1.618),(1.618,0,-1),(1.618,0,1),(-1.618,0,-1),(-1.618,0,1)]
ICO=[norm(v) for v in ICO]
F=[(0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),(1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),(3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),(4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1)]


def soma(b,c,r):
    base=len(b.points); b.points.extend([vadd(c,vmul(v,r)) for v in ICO])
    for f in F:
        b.counts.append(3); b.indices.extend([base+f[0],base+f[1],base+f[2]])


def tube(b,a,c,r0,r1=None,sides=6):
    if r1 is None: r1=r0
    d=vsub(c,a); L=math.sqrt(dot(d,d))
    if L < 1e-6: return
    w=norm(d); ref=(0,0,1) if abs(w[2])<.9 else (0,1,0); u=norm(cross(w,ref)); v=norm(cross(w,u))
    ra=[]; rb=[]
    for i in range(sides):
        ang=2*math.pi*i/sides; dv=vadd(vmul(u,math.cos(ang)),vmul(v,math.sin(ang)))
        ra.append(vadd(a,vmul(dv,r0))); rb.append(vadd(c,vmul(dv,r1)))
    base=len(b.points); b.points.extend(ra+rb)
    for i in range(sides):
        j=(i+1)%sides; b.counts.append(4); b.indices.extend([base+i,base+j,base+sides+j,base+sides+i])


def box(b,c,s):
    x,y,z=c; sx,sy,sz=s
    p=[(x-sx,y-sy,z-sz),(x+sx,y-sy,z-sz),(x+sx,y+sy,z-sz),(x-sx,y+sy,z-sz),(x-sx,y-sy,z+sz),(x+sx,y-sy,z+sz),(x+sx,y+sy,z+sz),(x-sx,y+sy,z+sz)]
    for f in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(4,0,3,7)]: b.face([p[i] for i in f])


palette={
'Azure':((.008,.30,1),(.03,.65,1)),'Cyan':((.003,.82,1),(.04,1,1)),'Violet':((.38,.01,1),(.75,.05,1)),
'Magenta':((1,.01,.62),(1,.08,.88)),'Rose':((1,.03,.28),(1,.14,.42)),'Amber':((1,.22,.003),(1,.66,.02)),
'Gold':((1,.48,.008),(1,.95,.05)),'White':((.90,.99,1),(1,1,1))}
b={k:Bucket(k) for k in palette}
colors=list(palette)

nodes=[]
specs=[(560,.945,.0076),(340,.825,.0063),(160,.70,.0054)]
for si,(count,R,base) in enumerate(specs):
    for i in range(count):
        u=(i+.5)/count; z=1-2*u; rr=math.sqrt(max(0,1-z*z)); th=i*GOLDEN+si*.49
        x=R*rr*math.cos(th); y=R*rr*math.sin(th); zz=R*z; x += (-1 if x<0 else 1)*.020*(1-abs(z))
        p=(x,y,zz); m=colors[(i*5+si*2)%len(colors)]; s=base*(2.9 if i%(29-si*3)==0 else 1.65 if i%13==0 else 1)
        soma(b[m],p,s); nodes.append({'id':f'n{si}_{i}','p':p,'m':m,'s':si})

seen=set(); dend=0
for si in range(3):
    ss=[n for n in nodes if n['s']==si]; nnear=4 if si==0 else 3
    for idx,n in enumerate(ss):
        near=sorted(((math.dist(n['p'],q['p']),q) for q in ss if q['id']!=n['id']),key=lambda x:x[0])[:nnear]
        for rank,(_,q) in enumerate(near):
            key=tuple(sorted((n['id'],q['id']))); 
            if key in seen: continue
            seen.add(key); a=n['p']; c=q['p']; m=tuple((a[k]+c[k])/2 for k in range(3)); ml=math.sqrt(dot(m,m)) or 1
            bend=(.008+rank*.0025)*(-1 if (idx+rank)%2 else 1); ctrl=tuple(m[k]+m[k]/ml*bend for k in range(3)); r=.00105 if si==0 else .00085
            tube(b[n['m']],a,ctrl,r,r*.78,6); tube(b[n['m']],ctrl,c,r*.78,r*.48,6); dend+=1

outer=[n for n in nodes if n['s']==0]; middle=[n for n in nodes if n['s']==1]; inner=[n for n in nodes if n['s']==2]
cross_depth=0
for stride,src,dst,ma,mb in [(6,outer,middle,'Cyan','Violet'),(5,middle,inner,'Magenta','Azure')]:
    for i,n in enumerate(src[::stride]):
        q=min(dst,key=lambda x:math.dist(n['p'],x['p'])); tube(b[ma if i%2==0 else mb],n['p'],q['p'],.0009,.00055,6); cross_depth+=1

left=[n for n in outer if n['p'][0]<-.14]; right=[n for n in outer if n['p'][0]>.14]; bridges=0
for j in range(84):
    a=left[(j*11)%len(left)]['p']; q=min(right,key=lambda n:abs(n['p'][1]-a[1])+abs(n['p'][2]-a[2]))['p']
    c1=(a[0]*.34,a[1]*.75,a[2]*.75); c2=(q[0]*.34,q[1]*.75,q[2]*.75); m='Gold' if j%5==0 else 'Cyan' if j%2==0 else 'Magenta'
    tube(b[m],a,c1,.00135,.00165,6); tube(b[m],c1,c2,.00165,.00165,6); tube(b[m],c2,q,.00165,.00135,6); bridges+=1

for r,m in [(.19,'Amber'),(.14,'Gold'),(.09,'White'),(.05,'Amber')]:
    total=72 if r>.1 else 40
    for i in range(total):
        u=(i+.5)/total; z=1-2*u; rr=math.sqrt(max(0,1-z*z)); th=i*GOLDEN; soma(b[m],(r*rr*math.cos(th),r*rr*math.sin(th),r*z),.012 if r>.1 else .010)
    soma(b[m],(0,0,0),r*.42)

for j in range(42):
    az=2*math.pi*j/42; elev=-.64+1.28*((j%13)/12); rr=math.sqrt(max(.08,1-elev*elev)); t=(.66*rr*math.cos(az),.66*rr*math.sin(az),.66*elev)
    c1=vmul(t,.27); c2=vmul(t,.61); m='Amber' if j%3==0 else 'Gold'; tube(b[m],(0,0,0),c1,.0052,.0037,7); tube(b[m],c1,c2,.0037,.0022,7); tube(b[m],c2,t,.0022,.0007,7)

sp=[(0,0,-.98+1.96*i/87) for i in range(88)]
for i in range(len(sp)-1): tube(b['White' if 31<i<57 else 'Cyan'],sp[i],sp[i+1],.0048,.0048,8)
for phase,m in [(0,'Violet'),(math.pi,'Gold')]:
    pts=[(.048*math.cos(phase+t*math.pi*10),.048*math.sin(phase+t*math.pi*10),-.95+1.9*t) for t in [i/139 for i in range(140)]]
    for i in range(len(pts)-1): tube(b[m],pts[i],pts[i+1],.0020,.0020,6)

books=0
for floor in range(5):
    z=-.12+floor*.06; r=.19+floor*.024
    for k in range(26):
        a=2*math.pi*k/26+floor*.12; p=(r*math.cos(a),r*math.sin(a),z); box(b['Gold' if k%6==0 else 'Azure'],p,(.0043,.0074,.0025)); books+=1
    pts=[(r*math.cos(2*math.pi*k/34),r*math.sin(2*math.pi*k/34),z) for k in range(34)]
    for k in range(34): tube(b['Gold' if floor%2==0 else 'Cyan'],pts[k],pts[(k+1)%34],.00135,.00135,6)


def fmt_pts(points): return ',\n                '.join(f'({x:.6f}, {y:.6f}, {z:.6f})' for x,y,z in points)
def fmt_int(vals,w=30): return ',\n                '.join(', '.join(map(str,vals[i:i+w])) for i in range(0,len(vals),w))

L=['#usda 1.0','(','    defaultPrim = "Brain"','    metersPerUnit = 1','    upAxis = "Z"','    startTimeCode = 0','    endTimeCode = 180','    timeCodesPerSecond = 30',')','','def Xform "Brain" {','    custom string eira:visualSchema = "eira2_living_neural_organism_v8"','    custom string eira:reactivity = "runtime_activity_driven_when_generated_by_eira"','    def Scope "Looks" {']
for name,(rgb,emit) in palette.items():
    L += [f'        def Material "{name}" {{',f'            token outputs:surface.connect = </Brain/Looks/{name}/S.outputs:surface>','            def Shader "S" {','                uniform token info:id = "UsdPreviewSurface"',f'                color3f inputs:diffuseColor = ({rgb[0]:.6f}, {rgb[1]:.6f}, {rgb[2]:.6f})',f'                color3f inputs:emissiveColor = ({emit[0]:.6f}, {emit[1]:.6f}, {emit[2]:.6f})','                float inputs:roughness = 0.10','                float inputs:metallic = 0.04','                token outputs:surface','            }','        }']
L+=['    }']
for name,bk in b.items():
    L += [f'    def Mesh "{name}Tissue" {{','        uniform token subdivisionScheme = "none"','        point3f[] points = [',f'                {fmt_pts(bk.points)}','        ]','        int[] faceVertexCounts = [',f'                {fmt_int(bk.counts)}','        ]','        int[] faceVertexIndices = [',f'                {fmt_int(bk.indices)}','        ]',f'        rel material:binding = </Brain/Looks/{name}>','    }']
L += ['    def Xform "CorePulse" {','        float3 xformOp:scale.timeSamples = { 0:(1,1,1), 20:(1.18,1.18,1.18), 40:(1,1,1), 60:(1.10,1.10,1.10), 80:(1,1,1), 100:(1.22,1.22,1.22), 120:(1,1,1), 140:(1.12,1.12,1.12), 160:(1,1,1), 180:(1,1,1) }','        uniform token[] xformOpOrder = ["xformOp:scale"]','        def Sphere "Pulse" { double radius = 0.205 rel material:binding = </Brain/Looks/Gold> }','    }']
regions=['conversation_spine','memory','evidence','reasoning','identity','universe_library','extensions','watcher','superprobe','delivery']
for i in range(18):
    region=regions[i%len(regions)]; a0=(i*GOLDEN)%(2*math.pi); a1=a0+1; a2=a0+2.1; z0=-.72+.08*(i%9); z1=.05*math.sin(i); z2=.72-.08*(i%9)
    def P(a,z,r=.90):
        rr=math.sqrt(max(.05,1-z*z)); return (r*rr*math.cos(a),r*rr*math.sin(a),r*z)
    p0,p1,p2=P(a0,z0),P(a1,z1,.84),P(a2,z2); start=(i*9)%150; mat='Gold' if i%4==0 else 'White' if i%3==0 else 'Cyan'
    L += [f'    def Xform "Impulse_{i:02d}" {{',f'        custom string eira:activityRegion = "{region}"','        custom string eira:previewMode = "cosmetic_idle_demo_not_runtime_truth"',f'        double3 xformOp:translate.timeSamples = {{ {start}:({p0[0]:.6f},{p0[1]:.6f},{p0[2]:.6f}), {start+15}:({p1[0]:.6f},{p1[1]:.6f},{p1[2]:.6f}), {start+30}:({p2[0]:.6f},{p2[1]:.6f},{p2[2]:.6f}), {start+45}:({p0[0]:.6f},{p0[1]:.6f},{p0[2]:.6f}) }}',f'        float3 xformOp:scale.timeSamples = {{ {start}:(0.5,0.5,0.5), {start+8}:(1.35,1.35,1.35), {start+16}:(0.75,0.75,0.75), {start+30}:(1.25,1.25,1.25), {start+45}:(0.5,0.5,0.5) }}','        uniform token[] xformOpOrder = ["xformOp:translate","xformOp:scale"]',f'        def Sphere "Signal" {{ double radius = 0.017 rel material:binding = </Brain/Looks/{mat}> }}','    }']
L+=['}']
USDA.write_text('\n'.join(L)+'\n',encoding='utf-8')
assert USDA.read_text().count('{')==USDA.read_text().count('}')
zi=zipfile.ZipInfo(USDA.name,time.localtime()[:6]); zi.compress_type=zipfile.ZIP_STORED; zi.external_attr=0o644<<16
with zipfile.ZipFile(USDZ,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as z: z.writestr(zi,USDA.read_bytes())
with zipfile.ZipFile(USDZ,'r') as z: assert z.testzip() is None and len(z.infolist())==1 and z.infolist()[0].compress_type==zipfile.ZIP_STORED
sha=hashlib.sha256(USDZ.read_bytes()).hexdigest()
REPORT.write_text(json.dumps({'schema':'eira2_living_neural_organism_v8_validation','zip_integrity':True,'compression':'stored','optimized_mesh_prims':8,'animation_prims':19,'neurons':sum(x[0] for x in specs),'dendritic_networks':dend,'cross_depth_synapses':cross_depth,'corpus_bridges':bridges,'hall_books':books,'runtime_truth_note':'standalone impulse animation is cosmetic; LIVE generator maps real NeuralActivity regions and evidenced fibers','size_bytes':USDZ.stat().st_size,'sha256':sha},indent=2))
print(json.dumps({'USDZ':str(USDZ.relative_to(ROOT)),'sha256':sha,'bytes':USDZ.stat().st_size},sort_keys=True))
