from pathlib import Path
import math, random, zipfile, struct, collections
import numpy as np
import trimesh
from trimesh.transformations import rotation_matrix

OUT=Path('/mnt/data')
USDZ=OUT/'EIRA_Off_World_Greenhouse_V10_Color.usdz'
GLB=OUT/'EIRA_Off_World_Greenhouse_V10_Color.glb'
USDA=OUT/'EIRA_Off_World_Greenhouse_V10_Color.usda'
random.seed(19)

# Materials: rgba, metallic, roughness
M={
 'steel':((150,158,166,255),.82,.24), 'dark':((38,43,49,255),.75,.32),
 'glass':((170,220,235,72),.0,.06), 'solar':((17,43,94,255),.12,.22), 'solargrid':((190,205,220,255),.65,.20),
 'water':((24,114,220,255),.12,.28), 'nutrient':((48,166,80,255),.06,.34), 'air':((236,157,31,255),.08,.32),
 'thermal':((204,65,45,255),.08,.30), 'power':((134,73,177,255),.08,.32), 'data':((32,181,190,255),.08,.30),
 'cabinet':((112,119,126,255),.42,.34), 'panel':((190,195,200,255),.35,.30), 'soil':((83,58,37,255),0,.88),
 'leafA':((41,119,51,255),0,.58), 'leafB':((78,157,65,255),0,.54), 'leafC':((123,170,61,255),0,.56),
 'fruit':((212,47,39,255),0,.42), 'flower':((240,152,36,255),0,.44), 'yellow':((228,192,47,255),.08,.32)
}
scene=trimesh.Scene()

def add(name,m,mat):
    if m is None: return None
    m.metadata['mat']=mat
    rgba=np.array(M[mat][0],dtype=np.uint8)
    m.visual.face_colors=np.tile(rgba,(len(m.faces),1))
    scene.add_geometry(m,geom_name=name,node_name=name)
    return m

def box(name,c,e,mat):
    m=trimesh.creation.box(extents=e); m.apply_translation(c); return add(name,m,mat)

def cyl(name,c,r,h,mat,axis='z',sections=20):
    m=trimesh.creation.cylinder(radius=r,height=h,sections=sections)
    if axis=='x': m.apply_transform(rotation_matrix(math.pi/2,[0,1,0]))
    elif axis=='y': m.apply_transform(rotation_matrix(math.pi/2,[1,0,0]))
    m.apply_translation(c); return add(name,m,mat)

def between(name,a,b,r,mat,sections=14):
    a=np.array(a,float); b=np.array(b,float); v=b-a; L=float(np.linalg.norm(v))
    if L<1e-8: return None
    m=trimesh.creation.cylinder(radius=r,height=L,sections=sections)
    d=v/L; z=np.array([0.,0.,1.]); ax=np.cross(z,d); dot=np.clip(np.dot(z,d),-1,1)
    if np.linalg.norm(ax)>1e-9: m.apply_transform(rotation_matrix(math.acos(dot),ax))
    elif dot<0: m.apply_transform(rotation_matrix(math.pi,[1,0,0]))
    m.apply_translation((a+b)/2); return add(name,m,mat)

def torus(name,c,R,r,mat,axis='x'):
    m=trimesh.creation.torus(major_radius=R,minor_radius=r,major_sections=32,minor_sections=10)
    if axis=='x': m.apply_transform(rotation_matrix(math.pi/2,[0,1,0]))
    elif axis=='y': m.apply_transform(rotation_matrix(math.pi/2,[1,0,0]))
    m.apply_translation(c); return add(name,m,mat)

def ell(name,c,scale,mat,sub=1):
    m=trimesh.creation.icosphere(subdivisions=sub,radius=1); m.apply_scale(scale); m.apply_translation(c); return add(name,m,mat)

def polyline(prefix,pts,r,mat,sections=12):
    for i,(a,b) in enumerate(zip(pts[:-1],pts[1:])): between(f'{prefix}_{i}',a,b,r,mat,sections)

def blade(name,c,length,width,thick,rot,mat):
    m=trimesh.creation.box(extents=(thick,length,width)); m.apply_transform(rotation_matrix(rot,[1,0,0])); m.apply_translation(c); return add(name,m,mat)

# Dimensions target ~8.2 x 4.7 x 2.8 upper habitat; raised service base
L=8.2; W=4.7; RY=W/2; ARCH=2.8; xmin=-L/2; xmax=L/2
base0=-1.0; deck=0.15; arch0=0.30

# Base: open structural chassis rather than slab
box('bottom_rail',(0,0,base0+0.08),(8.65,5.0,0.16),'dark')
for y in (-2.32,-1.55,0,1.55,2.32): between(f'base_long_{y}',(xmin-0.15,y,base0+0.22),(xmax+0.15,y,base0+0.22),0.045,'steel',16)
for x in np.linspace(xmin+0.15,xmax-0.15,11): between(f'base_cross_{x}',(x,-2.38,base0+0.22),(x,2.38,base0+0.22),0.040,'steel',16)
box('deck',(0,0,deck),(8.05,4.45,0.11),'panel')
for y in (-2.18,2.18): between(f'deckrail_{y}',(xmin+0.05,y,deck-0.18),(xmax-0.05,y,deck-0.18),0.055,'dark',16)
for x in np.linspace(xmin+0.15,xmax-0.15,9): between(f'deckcross_{x}',(x,-2.2,deck-0.18),(x,2.2,deck-0.18),0.040,'dark',14)

for i,x in enumerate(np.linspace(-3.55,-1.55,5)):
    mat='water' if i<3 else ('nutrient' if i==3 else 'steel')
    cyl(f'tank_{i}',(x,-1.85,-0.38),0.24,0.74,mat,'z',28)
    torus(f'tankring_{i}',(x,-1.85,-0.10),0.235,0.014,'dark','z')
    box(f'tankplate_{i}',(x,-2.10,-0.36),(0.25,0.035,0.22),'panel')
for i,x in enumerate(np.linspace(-1.15,3.65,11)):
    box(f'cab_{i}',(x,-1.83,-0.34),(0.34,0.40,0.72),'cabinet')
    box(f'cabface_{i}',(x,-2.04,-0.30),(0.24,0.025,0.30),'panel')
    cyl(f'pump_{i}',(x,-1.48,-0.53),0.11,0.28,'steel','x',20)
    cyl(f'motor_{i}',(x,-1.32,-0.53),0.09,0.22,'dark','x',20)
    if i%2==0: cyl(f'filter_{i}',(x+0.15,-1.55,-0.23),0.085,0.42,'water','z',18)
for i,x in enumerate(np.linspace(-3.2,3.4,9)):
    box(f'powercab_{i}',(x,1.90,-0.33),(0.42,0.40,0.74),'cabinet')
    box(f'powerface_{i}',(x,2.11,-0.30),(0.29,0.025,0.34),'panel')
    if i%3==0: cyl(f'thermal_vessel_{i}',(x+0.26,1.55,-0.30),0.095,0.45,'thermal','z',18)

systems=[('water',-2.20,-0.72,'water',0.024),('nut',-2.12,-0.63,'nutrient',0.020),('air',-2.04,-0.54,'air',0.022),('thermal',-1.96,-0.45,'thermal',0.020),('power',-1.88,-0.36,'power',0.017),('data',-1.80,-0.27,'data',0.014)]
for nm,y,z,mat,r in systems:
    polyline(nm,[(xmin+0.12,y,z),(xmax-0.12,y,z)],r,mat)
for j,x in enumerate(np.linspace(-3.4,3.4,12)):
    polyline(f'branchW{j}',[(x,-2.20,-0.72),(x,-1.95,-0.72),(x,-1.95,-0.18)],0.012,'water')
    polyline(f'branchP{j}',[(x+0.04,-1.88,-0.36),(x+0.04,-1.70,-0.36),(x+0.04,-1.70,-0.05)],0.009,'power')
for i,x in enumerate(np.linspace(-3.0,3.0,8)):
    box(f'manifold_{i}',(x,-1.38,-0.64),(0.48,0.18,0.16),'dark')
    for k in range(3):
        xx=x-0.13+k*0.13; between(f'valvestem_{i}_{k}',(xx,-1.28,-0.56),(xx,-1.18,-0.56),0.018,'steel',10); torus(f'valve_{i}_{k}',(xx,-1.12,-0.56),0.052,0.010,'yellow','y')

ths=np.linspace(0.02,math.pi-0.02,52)
for ri,x in enumerate(np.linspace(xmin+0.22,xmax-0.22,12)):
    pts=[(x,RY*math.cos(t),arch0+ARCH*math.sin(t)) for t in ths]; polyline(f'rib{ri}',pts,0.040,'steel',16)
for pi,t in enumerate(np.linspace(0.14,math.pi-0.14,9)):
    y=RY*math.cos(t); z=arch0+ARCH*math.sin(t); between(f'purlin{pi}',(xmin+0.18,y,z),(xmax-0.18,y,z),0.028,'steel',14)
for gi,t in enumerate(np.linspace(0.12,2.58,16)):
    y=RY*math.cos(t); z=arch0+ARCH*math.sin(t)
    m=trimesh.creation.box(extents=(7.85,0.18,0.012)); m.apply_transform(rotation_matrix(t+math.pi/2,[1,0,0])); m.apply_translation((0,y,z)); add(f'glass{gi}',m,'glass')

solar_theta=[2.10,2.32]
for row,t in enumerate(solar_theta):
    for col,x in enumerate(np.linspace(-3.15,2.35,6)):
        y=RY*math.cos(t)-0.035; z=arch0+ARCH*math.sin(t)+0.085
        m=trimesh.creation.box(extents=(0.82,0.62,0.035)); m.apply_transform(rotation_matrix(t+math.pi/2,[1,0,0])); m.apply_translation((x,y,z)); add(f'solar_{row}_{col}',m,'solar')
        rail=trimesh.creation.box(extents=(0.85,0.035,0.028)); rail.apply_transform(rotation_matrix(t+math.pi/2,[1,0,0])); rail.apply_translation((x,y,z-0.03)); add(f'solarrail_{row}_{col}',rail,'steel')
        for k in range(1,4):
            g=trimesh.creation.box(extents=(0.010,0.58,0.007)); g.apply_transform(rotation_matrix(t+math.pi/2,[1,0,0])); g.apply_translation((x-0.41+k*0.205,y,z+0.024)); add(f'sgridv{row}_{col}_{k}',g,'solargrid')

duct_y=0.25; duct_z=arch0+ARCH-0.20
between('duct_spine_left',(-2.85,duct_y-0.24,duct_z),(2.65,duct_y-0.24,duct_z),0.13,'steel',22)
between('duct_spine_right',(-2.85,duct_y+0.24,duct_z),(2.65,duct_y+0.24,duct_z),0.13,'steel',22)
for i,x in enumerate(np.linspace(-2.25,1.95,4)):
    torus(f'fanring_{i}',(x,duct_y,duct_z),0.255,0.040,'dark','x')
    cyl(f'fanhub_{i}',(x,duct_y,duct_z),0.050,0.12,'dark','x',22)
    for b in range(8): blade(f'blade_{i}_{b}',(x,duct_y,duct_z),0.18,0.055,0.024,b*math.pi/4,'dark')
    between(f'fanbraceA_{i}',(x,duct_y-0.24,duct_z),(x,duct_y-0.20,duct_z),0.030,'steel',12)
    between(f'fanbraceB_{i}',(x,duct_y+0.20,duct_z),(x,duct_y+0.24,duct_z),0.030,'steel',12)
cyl('wind_inlet',(-3.12,duct_y,duct_z),0.26,0.52,'steel','x',28)
cyl('wind_outlet',(2.92,duct_y,duct_z),0.23,0.50,'steel','x',28)
for idx,(mat,dy) in enumerate([('water',0.48),('nutrient',0.57),('air',0.66)]):
    between(f'roofline{idx}',(xmin+0.30,dy,arch0+ARCH-0.08),(xmax-0.30,dy,arch0+ARCH-0.08),0.014,mat,12)

beds=[(-2.85,-1.25,1.15,.70,'leaf'),(-1.35,-1.25,1.15,.70,'fruit'),(0.15,-1.25,1.15,.70,'leaf'),(1.65,-1.25,1.15,.70,'tall'),(3.05,-1.25,1.05,.68,'herb'),(-2.4,0.05,1.28,.72,'mixed'),(-0.7,0.05,1.28,.72,'leaf'),(1.0,0.05,1.28,.72,'mixed'),(2.7,0.05,1.20,.72,'tall'),(-2.25,1.30,1.18,.64,'herb'),(-0.65,1.30,1.18,.64,'fruit'),(0.95,1.30,1.18,.64,'leaf'),(2.55,1.30,1.18,.64,'tall')]
for bi,(x,y,sx,sy,kind) in enumerate(beds):
    box(f'bed{bi}',(x,y,deck+0.18),(sx,sy,0.26),'steel'); box(f'soil{bi}',(x,y,deck+0.33),(sx*0.92,sy*0.88,0.05),'soil')
    between(f'irrig{bi}',(x-sx*.40,y-sy*.36,deck+0.42),(x+sx*.40,y-sy*.36,deck+0.42),0.010,'water',10)
    nx=5 if sx>1.2 else 4; ny=3
    for ix in range(nx):
        for iy in range(ny):
            px=x-sx*.36+ix*(sx*.72/(nx-1)); py=y-sy*.28+iy*(sy*.56/(ny-1)); seed=(bi*31+ix*7+iy*13)%11
            if kind=='tall':
                h=0.62+0.10*((seed%4)/3); between(f'stem{bi}_{ix}_{iy}',(px,py,deck+.36),(px,py,deck+.36+h),0.012,'leafA',8)
                for lv,zf in enumerate((.35,.58,.80)):
                    side=-1 if lv%2 else 1; ell(f'leaf{bi}_{ix}_{iy}_{lv}',(px+side*.08,py,deck+.36+h*zf),(.13,.032,.018),'leafC',1)
            elif kind=='fruit' or kind=='mixed':
                h=.32+.07*((seed%4)/3); between(f'stem{bi}_{ix}_{iy}',(px,py,deck+.36),(px,py,deck+.36+h),.010,'leafA',8)
                for a in (0,2.1,4.2): ell(f'leaf{bi}_{ix}_{iy}_{a}',(px+.055*math.cos(a),py+.055*math.sin(a),deck+.36+h*.72),(.075,.035,.018),'leafB',1)
                if seed%2==0: ell(f'fruit{bi}_{ix}_{iy}',(px+.025,py,deck+.36+h-.02),(.030,.030,.032),'fruit',1)
            else:
                h=.18+.06*((seed%5)/4); between(f'stem{bi}_{ix}_{iy}',(px,py,deck+.36),(px,py,deck+.36+h),.009,'leafA',8)
                for a in (0,2.4,4.8): ell(f'leaf{bi}_{ix}_{iy}_{a}',(px+.045*math.cos(a),py+.045*math.sin(a),deck+.36+h),(.068,.032,.017),'leafB' if kind!='herb' else 'leafC',1)
                if kind=='herb' and seed%3==0: ell(f'flower{bi}_{ix}_{iy}',(px,py,deck+.36+h+.025),(.022,.022,.014),'flower',1)

railz=arch0+1.90
for y in (-1.12,-0.40,0.40,1.12): between(f'hangrail{y}',(-3.45,y,railz),(3.35,y,railz),0.020,'dark',12)
hi=0
for x in np.linspace(-2.9,2.8,7):
    for y in (-1.10,-0.38,0.38,1.10):
        if (hi%5)==0: hi+=1; continue
        drop=.28+.07*(hi%3); between(f'hanger{hi}',(x,y,railz),(x,y,railz-drop),.005,'dark',8); cyl(f'pot{hi}',(x,y,railz-drop-.05),.11,.10,'soil','z',18)
        for v in range(6):
            a=2*math.pi*v/6; ex=x+.13*math.cos(a); ey=y+.13*math.sin(a); ez=railz-drop-.28-.04*(v%2)
            between(f'vine{hi}_{v}',(x,y,railz-drop-.02),(ex,ey,ez),.007,'leafA',8)
            for lv in (0.35,.70):
                px=x*(1-lv)+ex*lv; py=y*(1-lv)+ey*lv; pz=(railz-drop-.02)*(1-lv)+ez*lv
                ell(f'vleaf{hi}_{v}_{lv}',(px,py,pz),(.040,.024,.012),'leafB',1)
            if v%2==0: ell(f'vfruit{hi}_{v}',(ex,ey,ez+.03),(.024,.024,.026),'fruit',1)
        hi+=1

box('walkway',(0,-.02,deck+.09),(7.45,.50,.06),'panel')
for y in (-.34,.34): between(f'walkrail{y}',(-3.6,y,deck+.58),(3.5,y,deck+.58),.014,'steel',10)
for x in np.linspace(-3.5,3.4,12):
    for y in (-.34,.34): between(f'walkpost{x}_{y}',(x,y,deck+.22),(x,y,deck+.58),.012,'steel',10)
for i,(x,y) in enumerate([(-1.0,1.80),(-.45,1.80),(0.10,1.80),(.65,1.80)]):
    box(f'intcab{i}',(x,y,deck+.55),(.42,.32,.66),'cabinet'); box(f'intface{i}',(x,y-.17,deck+.55),(.26,.02,.28),'panel')
for i,x in enumerate(np.linspace(-3.3,3.3,10)):
    polyline(f'water_riser{i}',[(x,-2.20,-.72),(x,-2.05,-.72),(x,-2.05,deck+.28)],.010,'water',10)
    if i%2==0: polyline(f'nutr_riser{i}',[(x+.035,-2.12,-.63),(x+.035,-1.98,-.63),(x+.035,-1.98,deck+.26)],.008,'nutrient',10)
for z in (-.80,-.45,-.10): between(f'front_guard{z}',(xmin-.02,-2.38,z),(xmax+.02,-2.38,z),.022,'dark',12)
for x in np.linspace(xmin+.1,xmax-.1,9): between(f'guardpost{x}',(x,-2.38,-.85),(x,-2.38,.02),.020,'dark',12)

scene.export(GLB)
G=collections.defaultdict(list)
for g in scene.geometry.values():
    if isinstance(g,trimesh.Trimesh) and len(g.faces): G[g.metadata.get('mat','steel')].append(g)
merged={k:trimesh.util.concatenate(v) for k,v in G.items()}
allb=np.array([m.bounds for m in merged.values()]); mn=allb[:,0,:].min(axis=0); mx=allb[:,1,:].max(axis=0)
shift=np.array([-(mn[0]+mx[0])/2,-(mn[1]+mx[1])/2,-mn[2]])
for m in merged.values(): m.apply_translation(shift)

lines=['#usda 1.0','(','    defaultPrim = "Greenhouse"','    metersPerUnit = 1','    upAxis = "Z"',')','','def Xform "Greenhouse"','{','    def Scope "Materials"','    {']
for mat,(rgba,metal,rough) in M.items():
    if mat not in merged: continue
    r,g,b,a=[c/255 for c in rgba]
    lines += [f'        def Material "{mat}"','        {',f'            token outputs:surface.connect = </Greenhouse/Materials/{mat}/Preview.outputs:surface>','            def Shader "Preview"','            {','                uniform token info:id = "UsdPreviewSurface"',f'                color3f inputs:diffuseColor = ({r:.6f}, {g:.6f}, {b:.6f})',f'                float inputs:metallic = {metal:.6f}',f'                float inputs:roughness = {rough:.6f}',f'                float inputs:opacity = {a:.6f}','                token outputs:surface','            }','        }']
lines += ['    }']
for mat,m in merged.items():
    V=np.asarray(m.vertices,float); F=np.asarray(m.faces,int); idx=F.reshape(-1)
    lines += [f'    def Mesh "Mesh_{mat}"','    {','        uniform token subdivisionScheme = "none"','        uniform bool doubleSided = true',f'        rel material:binding = </Greenhouse/Materials/{mat}>','        point3f[] points = [']
    lines += [f'            ({x:.7g}, {y:.7g}, {z:.7g}),' for x,y,z in V]
    lines += ['        ]','        int[] faceVertexCounts = [']
    for j in range(0,len(F),96): lines.append('            '+', '.join(['3']*min(96,len(F)-j))+',')
    lines += ['        ]','        int[] faceVertexIndices = [']
    for j in range(0,len(idx),96): lines.append('            '+', '.join(map(str,idx[j:j+96]))+',')
    lines += ['        ]','    }']
lines += ['}']
USDA.write_text('\n'.join(lines),encoding='utf-8')
payload=USDA.read_bytes()
with open(USDZ,'wb') as fp:
    with zipfile.ZipFile(fp,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as zf:
        zi=zipfile.ZipInfo('model.usda'); zi.compress_type=zipfile.ZIP_STORED
        base=fp.tell()+30+len(zi.filename.encode()); pad=(-base)%64
        if pad and pad<4: pad+=64
        if pad: zi.extra=struct.pack('<HH',0xCAFE,pad-4)+b'\0'*(pad-4)
        zf.writestr(zi,payload)
with zipfile.ZipFile(USDZ) as zf:
    info=zf.infolist()[0]; off=info.header_offset+30+len(info.filename.encode())+len(info.extra)
    assert off%64==0 and info.compress_type==zipfile.ZIP_STORED and info.filename=='model.usda'

print('USDZ',USDZ,USDZ.stat().st_size)
print('GLB',GLB,GLB.stat().st_size)
print('materials',len(merged),'geometries',len(scene.geometry),'verts',sum(len(m.vertices) for m in merged.values()),'faces',sum(len(m.faces) for m in merged.values()))
