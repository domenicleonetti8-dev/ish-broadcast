from __future__ import annotations

from typing import Any

SCHEMA = "eira2_living_neural_organism_apple_ar_v8"
ARTIFACT = "eira2_transport_bus/to_superprobe/artifacts/EIRA2_LIVING_NEURAL_ORGANISM_V8.usdz"
REGIONS = (
    "conversation_spine","memory","evidence","reasoning","identity",
    "universe_library","extensions","watcher","superprobe","delivery",
)


def activity_regions(activity: dict[str, Any] | None) -> dict[str, float]:
    activity = activity or {}
    out = {name: 0.0 for name in REGIONS}
    rows = activity.get("events") or activity.get("activity") or ()
    if not isinstance(rows, (list, tuple)):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get(k) or "") for k in ("id","node","path","topic","service","cluster","region")).casefold()
        weight = float(row.get("weight") or row.get("intensity") or 1.0)
        mapping = (
            (("conversation","spine","input"),"conversation_spine"),
            (("memory","history"),"memory"),
            (("evidence","source","verify"),"evidence"),
            (("reason","analysis","cognition"),"reasoning"),
            (("identity",),"identity"),
            (("universe_library","library","archive"),"universe_library"),
            (("extension",),"extensions"),
            (("watcher",),"watcher"),
            (("superprobe",),"superprobe"),
            (("delivery","response","output"),"delivery"),
        )
        for needles, region in mapping:
            if any(n in text for n in needles):
                out[region] = min(1.0, out[region] + max(0.0, weight))
    return out


def build_contract(atlas: Any, activity: dict[str, Any] | None = None) -> dict[str, Any]:
    page = atlas.page(cursor=0, limit=5000, include_paths=False)
    neurons = [dict(x) for x in (page.get("neurons") or []) if isinstance(x, dict)]
    fibers = [dict(x) for x in ((atlas.fibers_for(limit=30000) or {}).get("fibers") or []) if isinstance(x, dict)]
    return {
        "schema": SCHEMA,
        "artifact": ARTIFACT,
        "visual_contract": {
            "shape": "full spherical neurological organism",
            "optimized_material_meshes": 8,
            "max_animation_overlay_prims": 24,
            "three_depth_neural_tissue": True,
            "branching_dendrites": True,
            "cross_depth_synapses": True,
            "corpus_callosum_bridges": True,
            "radiant_pulsing_core": True,
            "vertical_luminous_spine": True,
            "traveling_neurological_impulses": True,
            "living_hall_of_records": "inside organism",
            "one_runtime_one_http_server": True,
            "quicklook_loadability_preserves_v7_mesh_strategy": True,
        },
        "runtime_activity": activity_regions(activity),
        "neurons": neurons,
        "fibers": fibers,
        "reactivity": {
            "source": "NeuralActivity live execution trace",
            "selection": "active Eira node ids and canonical regions only",
            "propagation": "evidenced atlas fibers only",
            "input_path": "conversation -> invoked systems -> accepted answer -> delivery",
            "idle": "subtle cosmetic pulse explicitly not runtime truth",
        },
    }
