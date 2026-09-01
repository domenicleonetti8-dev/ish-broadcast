import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eira_inventor_holographic_lab.compiler import compile_assembly
from eira_inventor_holographic_lab.quality import inspect_scene
from tests.fixtures.reference_greenhouse_v8 import build_reference_greenhouse

ROOT = Path(__file__).resolve().parents[1]

assembly = build_reference_greenhouse()
compiled, scene = compile_assembly(assembly, duration_s=8.0, fps=24)
quality = inspect_scene(compiled, scene, support_gap_m=0.08, forbidden_overlap_m3=1e-5)

# The fixture is deliberately dense and should still satisfy the deterministic quality gate.
assert quality["ok"], quality
assert len(assembly["parts"]) >= 300
assert len(assembly.get("joints", [])) >= 4
assert any((p.get("visual") or {}).get("clearance_group") == "solar" for p in assembly["parts"])
assert any((p.get("visual") or {}).get("clearance_group") == "wind" for p in assembly["parts"])
assert sum(1 for p in assembly["parts"] if p.get("system") == "living architecture") >= 120
assert sum(1 for p in assembly["parts"] if p.get("subsystem") == "service bay") >= 10

artifacts = ROOT / "artifacts"
artifacts.mkdir(exist_ok=True)
(artifacts / "off_world_greenhouse_v8_ir.json").write_text(json.dumps(compiled, indent=2))
(artifacts / "off_world_greenhouse_v8_quality.json").write_text(json.dumps(quality, indent=2))
scene.export(artifacts / "off_world_greenhouse_v8_reference.glb")

print(
    "REFERENCE GREENHOUSE V8 PASS",
    len(assembly["parts"]), "parts",
    len(assembly.get("joints", [])), "moving joints",
    quality["counts"],
)
