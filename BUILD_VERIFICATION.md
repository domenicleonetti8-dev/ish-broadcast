# Build verification — V8 visual sandbox

Branch: `eira-inventor-holographic-lab-v8-visual-sandbox`

Verified by GitHub Actions in the isolated CI environment on 2026-09-01:

- Python package/test compile: PASS
- Unit + integration tests: PASS
- General geometry regression: 300/300 PASS
- Geometry-quality regression: 300/300 PASS
- Arbitrary-vector extrusion regression: PASS
- Parallel-transport sweep regression: PASS
- Loft winding/section alignment regression: PASS
- Arbitrary revolve-axis regression: PASS
- Blender generated-script syntax contract: PASS
- Blender capsule/plane backend parity regression: PASS
- Non-bypassable visual-review threshold regression: PASS
- Diagnostic five-view preview contract: PASS
- HTTP lifecycle regression: PASS
- Dense greenhouse regression specimen: PASS
  - 742 physical parts checked by deterministic geometry QA
  - 757 scene geometries including diagram overlays
  - 0 deterministic QA errors
  - 0 deterministic QA warnings
  - GLB artifact generated in CI: 1,348,964 bytes
  - GLB + compiled IR + geometry-quality report preserved as GitHub Actions artifacts

V8 architectural changes under test:

- Deterministic pre-render geometry gate for floating supported parts, collapsed/non-finite geometry, tiny fragments and solar/wind clearance-envelope conflicts.
- General geometry engine uses arbitrary-vector extrusion, arbitrary-axis revolve, parallel-transport sweep frames and loft section alignment.
- Renderer instance semantics use local source geometry before each instance transform.
- Blender backend implements declared plane/capsule geometry rather than silently substituting another primitive; smooth curved primitives and transparent glazing material handling were strengthened.
- Render pipeline is now a closed loop: source image -> engineering IR -> compile -> deterministic geometry QA -> Blender GLB -> five diagnostic preview renders -> source-vs-render visual critic -> structured IR repair -> retry. Only an accepted attempt is promoted.
- Visual acceptance cannot self-pass below the configured threshold and an error-level visible defect blocks promotion.
- The greenhouse is a regression fixture only; runtime prompting remains general-purpose for arbitrary invention/construction designs.

Important truth boundary:

GitHub CI does not contain the Raspberry Pi's live Ollama/Gemma + Blender runtime. The full live image -> Gemma engineering IR -> Blender render -> preview -> visual critic/repair loop is therefore **not claimed proven on the Pi yet**. The current evidence proves the Python architecture, deterministic geometry/quality logic, generated Blender-script syntax, regression suites, dense reference geometry compilation, and CI artifact production. Live Pi acceptance is a separate gate and must be run before V8 replaces the installed extension.
