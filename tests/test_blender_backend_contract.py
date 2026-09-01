import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eira_inventor_holographic_lab.blender_backend import generate_blender_script


def specimen(primitive, dimensions):
    return {
        "assembly_id": "backend_contract",
        "name": "backend contract",
        "parts": [{
            "part_id": "p",
            "name": primitive,
            "geometry": {"kind": "primitive", "primitive": primitive, "dimensions": dimensions},
            "transform": {"location": [0,0,0], "rotation_deg": [0,0,0], "scale": [1,1,1]},
            "source": {"provenance": "assumed", "confidence": 1.0},
            "visual": {"color": "#88aacc", "alpha": 0.5, "metallic": 0.2, "roughness": 0.3},
        }],
        "joints": [],
        "motion_tracks": {},
        "living_simulation": {"duration_s": 1, "frames": []},
        "diagram_layer": {"items": []},
    }


def test_generated_blender_script_is_python_syntax_valid():
    script = generate_blender_script(specimen("capsule", {"radius": .2, "height": 1, "segments": 32}), "/tmp/x.glb")
    compile(script, "generated_blender.py", "exec")


def test_capsule_is_not_sphere_fallback():
    script = generate_blender_script(specimen("capsule", {"radius": .2, "height": 1, "segments": 32}), "/tmp/x.glb")
    assert "def capsule_obj" in script
    assert "primitive_cylinder_add" in script
    assert "q=='capsule': o=capsule_obj" in script


def test_plane_and_glazing_material_are_supported():
    script = generate_blender_script(specimen("plane", {"x": 2, "y": 3, "z": .01}), "/tmp/x.glb")
    assert "q=='plane'" in script
    assert "Transmission Weight" in script
    compile(script, "generated_blender.py", "exec")
