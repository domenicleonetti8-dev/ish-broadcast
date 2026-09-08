from __future__ import annotations

import math
from typing import Any

SCHEMA = "eira2_luminous_neural_organism_apple_ar_v5"
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def _nid(row: dict[str, Any]) -> str:
    return str(row.get("_id") or row.get("id") or "")


def runtime_region(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(k) or "") for k in ("_id", "id", "logical_path", "kind", "cluster")).casefold()
    rules = (("universe_library","universe_library"),("memory","memory"),("history","memory"),("evidence","evidence"),("reason","reasoning"),("identity","identity"),("delivery","delivery"),("conversation","conversation_spine"),("watcher","watcher"),("superprobe","superprobe"),("extension","extensions"),("learn","learning"))
    for needle, region in rules:
        if needle in text:
            return region
    return "organism"


def _all(atlas: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    neurons=[dict(x) for x in (atlas.page(cursor=0,limit=5000,include_paths=False).get("neurons") or []) if isinstance(x,dict)]
    fibers=[dict(x) for x in ((atlas.fibers_for(limit=30000) or {}).get("fibers") or []) if isinstance(x,dict)]
    seen={_nid(x) for x in neurons if _nid(x)}
    for f in fibers:
        for key in ("source","target"):
            ident=str(f.get(key) or "")
            if ident and ident not in seen:
                row=atlas.neuron(ident)
                if row: neurons.append(dict(row)); seen.add(ident)
    return neurons,fibers


def spherical_positions(neurons: list[dict[str, Any]]) -> dict[str, tuple[float,float,float]]:
    left=[n for n in neurons if n.get("hemisphere")=="left" and not n.get("spine")]
    right=[n for n in neurons if n.get("hemisphere")=="right" and not n.get("spine")]
    mid=[n for n in neurons if n not in left and n not in right]
    out={}
    def side(items,sign):
        total=max(1,len(items))
        for i,row in enumerate(sorted(items,key=_nid)):
            u=(i+.5)/total; z=1-2*u; rr=math.sqrt(max(0,1-z*z)); th=i*GOLDEN+(0 if sign<0 else math.pi/7)
            p=[sign*(.04+.90*abs(rr*math.cos(th))),.94*rr*math.sin(th),.94*z]
            ln=math.sqrt(sum(v*v for v in p)) or 1; shell=.88+.06*((i%13)/12)
            out[_nid(row)]=tuple(v/ln*shell for v in p)
    side(left,-1); side(right,1)
    spine=[r for r in mid if r.get("spine")]; other=[r for r in mid if not r.get("spine")]
    for i,row in enumerate(sorted(spine,key=_nid)):
        t=.5 if len(spine)==1 else i/max(1,len(spine)-1); out[_nid(row)]=(0,0,-.94+1.88*t)
    for i,row in enumerate(sorted(other,key=_nid)):
        a=i*GOLDEN; r=.18+.10*((i%9)/8); out[_nid(row)]=(r*math.cos(a),r*math.sin(a),-.22+.44*((i%17)/16))
    return out


def build_contract(atlas: Any) -> dict[str, Any]:
    neurons,fibers=_all(atlas); positions=spherical_positions(neurons)
    rows=[]
    for row in neurons:
        ident=_nid(row)
        if ident and ident in positions:
            rows.append({"id":ident,"position":positions[ident],"hemisphere":row.get("hemisphere"),"spine":bool(row.get("spine")),"region":runtime_region(row),"activity_key":ident,"visual_role":"soma"})
    bridges=[]
    for f in fibers:
        s,t=str(f.get("source") or ""),str(f.get("target") or "")
        if s in positions and t in positions and s!=t:
            bridges.append({"source":s,"target":t,"conductive":bool(f.get("conductive")),"visual_role":"axon"})
    return {"schema":SCHEMA,"visual_contract":{"shape":"full luminous spherical neurological organism","three_depth_neural_tissue":True,"branching_dendrites":True,"cross_depth_synapses":True,"corpus_callosum_bridges":True,"radiant_cognition_core":True,"vertical_luminous_spine":True,"living_hall_of_records":"inside organism","balls_on_strings":False,"one_runtime_one_http_server":True},"neurons":rows,"fibers":bridges,"reactivity":{"source":"NeuralActivity/live execution trace","input":"illuminate neuron ids and anatomical regions selected by current input trace","answer":"propagate illumination along evidenced fibers participating in accepted answer trace","flash":"emissive pulse rather than geometry teleportation","idle":"subtle spontaneous background pulses, explicitly non-authoritative"}}
