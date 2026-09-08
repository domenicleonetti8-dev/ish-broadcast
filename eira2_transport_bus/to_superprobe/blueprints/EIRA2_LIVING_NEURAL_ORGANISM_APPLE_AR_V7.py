from __future__ import annotations

import math
from typing import Any

SCHEMA = "eira2_living_neural_organism_apple_ar_v7"
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def _nid(row: dict[str, Any]) -> str:
    return str(row.get("_id") or row.get("id") or "")


def _all(atlas: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    neurons = [dict(x) for x in (atlas.page(cursor=0, limit=5000, include_paths=False).get("neurons") or []) if isinstance(x, dict)]
    fibers = [dict(x) for x in ((atlas.fibers_for(limit=30000) or {}).get("fibers") or []) if isinstance(x, dict)]
    seen = {_nid(x) for x in neurons if _nid(x)}
    for fiber in fibers:
        for key in ("source", "target"):
            ident = str(fiber.get(key) or "")
            if ident and ident not in seen:
                row = atlas.neuron(ident)
                if row:
                    neurons.append(dict(row)); seen.add(ident)
    return neurons, fibers


def runtime_region(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(k) or "") for k in ("_id", "id", "logical_path", "kind", "cluster")).casefold()
    rules = (("universe_library","universe_library"),("memory","memory"),("history","memory"),("evidence","evidence"),("reason","reasoning"),("identity","identity"),("delivery","delivery"),("conversation","conversation_spine"),("watcher","watcher"),("superprobe","superprobe"),("extension","extensions"),("learn","learning"))
    for needle, region in rules:
        if needle in text:
            return region
    return "organism"


def spherical_positions(neurons: list[dict[str, Any]]) -> dict[str, tuple[float,float,float]]:
    left = [n for n in neurons if n.get("hemisphere") == "left" and not n.get("spine")]
    right = [n for n in neurons if n.get("hemisphere") == "right" and not n.get("spine")]
    mid = [n for n in neurons if n not in left and n not in right]
    out: dict[str, tuple[float,float,float]] = {}

    def side(items: list[dict[str, Any]], sign: float) -> None:
        total = max(1, len(items))
        for i, row in enumerate(sorted(items, key=_nid)):
            u = (i + 0.5) / total
            z = 1.0 - 2.0 * u
            rr = math.sqrt(max(0.0, 1.0 - z*z))
            theta = i * GOLDEN + (0.0 if sign < 0 else math.pi/7.0)
            p = [sign*(0.04 + 0.90*abs(rr*math.cos(theta))), 0.94*rr*math.sin(theta), 0.94*z]
            length = math.sqrt(sum(v*v for v in p)) or 1.0
            shell = 0.88 + 0.06*((i % 13)/12.0)
            out[_nid(row)] = tuple(v/length*shell for v in p)

    side(left, -1.0); side(right, 1.0)
    spine = [r for r in mid if r.get("spine")]
    other = [r for r in mid if not r.get("spine")]
    for i, row in enumerate(sorted(spine, key=_nid)):
        t = 0.5 if len(spine) == 1 else i/max(1, len(spine)-1)
        out[_nid(row)] = (0.0, 0.0, -0.94 + 1.88*t)
    for i, row in enumerate(sorted(other, key=_nid)):
        a = i * GOLDEN
        r = 0.18 + 0.10*((i % 9)/8.0)
        out[_nid(row)] = (r*math.cos(a), r*math.sin(a), -0.22 + 0.44*((i % 17)/16.0))
    return out


def build_mesh_contract(atlas: Any) -> dict[str, Any]:
    neurons, fibers = _all(atlas)
    positions = spherical_positions(neurons)
    node_rows = []
    for row in neurons:
        ident = _nid(row)
        if ident and ident in positions:
            node_rows.append({
                "id": ident,
                "position": positions[ident],
                "region": runtime_region(row),
                "hemisphere": row.get("hemisphere"),
                "spine": bool(row.get("spine")),
                "activity_key": ident,
            })
    fiber_rows = []
    for f in fibers:
        source, target = str(f.get("source") or ""), str(f.get("target") or "")
        if source in positions and target in positions and source != target:
            fiber_rows.append({"source": source, "target": target, "conductive": bool(f.get("conductive"))})
    return {
        "schema": SCHEMA,
        "render_strategy": "material-batched_meshes_not_thousands_of_prims",
        "visual_contract": {
            "shape": "full spherical neurological organism",
            "dense_surface_neurons": True,
            "layered_neural_tissue": True,
            "branching_dendrites": True,
            "cross_depth_synapses": True,
            "corpus_callosum_bridges": True,
            "radiant_truth_core": True,
            "vertical_spine": True,
            "living_hall_of_records": "inside organism",
            "balls_on_strings": False,
            "one_runtime_one_http_server": True,
        },
        "neurons": node_rows,
        "fibers": fiber_rows,
        "reactivity": {
            "source": "NeuralActivity/live execution trace",
            "input": "illuminate selected neuron ids and runtime regions",
            "answer": "propagate emission along evidenced fibers used by accepted answer trace",
            "idle": "subtle non-authoritative spontaneous pulses only",
        },
    }
