# Build verification

Verified in the isolated build environment on 2026-08-31:

- Python compile: PASS
- General geometry regression: 300/300 PASS
- Malformed geometry rejection: PASS
- HTTP lifecycle regression: PASS
- Supplied Off-World Greenhouse reference compile: PASS
- Detailed living reference reconstruction: PASS
  - 341 physical parts
  - 352 scene geometries including diagram overlays
  - 3 moving joints
  - 8 living/state behaviors
  - 3 explicit engineering dimensions
  - 2 system flow paths
  - 733 closed-form calculated quantities
  - deterministic GLB export: 1,252,104 bytes
- Job lifecycle terminates in completed/failed rather than indefinite rendering.

Important truth boundary: Blender and Gemma/Ollama are not present in this build container. The actual Raspberry Pi Gemma -> Blender live path is therefore NOT claimed proven until it is run on the Pi.
