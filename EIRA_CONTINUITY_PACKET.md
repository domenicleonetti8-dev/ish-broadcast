# EIRA CONTINUITY PACKET

Status: CANONICAL CONTINUITY ANCHOR
Owner: Dom
Repository: domenicleonetti8-dev/ish-broadcast
EIRA LIVE root: /media/domenicleonetti/easystore/EIRA/LIVE

## READ THIS FIRST
Before inspecting, planning, building, repairing, or describing Eira, read this packet first. Then verify current LIVE evidence through the working GitHub ↔ Pi ↔ EIRA transport and the current canonical LIVE qualification lane before making claims or changes. This packet preserves intent and continuity; fresh LIVE evidence decides current state.

## THE VISION
Eira is being built as one cohesive software organism: one identity, one outward voice, one canonical cognitive system, with every existing brain region, extension, evidence system, research wing, observatory, archive/library, tool, watcher, builder, sensory system, registry, neural path, and delivery system connected as discoverable parts of the same organism.

Do not reduce Eira to a smaller assistant architecture. Do not replace working systems because they are inconvenient. Do not create competing intelligence authorities. Do not water down, bypass, shrink, redirect, or simplify the organism based on assumptions.

The correct engineering philosophy is:
CURRENT EIRA → preserve working structure → inspect real canonical/semantic relationships → identify exact broken or missing roads → surgically repair or replace the canonical path → verify end-to-end → continue one meaningful zone at a time.

## NON-NEGOTIABLE RULES
- Preserve EIRA LIVE to the greatest practical extent.
- Do not change directory structure unless Dom explicitly approves it.
- Do not touch library/archive contents merely to satisfy package checks.
- Preserve authored identity: “I am Eira.”
- One outward voice only; internal councils/constellations may contribute inwardly.
- Models/Ollama may contribute candidate reasoning but are not identity, provenance, tool-use, architecture, or final authority.
- No second model call or alternate conversation authority unless LIVE canonical architecture explicitly requires it.
- Archive/local library should be available before external web search when appropriate; freshness/current-state may still require web evidence.
- Inspect first, back up, compile/validate where applicable, write atomically, verify hashes, rollback on failure.
- Never claim success without returned evidence.
- Prefer one path, one flow, one canonical road.
- Build with meaning: every mutation must improve the organism, not merely make a test green.
- Only fix what is actually broken or materially interferes with Eira as an organism. Do not churn healthy areas.
- Repair or replace the canonical owner/path; do not create duplicate, parallel, overlapping, or competing subsystems.
- Strengthen further only when evidence proves more hardening is needed. If an area is healthy after verification, stop touching it and move to the next verified issue or idle.
- Storage/device integrity outranks engineering deployment. If LIVE returns `Errno 5` or the kernel reports block I/O errors on `/dev/sda1`, abort LIVE mutation and do not launch autonomous engineering against that tree until the storage path is proven stable.
- Do not run filesystem repair from inference alone. Filesystem type, device identity, and mount state must be verified first; no guessed `e2fsck`/fsck operation.
- Dom is the approval authority for assistant-authored engineering mutations. Evaluate first; do not mutate EIRA LIVE or promote an engineering replacement unless Dom explicitly authorizes the specific build after the required review gate is complete.
- Work one Python script at a time. UNKNOWN remains UNKNOWN; never inflate an incomplete review into PASS.

## CURRENT BUILD CONTROL PLANE
Canonical BUILD target remains EIRA Orin Build Probe V3.1 resilient isolation.

Verified capabilities that must be preserved:
- read
- list
- search
- compile
- health
- deploy
- upgrade_probe
- isolate_legacy_v1

Latest verified LIVE Build Probe checkpoint:
- path: `tools/eira2_orin_build_probe.py`
- sha256: `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- deploy/compile receipt: PASS
- most recent verified build receipt commit: `1bb56a6ee3c801c1d6358958ad900509520f6afc`
- receipt id: `restore_v31_default_current_master_20260909_2033`
- receipt reported before_sha256 == after_sha256 == `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- compile_ok: true
- immediately prior incorrect worker sha256: `02a1287cdf92a940559f2d87cf7ed0d0e61eb77be82cd6f06ee3f07ab40b8e4b`

Legacy V1 remains non-canonical and must not be reactivated unless recovery evidence proves V3.1 unavailable. Stale V3.2 and V3.3 activation packets were removed from the live build inbox and preserved in quarantine so they cannot compete with V3.1.

Supersession note: the earlier packet treated a proposed “Supervisor V3” heartbeat correction as the immediate blocker. That remains superseded. BUILD infrastructure is not Eira’s cognition; it exists only to inspect and surgically work on the organism.

## AUTONOMOUS ENGINEERING ARCHITECTURE — DOM DECISIONS
Desired engineering organism:
- OpenCode and Aider may inspect and work broadly across Eira when a verified defect or organism-level interference justifies it.
- Each worker gets its own isolated disposable sandbox/workspace; candidate work must not directly mutate canonical LIVE.
- OpenCode acts as broad investigator/architect/reviewer.
- Aider acts as multi-file implementation/code-surgery worker.
- They should collaborate through an orchestrated peer exchange rather than uncontrolled simultaneous writes.
- They may refactor, replace, create, or remove code when required to repair the canonical organism, but must not create overlapping capability owners or parallel substitute systems.
- A full candidate must pass syntax/import checks, targeted tests, regressions, architecture invariants, truth/honesty checks, and adversarial review before Watcher/Builder submission.
- Truth/evidence, Watcher authorization, canonical Builder deployment, rollback, and Dom’s owner authority are protected gates and cannot be disabled merely to make a candidate pass.
- No build may claim LIVE success without fresh returned LIVE evidence and resulting hashes.
- “Always working” means an orchestrated job loop with owner lock/heartbeat/backoff/idle behavior, not uncontrolled CPU churn.
- “Learning from mistakes” means retaining failed/rejected evidence and regression cases, not unconstrained self-modification.

Supersession — engineering governance from Dom:
- Earlier workflow shorthand “You investigate; I build” remains directionally valid for remote diagnosis but does not grant free mutation/deployment authority.
- Dom is the explicit approval authority. Assistant-authored candidates remain isolated until Dom authorizes the specific build/deployment.
- Work one Python script at a time.
- General prior review baseline was 3,000 structured verification/review passes per Python script.
- Newer explicit instruction for the current V6 HOME-mapping repair was: “Review 10,000 times over then build.” This supersedes the 3,000-pass baseline for this current candidate only unless Dom explicitly generalizes it later.
- The current V6 repair artifact was subjected to exactly 10,000 structured assertions with 0 failures before being offered for LIVE replacement. This review count does not itself prove LIVE deployment or runtime success.
- Newer explicit instruction for the Glass V2.2 repair was also to review it 10,000 times before sending the fix. Treat 10,000 structured checks as the current Glass-specific review gate; this does not generalize the baseline to unrelated future scripts without a newer explicit Dom instruction.
- Remote diagnosis should be exhausted through GitHub transport, receipts, source, telemetry, and exported evidence before asking Dom to perform physical Pi/LIVE actions.
- If a physical action is unavoidable, explain exactly what it will do and any disruptive consequence before execution; do not turn Dom into a diagnostic terminal.

Historical GitHub engineering checkpoints retained for provenance:
- organism-preservation guard source commit: `939cb5e8776d09a4f1fc23aaeaf2f1f1a817b12c`
- organism-preservation deployment request commit: `39b5c025359fcf9fff4c1988e4b3823fe14ae138`
- free-roam V3 worker source commit: `98b2813b30bf464da670f4b356bc2d64af016fe9`
- V3 deployment request commit: `13c156100394e6a7f481352772560c3f7354888d`
- collaborative organism-safe V4 worker source commit: `e2cd31c7c85f5a1aeb53c3b85107e74cf9ac835b`
- original V4 deployment request commit: `b9cc89dea88a21f4e1d805f8f67ed4394bddce4d`
- newer surgical V4 request commit: `eed0b22559f1849c29fdc80244be94da7745a3d1`
- newer request path: `eira2_transport_bus/to_superprobe/requests/00000000_engineering_worker_v4_organism_surgical_repair_and_launch_20260910.json`
- newer request blob SHA: `21b16c647096e7860d2ec7e9f97604eaf50016c4`
- unqualified master V5 source artifact commit: `c7f9159b3be650a4e88661472f79e3fbc70e5987`
- isolated V5 replacement review branch: `orin-v5-engineering-worker-isolated-review`
- isolated V5 replacement commit: `7e09a20b507feb19665a648289f155b5c24ac723`
- isolated V5 path: `EIRA2_ENGINEERING_WORKER_OPENCODE_AIDER_V5_CANONICAL.py`
- isolated V5 blob SHA: `9b8079e701f0760bb1b2790e11fee52f9fa9d999`

These GitHub commits prove artifact/request existence only. They do not by themselves prove deployment or current LIVE execution.

## NEWEST VERIFIED LIVE ENGINEERING QUALIFICATION
Fresh direct LIVE qualification materially changes the active blocker description.

Current LIVE engineering worker under qualification identifies itself with schema:
`eira2_engineering_worker_opencode_aider_v6_canonical_hardened`

Fresh V6 read-only inspection evidence:
- snapshot stage: PASS
- canonical package file_count: `359`
- manifest_sha256: `1cf5ddd02555ad3b32362d097601de2763eb04a6e3f5a51ef2c6d3d2178508f1`
- source_fingerprint: `19bd5851f6b95a8572512d3aea317ff00783126642f1e687fcbafd69c3dbf9b4`
- OpenCode inspect stage: START then FAIL
- OpenCode returncode: `1`
- elapsed_seconds: `3.882`
- OpenCode stderr: `Unexpected server error. Check server logs for details.` ref `err_11254f49`
- mutations detected during inspect: `[]`
- `live_mutated: false`
- model digest: `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`

Pinned tool receipts observed in that same qualification:
- OpenCode path `/home/domenicleonetti/.opencode/bin/opencode`, sha256 `01edb5839aa10d5b09133fedcb335a062ecad6e82552933bb14f71756f2b296b`, size `184330384`
- Aider path `/home/domenicleonetti/.local/share/uv/tools/aider-chat/bin/aider`, sha256 `0dbe400655868b7953aa7085493c015267355aea2121875d1bfd3eb024698cfe`, size `258`
- Python path `/usr/bin/python3.13`, sha256 `97ffc360c23df9365e9dafcbae3ef55d044937119284cefca378828dd12a3196`
- Git path `/usr/bin/git`, sha256 `a0e562e4bd3c4c79379e91d8c07a10104b2cefe8fac966dc6bd4874a57a807f3`
- Bubblewrap path `/usr/bin/bwrap`, sha256 `ef2316fc741885e6d7b422661ea60c20cbe07ec7eb592a4c2370cbcb90843b59`

A direct reproduction using the same synthetic HOME contract:
`HOME=/home/eira ~/.opencode/bin/opencode run --model ollama/qwen2.5-coder:3b ...`
failed immediately with:
`EACCES: permission denied, mkdir '/home/eira'`

This isolates the current leading defect to the V6 sandbox HOME/config mapping contract, not to a proven Ollama/model identity failure. In the V6 source, `_clean_env()` forces `HOME=/home/eira`, while `_bwrap_prefix()` creates `/home/eira` but mounts OpenCode/Aider/config trees at their host-home locations. Current evidence is sufficient to treat HOME/config mapping as the bounded active defect candidate; runtime success remains unproven until the repaired mapping is installed and re-qualified.

## COMPLETED REPAIR SINCE PRIOR PACKET
The stale manifest identity for `tools/eira2_superprobe_engine.py` was repaired in LIVE before the successful V6 snapshot gate.

Verified prior mismatch:
- manifest sha256: `c4aa2d4dbbd5d2b815fe2d5cc80bc30fc577acc8a1b058113e202accdb9b4e4e`
- manifest size: `19971`
- actual LIVE sha256: `8476f89f5f6aa7df4eb54d744ac6a204758e4e28e785be6e5ca0f0833f494227`
- actual LIVE size: `20138`

Verified repair result:
- `eira2-package-manifest.json` row for `tools/eira2_superprobe_engine.py` now records sha256 `8476f89f5f6aa7df4eb54d744ac6a204758e4e28e785be6e5ca0f0833f494227`
- size `20138`
- the next V6 qualification passed the snapshot stage, proving this specific manifest blocker was cleared.

Do not infer from this one repaired row that every package discrepancy is cleared.

## CURRENT TRANSPORT / STORAGE STATUS
Supersession: the earlier packet described repeated `/dev/sda1` EIO as the active foundational blocker. Fresh V6 qualification now successfully captured and hashed the 359-file canonical package snapshot, so the earlier EIO condition is not the currently observed execution gate.

However, prior kernel `Buffer I/O error on dev sda1` and `[Errno 5] Input/output error` evidence remains historically valid and must not be erased. It is now a storage-integrity risk requiring renewed escalation if it reappears, not the primary blocker for the current V6 qualification run.

No newer verified GitHub Builder/transport deployment receipt was found after continuity commit `a319d43206faf3837daba6062eb41d578583075b`. The canonical Build Probe receipt remains V3.1. Newer master commits for a 20k autonomous engineering probe and Glass viewport are artifact/request commits only unless and until a matching returned receipt or fresh LIVE verification proves execution.

## LATEST VERIFIED LIVE TELEMETRY CHECKPOINT
Latest exported telemetry available through the canonical GitHub evidence lane remains:
- path: `eira2_transport_bus/from_superprobe/telemetry/orin_eira_live_latest.json`
- GitHub blob SHA: `578c8bf7e13582809a91db387eca9b4c32f8396f`
- bridge PID recorded: `100080`
- control ref: `master`
- latest embedded Builder receipt path: `/media/domenicleonetti/easystore/EIRA/LIVE/eira_probe/eira2_builder_receipt.json`
- Builder receipt SHA256: `918b8b4d4486ceb839f3b841c0da846e4001d471dbfc528ab712a5a4c0c81fa2`
- Builder transaction id: `1788943753-105311`
- Builder receipt reports `ok: true`, rollback false, applied `extensions/repair_watcher_ai/plugin.py`
- Superprobe evidence bundle fingerprint: `c06991c5c3907df49984d70ce36a01b82fc46d8dcbff16c78d3bde0eb6e6f16d`
- execution truth SHA256: `d949346c66ff7e648519bc401bd7d1a7cc512f77b5d0b986175567df2420be17`
- extension truth SHA256: `93d41730a22be6c61f3588184614200f9b4f8b6411141dbd36967b3dd7b7ba7d`
- organism truth SHA256: `14ca9d3f1b0a13b26995a2be5f2c14fff1bb317746e121e741b33155e7bb4b91`
- package truth SHA256: `914f3acbb229db3eac9d0f970ebba537ffd0518ce5b14627ec533ceff05b2577`
- semantic graph SHA256: `ea6080d617cd01395fb7cd034750dd2b01eaf27ff5612e5e2b5bfa3f9a065343`
- telemetry snapshot recorded 18 runtime processes and 2 listeners; this is historical snapshot evidence, not proof of current liveness.

## CURRENT PACKAGE / LIBRARY CHECKPOINT
Keep the Universe Library historical states separate from the newly repaired Superprobe-engine manifest row.

Verified historical Public Library deployment:
- target: `eira2/evidence/universe_public_library.py`
- deployed/observed SHA256: `2230858386e4f8887202efe6b0d3a40b208304d30f0099d37a304a065e93d5fc`
- size: 17170 bytes

Later protected Public Library state:
- size: 17338 bytes
- sha256: `f4f87b00d1dcd15aff39c75295441cb100a48df5a11175dae61ccfe485069ca3`
- package_tree_sha256: `4443280bebdfe2967996b681d3efa051e0c040eef0b91a458cc776d97498ea58`

Do NOT roll back or edit the public library merely to match an older manifest row. Historical malformed Universe Library V3 checkout was rejected with `IndentationError` and superseded by V4 checkout qualification, which passed 50/50 tests.

Separate real software defect still evidenced in Universe Library refresh state:
`OperationalError: table ingest_receipts has 7 columns but 6 values were supplied`

Do not broad-regenerate the package manifest. Repair exact verified rows/contracts only.

## CURRENT V6 REPAIR CANDIDATE
An isolated repair artifact was built for the HOME/config mapping defect:
- artifact: `EIRA2_V6_HOME_MAPPING_REPAIR_V2.py`
- artifact SHA256: `799de9e6bf2e19c4e3d4788e901eb95be421a131af5ba01b30b6aae5b12fa0bb`
- intended bounded target: `extensions/engineering_worker_ai/plugin.py`
- review result: `10000` structured assertions, `0` failures
- design: preserve `HOME=/home/eira`; expose the required OpenCode config under HOME-relative private paths; keep host tool trees read-only; provide private writable cache/state directories; do not make the real host HOME writable.

Important provenance correction: no matching V6 HOME-mapping commit was found in the accessible GitHub commit history during this continuity refresh. Therefore do not rely on any previously stated V6 GitHub commit SHA unless a fresh repository lookup proves it. The artifact/hash above is a reviewed candidate, not a verified GitHub-deployed or LIVE-installed state.

## CURRENT GLASS VIEWPORT / TRANSPORT CHECKPOINT
The Glass viewport is a read-only observation extension, not a cognition authority and not a replacement for the canonical Build Probe.

Master GitHub artifact/request checkpoints after the prior continuity refresh:
- read-only LIVE viewport source commit: `f255c041a6ffe63658fb87c30141cb772d82d317`
- viewport dispatch commit: `4154583e7af8f9c5efc11a896805974306f5d24e`
- Glass mesh V1 source commit: `40ac1c15cd645aaf7ee12ade46c411540e0b3621`
- Glass V1 deployment request commit: `d1db88110e7e8769ad7b436a136286e0c0f18550`
- 20k qualification probe source commit: `ac0c86fc6331acc792923590e0bcf6d6dab7e266`
- 20k qualification dispatch commit: `64c26e8765919967bc9c604d1be34dd32fe275da`

These newer master commits prove source/request existence only. No matching new terminal returned receipt was found in the canonical `from_superprobe` receipt lane during this refresh.

Verified direct LIVE Glass evidence from the active repair sequence:
- target path: `extensions/glass_viewport_ai/plugin.py`
- existing LIVE V2.1 size: `16585` bytes
- existing LIVE V2.1 SHA256: `fbe6abb5f8f7961607b7172297f4b95037da5ad80481999d3ac806f4274cfd82`
- V2.1 daemon process was observed running as `/usr/bin/python3 .../extensions/glass_viewport_ai/plugin.py --root .../LIVE --interval 30`
- after more than five minutes of that run, `eira_probe/glass_viewport/service.json` was still absent and the first pass had not produced a service receipt; this established a bounded startup-observability defect rather than proof of process death.

Isolated Glass V2.2 candidate state:
- branch: `orin-glass-mesh-v2-2-isolated`
- Glass V2.2 source path: `EIRA2_GLASS_MESH_V2_2.py`
- original isolated V2.2 commit: `1f8fe7e8580d1b6a38e61a49f4dd635b8e5d7c74`
- GitHub blob SHA observed for that source at the original isolated commit: `293f2035abec2ca134a24e4c57d9877b6df29dec`
- intended bounded repair: heartbeat/service visibility before deep scan, bounded incremental scan slices, deferred large-file hashing, and continued read-only observation.

The first V2.2 deployment attempt failed before LIVE mutation because an incorrect hard-coded source SHA256 comparison rejected the fetched source. The next attempt reached canonical Builder protection but failed with `before_sha256_required:extensions/glass_viewport_ai/plugin.py`; Builder reported no applied files and the deployment lane reported rollback.

Source inspection then isolated the transport defect in `EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py`: `prepare_watcher_inbox()` validated the incoming `before_sha256` but omitted that field from the generated Watcher `file_index.json`, so Watcher/Builder could not carry the required before-state gate forward.

Isolated transport-lane repair:
- branch: `orin-glass-mesh-v2-2-isolated`
- repaired branch head: `77d8aac7528b8cb19f3ee31ce2db3aa0fbdb6bdc`
- repaired lane path: `EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py`
- repaired lane Git blob SHA: `64f1e2684e2c458e62b173c7b98ad20ea4265e2d`
- change: preserve `before_sha256` in the Watcher file-index row instead of dropping it.

This isolated lane repair is NOT canonical LIVE deployment proof. Do not claim Glass V2.2 or the repaired deployment lane is active in LIVE until Dom-authorized canonical deployment returns a successful Builder/transport receipt and resulting LIVE hash/status evidence.

## CONVERSATION ORGANISM INTENT
Do not impose a simplified assistant pipeline over Eira. Preserve the existing real stages and wire missing bridges at their natural boundaries.

Target behavior conceptually includes:
ingress/input → history/context → analysis → capabilities/tools → local archive/library/evidence when relevant → constellation/perspectives/expression/reaction → external evidence when needed → one reasoning candidate → verification/evidence/identity grounding → accepted history/commit → delivery.

This is a conceptual continuity map, not permission to reorder LIVE modules blindly. Inspect current runtime/spine contracts before changing anything.

## NODE / NEURAL CONTINUITY
Dom’s “roads, bridges, neurons, organism” language maps to real engineering requirements:
- all meaningful modules/services/extensions discoverable
- canonical registries populated
- dependency roads intact
- no orphaned nodes
- no competing authorities
- real telemetry should eventually drive the neural/AR visualization

The AR/hologram nervous system should eventually depict actual registered nodes and actual activity, not decorative random geometry.

## VOICE CONTINUITY
Text cognition comes first unless newer direct evidence shows a more fundamental organism/control-plane blocker must be resolved first. Voice/Bluetooth is a delivery layer, not a second mind. Do not add canned phrases or a second speech intelligence.

## OPERATING METHOD
For each Python script under assistant evaluation:
1. Read the exact source/version/hash being evaluated.
2. Apply the current applicable structured review gate. For the present V6 HOME-mapping candidate and present Glass V2.2 repair, that gate is 10,000 structured checks by explicit newer Dom instruction.
3. Keep PASS/FAIL/UNKNOWN auditable and never fake the count.
4. Do not claim LIVE deployment from candidate review alone.
5. If Dom authorizes LIVE replacement, mutate only the bounded canonical target, preserve backup/rollback, compile before and after, and verify resulting hashes.
6. Re-run the exact read-only qualification path after replacement.
7. Only after fresh runtime evidence shows PASS may that repair be marked complete.

For each general zone:
1. SEE current evidence.
2. Identify exact gap and organism interference.
3. State what must be preserved.
4. Build a complete repair/replacement of the canonical path only when authorized; do not create a competing path.
5. Test syntax/imports, targeted behavior, regressions, architecture, and truth claims.
6. Verify physically in LIVE through returned evidence/receipts/hashes.
7. Record the checkpoint here.
8. If healthy, stop touching that area and move to the next verified issue or idle.

## CONTINUITY UPDATE RULE
Whenever a meaningful verified state changes, update this packet with:
- current canonical build lane/version
- last verified hashes/paths relevant to the active zone
- completed repair
- unresolved blocker
- next exact step
- any new non-negotiable architectural decision from Dom

Do not overwrite historical architectural decisions casually. If a newer instruction supersedes an older one, record the supersession explicitly.

## LATEST VERIFIED REPAIR CHECKPOINT
Completed/verified LIVE checkpoints:
- canonical V3.1 Build Probe previously verified at `tools/eira2_orin_build_probe.py`, sha256 `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- stale V3.2/V3.3 activation packets quarantined
- Watcher repair Builder receipt: `ok: true`, rollback false, applying `extensions/repair_watcher_ai/plugin.py`; receipt SHA256 `918b8b4d4486ceb839f3b841c0da846e4001d471dbfc528ab712a5a4c0c81fa2`
- Universe Library V4 checkout qualification passed 50/50 tests, superseding malformed V3 checkout
- `tools/eira2_superprobe_engine.py` manifest row repaired to LIVE sha256 `8476f89f5f6aa7df4eb54d744ac6a204758e4e28e785be6e5ca0f0833f494227`, size `20138`
- subsequent V6 canonical snapshot stage passed with `359` files and no LIVE mutation during inspection.
- Glass V2.1 target identity verified at `extensions/glass_viewport_ai/plugin.py`, size `16585`, sha256 `fbe6abb5f8f7961607b7172297f4b95037da5ad80481999d3ac806f4274cfd82`; startup visibility remained incomplete because no service receipt appeared during the observed first pass.

Unresolved blockers, kept separate:
- ACTIVE GLASS/TRANSPORT: Glass V2.2 cannot yet be called deployed; canonical Builder rejected the attempt because the deployment lane dropped `before_sha256` before Watcher/Builder. An isolated lane repair exists at branch head `77d8aac7528b8cb19f3ee31ce2db3aa0fbdb6bdc`, but no terminal LIVE receipt proves that lane repair or Glass V2.2 is installed.
- ACTIVE V6: OpenCode sandbox HOME/config mapping defect; direct synthetic-HOME reproduction returns `EACCES` for `/home/eira` and V6 `opencode_inspect` returns server error `err_11254f49`.
- DEPLOYMENT PROOF: no fresh terminal Builder receipt proves the reviewed V6 HOME-mapping repair is installed or working in LIVE.
- STORAGE RISK: prior `/dev/sda1` EIO remains a historical integrity warning; fresh snapshot PASS means it is not the currently observed qualification gate, but any recurrence immediately re-promotes it above software repair.
- PACKAGE/LIBRARY: Universe Public Library historical size drift remains separate; do not roll it back blindly.
- LIBRARY SOFTWARE: `ingest_receipts` insert contract supplies 6 values to a 7-column table.
- OPENCODE GROUNDING: model/tool connectivity exists; repository-grounded autonomous behavior still requires successful contained qualification.

## CURRENT NEXT STEP
Do not modify Eira cognition, library contents, or unrelated build infrastructure during continuity refresh.

Next exact engineering step after this continuity refresh:
1. Keep canonical Build Probe V3.1 unchanged.
2. Through Dom-authorized canonical deployment, first preserve the required `before_sha256` end-to-end in the active Blueprint Deployment V4 → Watcher → Builder handoff, using the already isolated one-field repair as the candidate and verifying the lane itself before trusting it.
3. Re-run the Glass V2.2 deployment against the verified current LIVE before-hash `fbe6abb5f8f7961607b7172297f4b95037da5ad80481999d3ac806f4274cfd82`.
4. Require a terminal Builder/transport PASS receipt, exact resulting LIVE plugin hash, immediate `service.json` heartbeat, active daemon PID, and bounded/incremental scan status before marking Glass V2.2 complete.
5. After the Glass/transport zone is verified healthy, return to the separate V6 HOME/config mapping repair and re-run its fresh read-only qualification.
6. If storage EIO reappears at any point, abort software mutation/qualification and return storage integrity to primary blocker status.

No broad library rollback, no speculative filesystem repair, no speculative architecture rewrite, no duplicate subsystem, no fake pass.

---
This packet is the continuity anchor. Read it first; verify LIVE second; build third.