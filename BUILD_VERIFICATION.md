# Build verification

Local isolated regression environment on 2026-08-31:

- Python compile: PASS
- General geometry regression: 300/300 PASS
- Malformed geometry rejection: PASS
- Supplied Off-World Greenhouse reference reconstruction: PASS
- Reference reconstruction produced 34 engineering parts, an arched freeform shell, seven structural ribs, crop beds, plant geometry, a hypothesized life-support module, and a continuous moving fan joint.
- GLB export through deterministic non-Blender regression backend: PASS
- HTTP create/upload/render/poll/complete lifecycle in isolated test mode: PASS
- Duplicate-title detection and explicit invention deletion are implemented.
- Installer performs backup/replacement, preserves archive, compiles installed Python, hash-protects main.py, and rolls back if main.py changes.

Truth boundary: Blender and Gemma/Ollama are not installed in this build environment, so the real Raspberry Pi Gemma -> Blender end-to-end path is NOT claimed proven here. The production pipeline includes explicit terminal failure states and must still be validated on the Pi.
