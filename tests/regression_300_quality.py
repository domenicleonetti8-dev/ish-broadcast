import random
import sys
from pathlib import Path

import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eira_inventor_holographic_lab.quality import inspect_scene


def part(pid, role, support_required, clearance_group=""):
    return {
        "part_id": pid,
        "name": pid,
        "system": role,
        "geometry": {"kind": "primitive", "primitive": "box", "dimensions": {"x": 1, "y": 1, "z": 1}},
        "transform": {"location": [0,0,0], "rotation_deg": [0,0,0], "scale": [1,1,1]},
        "source": {"provenance": "inferred", "confidence": 0.8},
        "visual": {"role": role, "support_required": support_required, "clearance_group": clearance_group},
    }


def add_box(scene, pid, center, extents):
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(center)
    scene.add_geometry(m, geom_name=pid, node_name=pid)


def make_case(seed):
    rng = random.Random(seed)
    scenario = seed % 4
    assembly = {"quality": {"ground_z_m": 0.0}, "parts": []}
    scene = trimesh.Scene()

    # Every case has a grounded structural base.
    assembly["parts"].append(part("base", "structural base", True))
    add_box(scene, "base", (0,0,0.1), (8,5,0.2))

    if scenario == 0:  # valid separated roof systems
        assembly["parts"] += [
            part("solar", "solar array", False, "solar"),
            part("wind", "wind turbine duct", False, "wind"),
        ]
        add_box(scene, "solar", (-1.7, 0.8, 3.0), (2.0, 0.8, 0.08))
        add_box(scene, "wind", (1.7, -0.4, 3.0), (2.0, 0.7, 0.4))
        expect_ok = True
    elif scenario == 1:  # invalid roof collision
        assembly["parts"] += [
            part("solar", "solar array", False, "solar"),
            part("wind", "wind turbine duct", False, "wind"),
        ]
        jitter = rng.uniform(-0.1, 0.1)
        add_box(scene, "solar", (0, 0, 3.0), (2.0, 1.0, 0.15))
        add_box(scene, "wind", (jitter, 0, 3.0), (2.0, 0.8, 0.5))
        expect_ok = False
    elif scenario == 2:  # invalid floating equipment
        assembly["parts"].append(part("tank", "water storage tank", True))
        add_box(scene, "tank", (0, 0, 2.0 + rng.uniform(0.2, 1.0)), (0.8,0.8,0.8))
        expect_ok = False
    else:  # valid supported equipment on base
        assembly["parts"].append(part("tank", "water storage tank", True))
        add_box(scene, "tank", (0, 0, 0.6), (0.8,0.8,1.0))
        expect_ok = True

    return assembly, scene, expect_ok


passed = 0
for i in range(300):
    assembly, scene, expect_ok = make_case(i)
    report = inspect_scene(assembly, scene, support_gap_m=0.06)
    if report["ok"] != expect_ok:
        raise AssertionError(f"quality case {i} expected ok={expect_ok} got {report}")
    passed += 1

print(f"REGRESSION_300_QUALITY PASS {passed}/300")
