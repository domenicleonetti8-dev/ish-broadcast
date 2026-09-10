# EIRA CONTINUITY PACKET

Status: CANONICAL CONTINUITY ANCHOR
Owner: Dom
Repository: domenicleonetti8-dev/ish-broadcast
EIRA LIVE root: /media/domenicleonetti/easystore/EIRA/LIVE

## READ THIS FIRST
Before inspecting, planning, building, repairing, or describing Eira, read this packet first. Then verify current LIVE evidence through the working GitHub ↔ Pi ↔ EIRA transport before making claims or changes. This packet preserves intent and continuity; LIVE evidence decides current state.

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
- Evaluate one Python script at a time. Current review standard is 3,000 structured verification/review passes per Python script before proposing or authorizing mutation; do not fake pass counts or convert UNKNOWN into PASS.

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

Latest verified LIVE worker-file state:
- path: `tools/eira2_orin_build_probe.py`
- sha256: `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- deploy/compile receipt: PASS
- most recent verified build receipt commit: `1bb56a6ee3c801c1d6358958ad900509520f6afc`
- receipt id: `restore_v31_default_current_master_20260909_2033`
- receipt reported before_sha256 == after_sha256 == `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- compile_ok: true
- immediately prior incorrect worker sha256: `02a1287cdf92a940559f2d87cf7ed0d0e61eb77be82cd6f06ee3f07ab40b8e4b`

Legacy V1 remains non-canonical and must not be reactivated unless recovery evidence proves V3.1 unavailable.

Stale V3.2 and V3.3 activation packets were removed from the live build inbox and preserved in quarantine so they cannot compete with V3.1.

Supersession note: the earlier packet treated a proposed “Supervisor V3” heartbeat correction as the immediate blocker. That is no longer the canonical active blocker. Current repository/transport evidence does not justify continuing to describe an unverified Supervisor V3 as the next required repair. Do not resurrect that blocker without fresh LIVE evidence.

BUILD infrastructure is not Eira’s cognition. It exists only to inspect and surgically work on the organism.

## AUTONOMOUS ENGINEERING ARCHITECTURE — NEWER DOM DECISION
Newer explicit Dom direction supersedes the earlier narrow/single-target engineering-worker default while preserving truth, rollback, and canonical deployment boundaries.

Desired engineering organism:
- OpenCode and Aider may inspect and work broadly across Eira when a verified defect or organism-level interference justifies it.
- Each worker gets its own isolated disposable sandbox/workspace; candidate work must not directly mutate canonical LIVE.
- OpenCode acts as broad investigator/architect/reviewer.
- Aider acts as multi-file implementation/code-surgery worker.
- They should collaborate continuously through an orchestrated peer exchange rather than uncontrolled simultaneous writes.
- They may refactor, replace, create, or remove code when required to repair the canonical organism, but must not create overlapping capability owners or parallel substitute systems.
- A full candidate must pass syntax/import checks, targeted tests, regressions, architecture invariants, truth/honesty checks, and adversarial review before Watcher/Builder submission.
- Truth/evidence, Watcher authorization, canonical Builder deployment, rollback, and Dom’s owner authority are protected gates and cannot be disabled merely to make a candidate pass.
- No build may claim LIVE success without fresh returned LIVE evidence and resulting hashes.
- “Always working” means an orchestrated job loop with owner lock/heartbeat/backoff/idle behavior, not uncontrolled CPU churn.
- “Learning from mistakes” means retaining failed/rejected evidence and regression cases, not unconstrained self-modification.

Supersession — newest explicit engineering governance from Dom:
- Earlier workflow shorthand “You investigate; I build” remains directionally valid for remote diagnosis, but is now superseded where it implied the assistant could freely author or promote builds after inspection.
- Dom is the explicit approval authority. The assistant may evaluate and may create an isolated candidate only when Dom explicitly authorizes that isolated build; it must not mutate or deploy to EIRA LIVE without Dom’s specific post-review authorization.
- Work one Python script at a time.
- Each Python script must receive 3,000 structured verification/review passes before mutation is proposed/authorized. Passes must be auditable checks across distinct failure classes, not repeated ceremonial rereads.
- UNKNOWN remains UNKNOWN; never inflate an incomplete review into a passed review.
- Current engineering-worker replacement work must remain isolated until this gate is satisfied.
- Remote diagnosis should be exhausted through GitHub transport, receipts, source, telemetry, and exported evidence before asking Dom to perform a physical Pi/LIVE action.
- If a physical action is unavoidable, explain exactly what it will do and any disruptive consequence before execution; do not turn Dom into a diagnostic terminal.

GitHub engineering checkpoints now present:
- organism-preservation guard source commit: `939cb5e8776d09a4f1fc23aaeaf2f1f1a817b12c`
- organism-preservation deployment request commit: `39b5c025359fcf9fff4c1988e4b3823fe14ae138`
- free-roam V3 worker source commit: `98b2813b30bf464da670f4b356bc2d64af016fe9`
- V3 deployment request commit: `13c156100394e6a7f481352772560c3f7354888d`
- collaborative organism-safe V4 worker source commit: `e2cd31c7c85f5a1aeb53c3b85107e74cf9ac835b`
- original V4 deployment request commit: `b9cc89dea88a21f4e1d805f8f67ed4394bddce4d`
- newer surgical V4 request commit: `eed0b22559f1849c29fdc80244be94da7745a3d1`
- newer request path: `eira2_transport_bus/to_superprobe/requests/00000000_engineering_worker_v4_organism_surgical_repair_and_launch_20260910.json`
- newer request blob SHA: `21b16c647096e7860d2ec7e9f97604eaf50016c4`
- unqualified master V5 source artifact commit: `c7f9159b3be650a4e88661472f79e3fbc70e5987`; this is GitHub source existence only and is not a qualified or deployed canonical replacement.
- isolated V5 replacement review branch: `orin-v5-engineering-worker-isolated-review`
- isolated V5 replacement commit: `7e09a20b507feb19665a648289f155b5c24ac723`
- isolated V5 path: `EIRA2_ENGINEERING_WORKER_OPENCODE_AIDER_V5_CANONICAL.py`
- isolated V5 blob SHA: `9b8079e701f0760bb1b2790e11fee52f9fa9d999`

These source/request commits prove GitHub artifact existence only. They do NOT prove any engineering-worker replacement is installed or running in EIRA LIVE. The isolated V5 artifact remains under review and must not be promoted merely because it compiles or exists on GitHub.

## CURRENT TRANSPORT / ENGINEERING BLOCKER
Supersession: the earlier active blocker was framed primarily as “V4 request has no terminal receipt.” Newer direct evidence proves a deeper blocker beneath that symptom.

Verified physical/LIVE evidence includes repeated kernel-level `/dev/sda1` block read failures (`Buffer I/O error on dev sda1`) and multiple unrelated LIVE path reads returning `[Errno 5] Input/output error`, including the Build Probe and V10 transport script. This proves the active fault is below Python/Eira at the block-device/filesystem I/O layer. It does NOT yet prove whether the exact root cause is failing media, USB/SATA bridge, cable/power/UAS transport, filesystem damage, or another block-device path issue.

The surgical V4 request explicitly requires abort-on-EIO behavior and must remain untrusted/unconsumed until a fresh terminal receipt proves otherwise. No verified receipt exists for either:
- `engineering_worker_opencode_aider_v4_organism_deploy_20260909`, or
- `engineering_worker_v4_organism_surgical_repair_and_launch_20260910`.

Therefore:
- do not claim V4 or V5 installed or active in LIVE;
- do not invoke a guessed engineering-worker path;
- do not bypass Watcher/Builder to force-install it;
- do not run OpenCode/Aider against canonical LIVE while `/dev/sda1` is returning block I/O errors;
- treat missing engineering-worker terminal receipts as downstream symptoms until storage-path stability is established;
- even after storage becomes stable, do not promote an assistant-authored Python replacement until its required 3,000-pass review and Dom approval gate are complete.

A manual OpenCode/Ollama invocation proved the configured model is visible, but the model emitted a placeholder `/path/to/repo/docker-compose.yml` read request instead of verified Eira architecture evidence. Therefore OpenCode model connectivity is proven, but autonomous repository-grounding reliability is NOT yet proven and must remain behind evidence gates.

## LATEST VERIFIED LIVE TELEMETRY CHECKPOINT
Latest exported telemetry available through the canonical GitHub evidence lane remains:
- path: `eira2_transport_bus/from_superprobe/telemetry/orin_eira_live_latest.json`
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

No newer verified LIVE Builder/transport receipt was found during this refresh. The same latest Superprobe snapshot still reports one package discrepancy: `eira2_package_manifest_file_size_mismatch:eira2/evidence/universe_public_library.py`. Keep this separate from the storage EIO until causality is proven.

## CURRENT PACKAGE / LIBRARY CHECKPOINT
The Universe Library evidence separates several historical states and defects that must not be conflated.

Verified historical Public Library deployment:
- target: `eira2/evidence/universe_public_library.py`
- deployed/observed SHA256 at that checkpoint: `2230858386e4f8887202efe6b0d3a40b208304d30f0099d37a304a065e93d5fc`
- size: 17170 bytes
- Builder reported identical before/after hash, so that deployment was effectively a verified no-op against an already matching file.

A later package checkpoint preserved a newer protected Public Library state:
- size: 17338 bytes
- sha256: `f4f87b00d1dcd15aff39c75295441cb100a48df5a11175dae61ccfe485069ca3`
- package_tree_sha256: `4443280bebdfe2967996b681d3efa051e0c040eef0b91a458cc776d97498ea58`

Do NOT roll back or edit the public library file merely to match the historical 17170-byte row. A Superprobe size mismatch can represent stale manifest drift; it is not proof of file corruption.

Historical malformed Universe Library V3 checkout was rejected by qualification with an `IndentationError`. It was superseded by V4 checkout qualification, which passed 50/50 tests. Do not resurrect the malformed V3 artifact as an active blocker.

Separate real software defect still evidenced in Universe Library refresh state:
`OperationalError: table ingest_receipts has 7 columns but 6 values were supplied`
This is a SQLite schema/write-contract defect and is independent of the `/dev/sda1` block I/O failure unless new evidence proves a causal link.

Do not broad-regenerate the package manifest. Prefer exact targeted verification/repair only after storage is stable and current evidence identifies a real mismatch.

## IMMEDIATE ENGINEERING PRIORITY
Keep cognition/library contents untouched while protecting Eira and identifying the physical storage-path failure before any autonomous engineering deployment.

Order:
1. Preserve current canonical V3.1 Build Probe checkpoint and known hash; do not assume the file is currently readable merely because it was previously verified.
2. Treat repeated `/dev/sda1` kernel block I/O errors and LIVE `[Errno 5]` failures as the active foundational blocker.
3. Do not write, deploy, launch OpenCode/Aider, or run filesystem repair against LIVE while storage reliability is unresolved.
4. Use remote/exported evidence first to distinguish what is known from what is not known. Current GitHub telemetry does not contain enough SMART/USB/UAS/mount/filesystem evidence to distinguish failing media from bridge/cable/power/UAS/filesystem causes.
5. In parallel with non-mutating storage investigation, keep the isolated V5 engineering-worker replacement confined to `orin-v5-engineering-worker-isolated-review` and continue its one-script-at-a-time 3,000-pass evaluation. No promotion to master/LIVE follows from review progress alone.
6. If a physical Pi action becomes unavoidable, choose the smallest evidence-preserving action and explain its exact effects before Dom executes it.
7. Once the storage path is proven stable, re-establish read-only Superprobe/transport qualification and obtain fresh hashes for the Build Probe, Watcher, Builder, transport, package identity, and any proposed engineering-worker target path.
8. Do not consume the older queued V4 request merely because storage recovers if it has been superseded by the reviewed V5 replacement. Record that supersession only after Dom explicitly chooses V5 and its review gate passes.
9. For any chosen worker replacement, require Dom’s explicit post-review build/deployment authorization, Watcher → Builder transaction, fresh terminal deployment receipt, resulting LIVE target SHA256, self-test, sandbox separation, peer-exchange proof, truth/evidence qualification, and one full successful engineering cycle before unattended operation.
10. After control-plane stability, repair the separate SQLite `ingest_receipts` 7-vs-6 contract surgically; reseal package identity only if current verified content requires it.

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
Text cognition comes first unless newer direct evidence shows a more fundamental organism/control-plane blocker must be resolved first.

Supersession: current storage-layer block I/O instability is more fundamental than text/voice engineering work and must be resolved first. After storage/control-plane qualification passes, return to text cognition and then the existing canonical delivery path into voice/Flash Cube. Do not add canned phrases or a second speech intelligence. Voice/Bluetooth is a delivery layer, not a second mind.

## OPERATING METHOD
Work slowly enough to preserve meaning, but do not stall in analysis. Hyperfocus one verified issue at a time while allowing complete multi-file repair when the real defect crosses file boundaries.

For each Python script under assistant evaluation:
1. Read the exact source/version/hash being evaluated.
2. Complete 3,000 structured verification/review passes across distinct failure classes; keep PASS/FAIL/UNKNOWN auditable and never fake the count.
3. Do not mutate/promote that script until the review is complete and Dom explicitly authorizes the specific build.
4. If authorized, build only in the approved isolated workspace/branch first.
5. Re-review the resulting exact candidate; source changes invalidate prior pass claims for the changed areas and require renewed evaluation appropriate to the change.
6. Only after Dom’s explicit deployment authorization may Watcher/Builder be asked to mutate LIVE.
7. Verify physically through returned LIVE receipts/hashes. If healthy, stop touching that area.

For each general zone:
1. SEE current evidence.
2. Identify exact gap and organism interference.
3. State what must be preserved.
4. Build a complete repair/replacement of the canonical path only when authorized; do not create a competing path.
5. Test syntax/imports, targeted behavior, regressions, architecture, and truth claims.
6. Verify it physically in LIVE through Watcher/Builder and returned hashes.
7. Record the new checkpoint here.
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
Completed/verified LIVE checkpoints remain:
- canonical V3.1 default worker previously verified at `tools/eira2_orin_build_probe.py`
- sha256 `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- Python compile validation passed at that checkpoint
- stale V3.2/V3.3 live activation packets quarantined
- Watcher repair later produced a Builder receipt with `ok: true`, rollback false, applying `extensions/repair_watcher_ai/plugin.py`; receipt SHA256 `918b8b4d4486ceb839f3b841c0da846e4001d471dbfc528ab712a5a4c0c81fa2`
- Universe Library V4 checkout qualification passed 50/50 tests, superseding the malformed V3 checkout artifact.

No newer verified LIVE repair was found during this refresh.

Newer source/build preparation exists on GitHub but is not verified in LIVE:
- collaborative OpenCode+Aider engineering worker V4 source commit `e2cd31c7c85f5a1aeb53c3b85107e74cf9ac835b`
- surgical V4 request commit `eed0b22559f1849c29fdc80244be94da7745a3d1`
- unqualified master V5 source artifact commit `c7f9159b3be650a4e88661472f79e3fbc70e5987`
- isolated V5 review candidate commit `7e09a20b507feb19665a648289f155b5c24ac723`, blob `9b8079e701f0760bb1b2790e11fee52f9fa9d999`, branch `orin-v5-engineering-worker-isolated-review`
- no fresh terminal receipt proves V4 or V5 deployment or execution.

Unresolved blockers, kept separate:
- PRIMARY: repeated kernel `Buffer I/O error on dev sda1` plus unrelated LIVE `[Errno 5] Input/output error` reads. Exact physical/transport/filesystem cause remains unverified.
- GOVERNANCE: assistant-authored Python engineering replacements require one-script-at-a-time 3,000-pass structured review plus Dom’s explicit post-review authorization before mutation/deployment.
- DOWNSTREAM: existing V4 request has no verified terminal receipt and must not be forced while storage is unstable; it may later be superseded by V5 only by explicit Dom decision after review.
- PACKAGE: Superprobe snapshot reported `eira2/evidence/universe_public_library.py` size mismatch; likely stale manifest drift is plausible, but current cause must be verified after storage stability.
- LIBRARY SOFTWARE: `ingest_receipts` insert contract supplies 6 values to a 7-column table.
- OPENCODE GROUNDING: connectivity proven; reliable repository-grounded autonomous behavior not yet proven.

## CURRENT NEXT STEP
Do not modify Eira cognition, library contents, package contents, or build infrastructure during continuity refresh.

Protect Eira first. Establish storage-path stability before any further LIVE deployment or autonomous engineering. Continue reviewing only the isolated V5 worker candidate under the 3,000-pass one-script gate without promoting it. Once storage is stable, perform a fresh read-only canonical qualification of Build Probe/Watcher/Builder/transport/package identity and proposed worker target. After the V5 review gate is complete, Dom decides whether V5 supersedes V4 and whether any build/deployment is authorized. Only an explicitly authorized candidate may proceed through Watcher → Builder, with a fresh terminal receipt and resulting target hash required before claiming success. Repair the separate SQLite 7-vs-6 contract afterward through the same canonical path.

No broad library rollback, no speculative filesystem repair, no speculative architecture rewrite, no duplicate subsystem, no fake pass.

---
This packet is the continuity anchor. Read it first; verify LIVE second; build third.