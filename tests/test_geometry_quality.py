import sys
from pathlib import Path

import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eira_inventor_holographic_lab.quality import inspect_scene


def part(pid, role, loc, dims=(1, 1, 0.2), support_required=True):
    return {
        "part_id": pid,
        "name": pid,
        "system": role,
        "geometry": {"kind": "primitive", "primitive": "box", "dimensions": {"x": dims[0], "y": dims[1], "z": dims[2]}},
        "transform": {"location": list(loc), "rotation_deg": [0, 0, 0], "scale": [1, 1, 1]},
        "source": {"provenance": "inferred", "confidence": 0.8},
        "visual": {"role": role, "support_required": support_required},
    }


def add_box(scene, pid, center, extents):
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(center)
    scene.add_geometry(m, geom_name=pid, node_name=pid)


def test_solar_wind_overlap_is_blocked():
    assembly = {
        "parts": [
            part("solar", "solar array", (0, 0, 1), support_required=False),
            part("wind", "wind turbine duct", (0, 0, 1), support_required=False),
        ]
    }
    scene = trimesh.Scene()
    add_box(scene, "solar", (0, 0, 1), (1, 1, 0.2))
    add_box(scene, "wind", (0, 0, 1), (1, 1, 0.2))
    report = inspect_scene(assembly, scene)
    assert not report["ok"]
    assert any(x["code"] == "solar_wind_overlap" for x in report["issues"])


def test_separated_solar_and_wind_pass_clearance_check():
    assembly = {
        "parts": [
            part("solar", "solar array", (-1.5, 0, 1), support_required=False),
            part("wind", "wind turbine duct", (1.5, 0, 1), support_required=False),
        ]
    }
    scene = trimesh.Scene()
    add_box(scene, "solar", (-1.5, 0, 1), (1, 1, 0.2))
    add_box(scene, "wind", (1.5, 0, 1), (1, 1, 0.2))
    report = inspect_scene(assembly, scene)
    assert not any(x["code"] == "solar_wind_overlap" for x in report["issues"])


def test_floating_supported_part_is_blocked():
    assembly = {"quality": {"ground_z_m": 0.0}, "parts": [part("tank", "water storage tank", (0, 0, 2))]}
    scene = trimesh.Scene()
    add_box(scene, "tank", (0, 0, 2), (0.8, 0.8, 0.8))
    report = inspect_scene(assembly, scene, support_gap_m=0.02)
    assert any(x["code"] == "floating_part" for x in report["issues"])


def test_diagram_geometry_is_ignored():
    assembly = {"parts": [part("base", "structural base", (0, 0, 0.1), dims=(2, 2, 0.2))]}
    scene = trimesh.Scene()
    add_box(scene, "base", (0, 0, 0.1), (2, 2, 0.2))
    add_box(scene, "diagram__force", (0, 0, 100), (0.001, 0.001, 0.001))
    report = inspect_scene(assembly, scene)
    assert report["counts"]["parts_checked"] == 1
    assert report["ok"]
