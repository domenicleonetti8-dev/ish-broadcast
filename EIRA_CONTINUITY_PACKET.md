# EIRA CONTINUITY PACKET

Status: CANONICAL CONTINUITY ANCHOR  
Owner: Dom  
Repository: `domenicleonetti8-dev/ish-broadcast`  
EIRA LIVE root: `/media/domenicleonetti/easystore/EIRA/LIVE`

## READ THIS FIRST

Read this packet first. Then verify current LIVE evidence through the working GitHub ↔ Pi ↔ EIRA transport and the canonical LIVE qualification lane. This packet preserves intent and continuity; fresh evidence decides current state.

Glass House is the first passive observation path: read `GLASS_HOUSE_PROTOCOL.md`, then `eira2_transport_bus/from_superprobe/glass/heartbeat.json` and `eira2_transport_bus/from_superprobe/glass/latest.json`. Glass is observation only; it never grants mutation authority.

## VISION AND NON-NEGOTIABLES

Eira remains one cohesive software organism: one identity, one outward voice, one canonical cognitive system, with existing brain regions, extensions, evidence systems, research wings, observatory, archive/library, tools, watcher, builder, sensory systems, registries, neural paths, and delivery systems connected as discoverable parts of one organism.

Preserve EIRA LIVE to the greatest practical extent. Do not water down, bypass, shrink, redirect, simplify, or replace working systems based on assumptions. Preserve authored identity: “I am Eira.” Maintain one outward voice and no competing intelligence authority. Models/Ollama may provide candidate reasoning but are not identity, provenance, tool-use, architecture, or final authority. Do not touch library/archive contents merely to satisfy package checks. Inspect first; back up; validate; write atomically; verify hashes; roll back on failure. Never claim success without returned evidence. Prefer one path, one flow, one canonical road. Repair the canonical owner/path rather than creating parallel or competing subsystems. If an area is healthy after verification, stop touching it.

Storage/device integrity outranks deployment. If LIVE returns `Errno 5` or kernel block I/O errors on `/dev/sda1`, abort LIVE mutation and autonomous engineering until storage is proven stable. Do not run filesystem repair from inference alone; verify filesystem type, device identity, and mount state first. Dom is the approval authority for assistant-authored engineering mutations. Work one Python script at a time. UNKNOWN remains UNKNOWN. Glass is a window, not a door.

## CURRENT CANONICAL BUILD LANE

Canonical build lane remains **EIRA Orin Build Probe V3.1 resilient isolation**.

- Canonical path: `tools/eira2_orin_build_probe.py`
- Canonical LIVE SHA256: `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- Last verified PASS receipt commit: `1bb56a6ee3c801c1d6358958ad900509520f6afc`
- Receipt id: `restore_v31_default_current_master_20260909_2033`
- Receipt reported `before_sha256 == after_sha256 == 984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- `compile_ok: true`

Preserve capabilities: `read`, `list`, `search`, `compile`, `health`, `deploy`, `upgrade_probe`, `isolate_legacy_v1`.

Legacy V1 is non-canonical. Stale V3.2/V3.3 activation packets remain quarantined and must not compete with V3.1.

### Newest transport/build receipt inspected

Newest verified deployment return commit inspected: `1e54e405f08a34acf771b12bd9adbed8ad6e7400` (2026-09-09T11:15:29Z).

Receipt path: `eira2_transport_bus/from_superprobe/deployments/library_federation_wing_v1_deploy_20260909__1788952375-58fff938c50e__receipt.json`

This receipt is **not a successful canonical build checkpoint**:

- `status: DEPLOYMENT_FAILED`
- `builder_deployed: true`
- `payload_sha256: 2ee01f65257c35f19bc701983a75f75376246b1bcac1681d7722adf699d4ce38`
- `before_sha256: null`
- `package_identity_ok: false`
- `superprobe_ok: false`
- `live_http_roundtrip_verified: false`
- `rollback_performed: false`
- target: `eira2/evidence/universe_library_federation.py`
- lane receipt: `/media/domenicleonetti/easystore/EIRA/LIVE/eira_probe/blueprint_receipts/library_federation_wing_v1_deploy_20260909-1788952375-58fff938c50e.lane_v4.json`
- transport blueprint SHA256: `58fff938c50e5b06c346dc40819c284ca9d147744e313f666330c2018ece4e9d`

This failed receipt is newer than the prior packet’s “no newer terminal receipt” wording, but it does **not** supersede V3.1 as the canonical build lane and does not prove a successful LIVE deployment.

## DOM ARCHITECTURAL DECISIONS AND SUPSERSESSION RECORD

- OpenCode and Aider may inspect/work broadly only in isolated disposable workspaces; candidates must not directly mutate LIVE.
- OpenCode is investigator/architect/reviewer; Aider is implementation/code-surgery worker; collaboration must be orchestrated, not uncontrolled simultaneous writes.
- Truth/evidence, Watcher authorization, canonical Builder deployment, rollback, and Dom’s owner authority remain protected gates.
- “You investigate; I build” remains directional shorthand only; Dom is explicit approval authority.
- Work one Python script at a time.
- Baseline review gate is 3,000 structured checks per Python script.
- Explicit 10,000-review instruction supersedes that baseline for the V6 HOME-mapping candidate and Glass V2.2 repair only. It does not generalize without a newer explicit Dom instruction.
- Glass House supersedes the prior habit of sending an active probe first: start with passive Glass/GitHub evidence, using an active probe only when the fact is outside Glass coverage or Glass itself requires diagnosis. This does not supersede Build Probe V3.1.
- No newer explicit Dom architectural decision was verified during this refresh; all prior non-negotiables remain in force.

## NEWEST VERIFIED LIVE ENGINEERING QUALIFICATION

Current LIVE engineering worker under qualification identifies as:
`eira2_engineering_worker_opencode_aider_v6_canonical_hardened`

Last verified read-only qualification evidence remains:

- snapshot: PASS
- canonical package file_count: `359`
- manifest_sha256: `1cf5ddd02555ad3b32362d097601de2763eb04a6e3f5a51ef2c6d3d2178508f1`
- source_fingerprint: `19bd5851f6b95a8572512d3aea317ff00783126642f1e687fcbafd69c3dbf9b4`
- OpenCode inspect: START then FAIL
- returncode: `1`
- elapsed: `3.882s`
- stderr: `Unexpected server error. Check server logs for details.` ref `err_11254f49`
- mutations detected: `[]`
- `live_mutated: false`
- model digest: `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`

Direct reproduction of the same synthetic HOME contract failed immediately with `EACCES: permission denied, mkdir '/home/eira'`. The leading V6 blocker remains the sandbox HOME/config mapping contract; runtime success is unproven.

Reviewed candidate (not LIVE-deployed): `EIRA2_V6_HOME_MAPPING_REPAIR_V2.py` SHA256 `799de9e6bf2e19c4e3d4788e901eb95be421a131af5ba01b30b6aae5b12fa0bb`, with 10,000 structured assertions and 0 failures.

## COMPLETED VERIFIED REPAIRS

1. `tools/eira2_superprobe_engine.py` manifest row repaired to LIVE SHA256 `8476f89f5f6aa7df4eb54d744ac6a204758e4e28e785be6e5ca0f0833f494227`, size `20138`. The next V6 snapshot stage passed.
2. Glass V2.2 verified LIVE at `extensions/glass_viewport_ai/plugin.py`, SHA256 `5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`, with controlled deployment result `BUILDER=True` and exact matching `AFTER` hash.
3. Glass produced a populated viewport snapshot before publication stopped: `eira2_transport_bus/from_superprobe/glass/latest.json`, Git blob `117cc828915ed1e94400125dbfb3f234cb08667c`, repository size `81,349,661` bytes, newest observed viewport commit `b554a15ec6a5bc21b39166444bb204cbe2224445` authored 2026-09-10T11:10:22Z.

Do not treat candidate review as LIVE deployment. Do not treat a failed receipt as a completed repair.

## CURRENT GLASS HOUSE / LIVE OBSERVATION STATUS

Protocol file: `GLASS_HOUSE_PROTOCOL.md`

Observation road: `EIRA LIVE -> passive read-only Glass portals -> GitHub viewport -> Orin`  
Mutation road: `approved engineering -> Watcher -> Builder -> LIVE -> receipts/telemetry -> Glass/GitHub`

Last verified Glass heartbeat:

- path: `eira2_transport_bus/from_superprobe/glass/heartbeat.json`
- Git blob: `f864fc4252d59e8c37a0671346f76be142801c31`
- payload: `active=true`, version `2.2.0`, canonical LIVE root, PID `653044`, cycle `113`, phase `deepening`, portal_count `33585`, blind_spot_count `10126`, `scan_complete=false`
- `updated_unix=1789038607.9967208` = 2026-09-10T11:10:07.996721Z / 07:10:07 EDT

Current Glass liveness is **UNKNOWN** because the heartbeat is stale relative to the current refresh date. The old `active=true` field is historical payload, not proof that PID `653044` is alive now. The populated `latest.json` is real but stale; it proves snapshot generation, not current publisher liveness or scan completion.

## CURRENT TRANSPORT / STORAGE STATUS

Transport hardening remains unresolved at the canonical infrastructure level. The Glass transaction succeeded after preserving `before_sha256` through Builder planning and using an isolated Watcher inbox/stage, but that success does not prove every master/default/LIVE transport copy contains the final race-safe repair.

Prior `/dev/sda1` EIO and `Errno 5` evidence remains historically valid as a storage-integrity warning. Fresh V6 snapshot PASS means it was not the currently observed qualification gate; if it recurs, storage immediately outranks software repair.

Universe Library remains separate from package/manifest and should not be rolled back blindly. Historical malformed V3 checkout was superseded by V4 qualification that passed 50/50 tests. A separate software defect remains evidenced: `OperationalError: table ingest_receipts has 7 columns but 6 values were supplied`.

## LATEST LEGACY TELEMETRY CHECKPOINT

- path: `eira2_transport_bus/from_superprobe/telemetry/orin_eira_live_latest.json`
- Git blob: `578c8bf7e13582809a91db387eca9b4c32f8396f`
- bridge PID recorded: `100080`
- control ref: `master`
- Builder receipt SHA256: `918b8b4d4486ceb839f3b841c0da846e4001d471dbfc528ab712a5a4c0c81fa2`
- Builder transaction: `1788943753-105311`
- reports `ok: true`, rollback false, applying `extensions/repair_watcher_ai/plugin.py`

Historical telemetry is not proof of current process liveness.

## CONTINUITY UPDATE RULE

When a meaningful verified state changes, update this packet with:

- current canonical build lane/version
- relevant verified hashes/paths
- completed repair
- unresolved blocker
- next exact step
- any newer Dom architectural decision, with explicit supersession if applicable

Do not modify EIRA LIVE, library contents, cognition, or build infrastructure as part of a continuity refresh.

## CURRENT NEXT EXACT STEP

1. Keep canonical Build Probe V3.1 unchanged.
2. Treat Glass publication freshness as the immediate continuity blocker. The populated ~81 MB viewport proves snapshot generation worked; now determine why the heartbeat and viewport publisher stopped after 07:10 EDT.
3. Use the narrowest existing canonical diagnostic path to establish whether PID `653044` / the Glass daemon is actually alive. Do not infer liveness from stale heartbeat and do not infer EIRA LIVE failure from a stale Glass window.
4. Do not start a second Glass daemon or broadly kill EIRA/transport processes. If alive, inspect publisher/log/commit failure boundary; if dead, identify the terminal error before any restart.
5. Restore fresh Glass publication and require advancing heartbeat/viewport commit evidence plus explicit scan/accounting state.
6. Separately synchronize/review the complete `before_sha256` + isolated Watcher-stage race fix into the canonical transport lane before declaring transport infrastructure repaired.
7. After the observation lane is stable, return to the reviewed V6 HOME/config candidate only after Dom-authorized deployment and run the exact read-only qualification again.
8. If storage EIO reappears, abort software mutation/qualification and return storage integrity to primary blocker status.

No broad library rollback, speculative filesystem repair, speculative architecture rewrite, duplicate subsystem, or fake pass.

---
This packet is the continuity anchor. Read it first; verify LIVE second; build third.
