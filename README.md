# EIRA Inventor Holographic Lab — Living Engineering Renderer

General invention-to-3D engineering extension. The target is an inspectable, explicit engineering scene rather than a decorative approximation.

Core capabilities:
- evidence/provenance separation: observed, stated, calculated, inferred, assumed, hypothesized, unresolved
- arbitrary mesh, curve, extrude, revolve, sweep, loft, surface, instance/compound geometry
- system/subsystem/component hierarchy, ports, interfaces, relationships and constraints
- explicit 3D diagram overlays for dimensions, flows, force vectors and ports
- deterministic closed-form engineering preflight with equations/units (mass, weight, stress, beam deflection, Euler buckling, electrical power/Joule heating, fluid velocity/Reynolds/Darcy pressure drop, thermal conduction, rotational/kinetic energy)
- moving joints and sampled animation tracks
- living architecture behaviors for time-varying geometry/state
- Blender GLB export with extras, materials, animation, engineering diagram objects and text labels
- terminal job lifecycle; worker failure must end in `failed`, not infinite rendering

Supplied-sketch regression in the isolated build environment produced a detailed Off-World Greenhouse candidate with 341 physical parts, 352 scene geometries including diagram overlays, 3 moving joints, 8 state behaviors, explicit dimensions/flows, and 733 calculated engineering quantities. Deterministic GLB export was 1,252,104 bytes.

Truth boundary: the build environment does not contain the user's Raspberry Pi Blender/Gemma runtime, so only local deterministic compilation/export is claimed here. Real Gemma -> engineering IR -> Blender execution remains a live-Pi validation step.
