from __future__ import annotations

import math
from pathlib import Path
from typing import Any

SCHEMA = "eira2_spherical_neural_organism_apple_ar_v4"
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def _nid(row: dict[str, Any]) -> str:
    return str(row.get("_id") or row.get("id") or "")


def _all_neurons(atlas: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    page = atlas.page(cursor=0, limit=5000, include_paths=False)
    neurons = [dict(x) for x in (page.get("neurons") or []) if isinstance(x, dict)]
    fibers = [dict(x) for x in ((atlas.fibers_for(limit=30000) or {}).get("fibers") or []) if isinstance(x, dict)]
    seen = {_nid(x) for x in neurons if _nid(x)}
    for f in fibers:
        for key in ("source", "target"):
            ident = str(f.get(key) or "")
            if ident and ident not in seen:
                row = atlas.neuron(ident)
                if row:
                    neurons.append(dict(row)); seen.add(ident)
    return neurons, fibers


def spherical_positions(neurons: list[dict[str, Any]]) -> dict[str, tuple[float,float,float]]:
    left=[n for n in neurons if n.get("hemisphere")=="left" and not n.get("spine")]
    right=[n for n in neurons if n.get("hemisphere")=="right" and not n.get("spine")]
    mid=[n for n in neurons if n not in left and n not in right]
    out: dict[str, tuple[float,float,float]] = {}
    def side(items: list[dict[str,Any]], sign: float) -> None:
        total=max(1,len(items))
        for i,row in enumerate(sorted(items,key=_nid)):
            u=(i+0.5)/total
            z=1.0-2.0*u
            theta=i*GOLDEN + (0.0 if sign < 0 else math.pi/7.0)
            radial=math.sqrt(max(0.0,1.0-z*z))
            x=sign*(0.075+0.865*abs(radial*math.cos(theta)))
            y=0.92*radial*math.sin(theta)
            zz=0.92*z
            length=math.sqrt(x*x+y*y+zz*zz) or 1.0
            shell=0.86+0.075*((i%11)/10.0)
            out[_nid(row)]=(x/length*shell,y/length*shell,zz/length*shell)
    side(left,-1.0); side(right,1.0)
    spine=[r for r in mid if r.get("spine")]
    other=[r for r in mid if not r.get("spine")]
    for i,row in enumerate(sorted(spine,key=_nid)):
        t=0.5 if len(spine)==1 else i/max(1,len(spine)-1)
        out[_nid(row)]=(0.0,0.0,-0.94+1.88*t)
    for i,row in enumerate(sorted(other,key=_nid)):
        a=i*GOLDEN
        r=0.18+0.10*((i%9)/8.0)
        out[_nid(row)]=(r*math.cos(a),r*math.sin(a),-0.22+0.44*((i%17)/16.0))
    return out


def runtime_region(row: dict[str,Any]) -> str:
    text=" ".join(str(row.get(k) or "") for k in ("_id","id","logical_path","kind","cluster")).casefold()
    rules=(
        ("universe_library","universe_library"),("memory","memory"),("history","memory"),
        ("evidence","evidence"),("reason","reasoning"),("identity","identity"),
        ("delivery","delivery"),("conversation","conversation_spine"),("watcher","watcher"),
        ("superprobe","superprobe"),("extension","extensions"),("learn","learning"),
    )
    for needle,region in rules:
        if needle in text: return region
    return "organism"


def build_contract(atlas: Any) -> dict[str,Any]:
    neurons,fibers=_all_neurons(atlas)
    positions=spherical_positions(neurons)
    rows=[]
    for row in neurons:
        ident=_nid(row)
        if not ident or ident not in positions: continue
        rows.append({
            "id":ident,
            "position":positions[ident],
            "hemisphere":row.get("hemisphere"),
            "spine":bool(row.get("spine")),
            "region":runtime_region(row),
            "activity_key":ident,
        })
    bridges=[]
    for f in fibers:
        s,t=str(f.get("source") or ""),str(f.get("target") or "")
        if s in positions and t in positions and s!=t:
            bridges.append({"source":s,"target":t,"conductive":bool(f.get("conductive"))})
    return {
        "schema":SCHEMA,
        "visual_contract":{
            "shape":"full spherical organism",
            "nodes_on_outer_shell":True,
            "central_fissure":True,
            "vertical_spine":True,
            "cross_hemisphere_bridges":True,
            "central_truth_core":True,
            "living_hall_of_records":"inside central organism",
            "one_runtime_one_http_server":True,
        },
        "neurons":rows,
        "fibers":bridges,
        "reactivity":{
            "source":"NeuralActivity/live execution trace",
            "behavior":"flash matching activity_key neurons and propagate along evidenced fibers",
            "answer_mapping":"input and accepted answer trace select corresponding runtime regions and neuron ids",
            "idle":"subtle non-authoritative spontaneous pulse only",
        },
    }


def build_brain_usdz(atlas: Any, output: Path) -> Path:
    """Integration entrypoint. Existing LIVE apple_ar.py remains packaging authority until this candidate is qualified.

    The contract returned by build_contract is consumed by the V4 renderer replacement so every real atlas neuron is
    placed on the spherical organism and every evidenced fiber remains a real pathway. This file intentionally does not
    invent a second HTTP server or second AR authority.
    """
    raise RuntimeError("candidate_requires_renderer_qualification_before_live_packaging")
