from __future__ import annotations

import math
from itertools import count

import numpy as np


def src(conf=0.85, provenance="inferred", reason="reference-regression fixture"):
    return {"provenance": provenance, "confidence": conf, "reason": reason}


def transform(location=(0,0,0), rotation=(0,0,0), scale=(1,1,1)):
    return {"location": list(location), "rotation_deg": list(rotation), "scale": list(scale)}


def part(pid, name, geometry, *, location=(0,0,0), rotation=(0,0,0), system="", subsystem="", visual=None, engineering=None, source=None):
    return {
        "part_id": pid,
        "name": name,
        "geometry": geometry,
        "transform": transform(location, rotation),
        "system": system,
        "subsystem": subsystem,
        "visual": visual or {},
        "engineering": engineering or {},
        "source": source or src(),
    }


def boxg(x,y,z):
    return {"kind":"primitive","primitive":"box","dimensions":{"x":x,"y":y,"z":z}}


def cylg(radius,height,segments=40):
    return {"kind":"primitive","primitive":"cylinder","dimensions":{"radius":radius,"height":height,"segments":segments}}


def sphereg(radius):
    return {"kind":"primitive","primitive":"sphere","dimensions":{"radius":radius,"subdivisions":2}}


def curve(points,radius=0.018,basis="POLY"):
    return {"kind":"curve","basis":basis,"points":[list(x) for x in points],"radius":radius}


def build_reference_greenhouse():
    """Dense regression specimen based on the supplied greenhouse concept.

    This fixture lives in tests only. It deliberately exercises the general renderer:
    transparent freeform shell, repeated structure, solar/wind clearance, moving rotors,
    dense service base, routed utilities, multiple plant families and suspended planters.
    """
    parts=[]; joints=[]; behaviors=[]; flows=[]; dimensions=[]; relationships=[]
    ids=count()
    def pid(prefix): return f"{prefix}_{next(ids):04d}"

    L=8.2; W=4.7; H=2.8; deck_z=1.15

    base_id="base"
    parts.append(part(base_id,"Structural service base",boxg(L+0.30,W+0.28,0.22),location=(0,0,0.11),system="structure",subsystem="base",visual={"role":"structural base","support_required":True,"color":"#6e747b","metallic":0.75,"roughness":0.28},source=src(.96,"assumed","dimensions selected to match reference proportions")))
    deck_id="deck"
    parts.append(part(deck_id,"Grow-deck / service ceiling",boxg(L,W,0.16),location=(0,0,deck_z),system="structure",subsystem="deck",visual={"role":"structural deck","support_required":False,"color":"#b4b8bc","metallic":0.35,"roughness":0.42}))

    # Service base longitudinal beams and uprights.
    for y in (-2.05,-1.35,-0.65,0.65,1.35,2.05):
        parts.append(part(pid("beam"),"Service base longitudinal beam",boxg(L-0.25,0.08,0.12),location=(0,y,0.38),system="structure",subsystem="service frame",visual={"role":"mounted structural member","support_required":False,"color":"#6e747b","metallic":0.8,"roughness":0.25}))
    for x in np.linspace(-3.7,3.7,11):
        for y in (-2.05,2.05):
            parts.append(part(pid("post"),"Service-base support post",boxg(0.10,0.10,0.72),location=(float(x),y,0.72),system="structure",subsystem="service frame",visual={"role":"mounted structural member","support_required":False,"color":"#747a81","metallic":0.8,"roughness":0.25}))

    # Arched ribs and transparent shell.
    for x in np.linspace(-3.8,3.8,15):
        pts=[[float(x), (W/2)*math.cos(t), deck_z+H*math.sin(t)] for t in np.linspace(0,math.pi,42)]
        parts.append(part(pid("rib"),"Primary arched structural rib",curve(pts,0.042),system="structure",subsystem="shell frame",visual={"role":"mounted structural rib","support_required":False,"color":"#aab0b5","metallic":0.82,"roughness":0.20}))
    for t in np.linspace(0.15,math.pi-0.15,9):
        y=(W/2)*math.cos(t); z=deck_z+H*math.sin(t)
        parts.append(part(pid("purlin"),"Longitudinal shell rail",curve([[-3.9,y,z],[3.9,y,z]],0.026),system="structure",subsystem="shell frame",visual={"role":"mounted structural rail","support_required":False,"color":"#9ba2a9","metallic":0.82,"roughness":0.22}))
    grid=[]
    for x in np.linspace(-3.9,3.9,24):
        row=[]
        for t in np.linspace(0.03,math.pi-0.03,44):
            row.append([float(x),(W/2+0.035)*math.cos(t),deck_z+(H+0.04)*math.sin(t)])
        grid.append(row)
    parts.append(part("shell","Transparent ETFE/glazing shell",{"kind":"surface","grid":grid},system="structure",subsystem="shell",visual={"role":"transparent shell","support_required":False,"color":"#b9e2ef","alpha":0.20,"metallic":0.0,"roughness":0.06}))

    # Clean solar band along one side of the crown; distinct wind clearance group.
    solar_xs=np.linspace(-3.35,2.85,8)
    solar_ts=(2.05,2.26,2.47)
    for ix,x in enumerate(solar_xs):
        for jt,t in enumerate(solar_ts):
            y=(W/2+0.14)*math.cos(t); z=deck_z+(H+0.14)*math.sin(t)
            parts.append(part(pid("solar"),f"Solar module {ix+1}-{jt+1}",boxg(0.72,0.48,0.035),location=(float(x),y,z),rotation=(math.degrees(t-math.pi/2),0,0),system="power",subsystem="solar array",visual={"role":"solar module","support_required":False,"clearance_group":"solar","color":"#173a78","metallic":0.18,"roughness":0.24}))

    # Wind duct occupies a different roof lane and contains four moving rotors.
    duct_pts=[]
    for t in np.linspace(1.18,1.55,28):
        duct_pts.append([-0.4,(W/2-0.42)*math.cos(t),deck_z+(H-0.08)*math.sin(t)])
    duct_id="wind_duct"
    parts.append(part(duct_id,"Arched wind-energy duct",curve(duct_pts,0.18),system="wind energy",subsystem="arched turbine duct",visual={"role":"wind turbine duct","support_required":False,"clearance_group":"wind","color":"#737a81","metallic":0.78,"roughness":0.23}))
    for i,x in enumerate(np.linspace(-1.25,1.25,4)):
        housing=pid("fan_housing")
        rotor=pid("fan_rotor")
        parts.append(part(housing,f"Turbine housing {i+1}",cylg(0.24,0.13),location=(float(x),-0.18,deck_z+H-0.30),rotation=(0,90,0),system="wind energy",subsystem="turbine",visual={"role":"wind turbine housing","support_required":False,"clearance_group":"wind","color":"#818990","metallic":0.82,"roughness":0.22}))
        parts.append(part(rotor,f"Turbine rotor {i+1}",cylg(0.18,0.035),location=(float(x),-0.25,deck_z+H-0.30),rotation=(0,90,0),system="wind energy",subsystem="turbine",visual={"role":"wind turbine rotor","support_required":False,"clearance_group":"wind","color":"#202328","metallic":0.60,"roughness":0.28}))
        joints.append({"joint_id":f"rotor_spin_{i}","kind":"continuous","parent":housing,"child":rotor,"axis":[1,0,0],"speed":4.0+0.5*i})

    # Grow beds.
    bed_centers=[
        (-2.75,-1.25),(-1.35,-1.25),(0.05,-1.25),(1.45,-1.25),(2.85,-1.25),
        (-2.35,0.0),(-0.80,0.0),(0.75,0.0),(2.30,0.0),
        (-2.35,1.25),(-0.80,1.25),(0.75,1.25),(2.30,1.25),
    ]
    bed_ids=[]
    for i,(x,y) in enumerate(bed_centers):
        bid=pid("bed"); bed_ids.append(bid)
        parts.append(part(bid,f"Raised crop bed {i+1}",boxg(1.05,0.72,0.42),location=(x,y,deck_z+0.29),system="grow system",subsystem="plant bed",visual={"role":"raised crop bed","support_required":False,"color":"#747a80","metallic":0.45,"roughness":0.40}))
        soil=pid("soil")
        parts.append(part(soil,f"Growing medium {i+1}",boxg(0.95,0.62,0.06),location=(x,y,deck_z+0.53),system="grow system",subsystem="plant bed",visual={"role":"growing medium","support_required":False,"color":"#6c4d2f","metallic":0.0,"roughness":0.9}))
        relationships.append({"kind":"mounted_on","a":bid,"b":deck_id})

        # Distinct plant family per bed, with repeated stems and leaf/fruit components.
        family=i%4
        for row in range(2):
            for col in range(4):
                px=x-0.34+col*0.22; py=y-0.18+row*0.36
                basez=deck_z+0.57
                height=(0.28+0.06*((col+i)%3)) if family in (0,3) else (0.55+0.08*((col+i)%3))
                stem=pid("plant_stem")
                pts=[[px,py,basez],[px+0.02*math.sin(i+col),py,basez+height*0.55],[px,py,basez+height]]
                parts.append(part(stem,"Living crop stem",curve(pts,0.012,"BEZIER"),system="living architecture",subsystem=["leafy greens","fruiting crops","tall stalks","herbs"][family],visual={"role":"living plant stem","support_required":False,"color":["#55a34c","#347f3a","#6d9937","#4b8d42"][family],"metallic":0.0,"roughness":0.68}))
                # Two leaves as small flattened boxes rotated around stem.
                for li,sign in enumerate((-1,1)):
                    leaf=pid("leaf")
                    parts.append(part(leaf,"Plant leaf",boxg(0.16,0.055,0.012),location=(px+0.08*sign,py,basez+height*(0.55+0.18*li)),rotation=(0,18*sign,22*sign),system="living architecture",subsystem=["leafy greens","fruiting crops","tall stalks","herbs"][family],visual={"role":"living leaf","support_required":False,"color":"#6aab4e","metallic":0.0,"roughness":0.72}))
                if family==1 and (row+col)%2==0:
                    fruit=pid("fruit")
                    parts.append(part(fruit,"Fruiting crop",sphereg(0.035),location=(px+0.05,py,basez+height*0.72),system="living architecture",subsystem="fruiting crops",visual={"role":"fruit","support_required":False,"color":"#d84835","metallic":0.0,"roughness":0.55}))

    # Overhead plant rails + hanging planters.
    for y in (-1.05,-0.35,0.35,1.05):
        rail=pid("hang_rail")
        parts.append(part(rail,"Hanging planter rail",curve([[-3.1,y,deck_z+2.35],[3.1,y,deck_z+2.35]],0.022),system="grow system",subsystem="hanging rail",visual={"role":"hanging plant rail","support_required":False,"color":"#626970","metallic":0.75,"roughness":0.26}))
        for x in np.linspace(-2.7,2.7,6):
            hanger=pid("hanger")
            pot=pid("hang_pot")
            parts.append(part(hanger,"Hanging planter suspension",curve([[float(x),y,deck_z+2.35],[float(x),y,deck_z+1.98]],0.006),system="grow system",subsystem="hanging planter",visual={"role":"suspended cable","support_required":False,"color":"#555b61","metallic":0.5,"roughness":0.35}))
            parts.append(part(pot,"Hanging planter pod",cylg(0.13,0.12,28),location=(float(x),y,deck_z+1.91),system="living architecture",subsystem="hanging planter",visual={"role":"hanging planter","support_required":False,"color":"#6f553b","metallic":0.0,"roughness":0.72}))
            relationships.append({"kind":"suspended_from","a":pot,"b":rail})
            for vi in range(3):
                vx=float(x)+(vi-1)*0.055
                vine=pid("vine")
                parts.append(part(vine,"Trailing fruiting vine",curve([[vx,y,deck_z+1.89],[vx+0.03*math.sin(vi),y+0.02*(vi-1),deck_z+1.55],[vx,y,deck_z+1.22]],0.009,"BEZIER"),system="living architecture",subsystem="hanging fruiting plants",visual={"role":"suspended vine","support_required":False,"color":"#3f8f3b","metallic":0.0,"roughness":0.72}))
                for fi in range(2):
                    parts.append(part(pid("hang_fruit"),"Hanging fruit",sphereg(0.026),location=(vx+0.025*(fi*2-1),y,deck_z+1.45-0.18*fi),system="living architecture",subsystem="hanging fruiting plants",visual={"role":"fruit","support_required":False,"color":"#d84a36","metallic":0.0,"roughness":0.55}))

    # Dense under-deck service equipment.
    for i,x in enumerate(np.linspace(-3.45,-1.55,5)):
        tid=pid("tank")
        parts.append(part(tid,f"Water/recovery tank {i+1}",cylg(0.24,0.70,40),location=(float(x),-1.82,0.58),system="water recovery",subsystem="storage",visual={"role":"water storage tank","support_required":False,"color":"#2385d8" if i<3 else "#777d84","metallic":0.25,"roughness":0.34}))
    for i,x in enumerate(np.linspace(-1.2,3.45,12)):
        cid=pid("cabinet")
        parts.append(part(cid,f"Service/control cabinet {i+1}",boxg(0.34,0.36,0.68),location=(float(x),-1.80,0.62),system=["water recovery","nutrient delivery","air circulation","thermal management","power and controls"][i%5],subsystem="service bay",visual={"role":"service cabinet","support_required":False,"color":"#696f76","metallic":0.55,"roughness":0.33}))
        if i%2==0:
            parts.append(part(pid("pump"),"Pump/motor module",cylg(0.12,0.26,30),location=(float(x),-1.50,0.42),rotation=(0,90,0),system="water recovery",subsystem="pump",visual={"role":"pump module","support_required":False,"color":"#777e84","metallic":0.62,"roughness":0.30}))

    # Neatly separated color-coded utility mains and risers.
    routes=[
        ("water","#1489db",-2.12,0.36),
        ("nutrient","#32a954",-2.04,0.44),
        ("air","#df9d28",-1.96,0.52),
        ("thermal","#d85a38",-1.88,0.60),
        ("power","#9653b8",-1.80,0.68),
        ("data","#35bfc9",-1.72,0.76),
    ]
    for name,color,y,z in routes:
        p=pid("main")
        pts=[[-3.75,y,z],[3.75,y,z],[3.75,y+0.24,z]]
        parts.append(part(p,f"{name.title()} main distribution line",curve(pts,0.018),system=name if name!="data" else "power and controls",subsystem="distribution",visual={"role":"utility pipe" if name not in ("power","data") else "cable conduit","support_required":False,"color":color,"metallic":0.12,"roughness":0.38}))
        flows.append({"flow_id":f"flow_{name}","label":f"{name} distribution","path":pts,"medium":name,"source":src(.72,"inferred")})
    for i,(x,y) in enumerate(bed_centers[::2]):
        pts=[[x,-2.12,0.36],[x,y-0.40,0.36],[x,y-0.40,deck_z+0.55]]
        parts.append(part(pid("branch"),"Bed irrigation branch",curve(pts,0.010),system="water",subsystem="irrigation",visual={"role":"utility pipe","support_required":False,"color":"#1489db","metallic":0.10,"roughness":0.40}))

    dimensions += [
        {"dimension_id":"overall_length","label":"Overall length","a":[-L/2,-W/2,0],"b":[L/2,-W/2,0],"value":L,"unit":"m","source":src(.90,"assumed","reference proportion, not measured from original sketch")},
        {"dimension_id":"overall_width","label":"Overall width","a":[-L/2,-W/2,0],"b":[-L/2,W/2,0],"value":W,"unit":"m","source":src(.90,"assumed")},
        {"dimension_id":"crown_height","label":"Crown height","a":[0,0,deck_z],"b":[0,0,deck_z+H],"value":H,"unit":"m","source":src(.90,"assumed")},
    ]

    behaviors += [
        {"behavior_id":"irrigation_cycle","target":bed_ids[0],"variable":"visibility","curve":"pulse","parameters":{"period_s":12,"duty":0.75}},
        {"behavior_id":"growth_state","target":bed_ids[-1],"variable":"scale","curve":"hold","parameters":{"value":1.0}},
    ]

    return {
        "assembly_id":"off_world_greenhouse_v8_reference",
        "name":"Off-World Greenhouse V8 Reference Regression Specimen",
        "units":"m",
        "quality":{"ground_z_m":0.0},
        "parts":parts,
        "joints":joints,
        "behaviors":behaviors,
        "dimensions":dimensions,
        "flows":flows,
        "relationships":relationships,
        "hypotheses":[
            {"claim":"The sketch is interpreted as a sealed arched crop habitat with integrated renewable energy and closed-loop service systems.","source":src(.86,"inferred")},
            {"claim":"Exact dimensions, materials and subsystem performance require experimental validation and are not treated as measurements from the sketch.","source":src(.99,"hypothesized")},
        ],
        "validation_requirements":[
            {"kind":"visual_fidelity","requirement":"Solar and wind systems remain visibly separated and mechanically mounted."},
            {"kind":"clearance","requirement":"No floating service equipment, panels, pipes or roof components."},
            {"kind":"living_architecture","requirement":"Plant families remain visibly distinct rather than one repeated generic primitive."},
        ],
    }
