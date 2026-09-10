# EIRA CONTINUITY PACKET

Status: CANONICAL CONTINUITY ANCHOR
Owner: Dom
Repository: domenicleonetti8-dev/ish-broadcast
EIRA LIVE root: /media/domenicleonetti/easystore/EIRA/LIVE

## READ THIS FIRST
Before inspecting, planning, building, repairing, or describing Eira, read this packet first. Then verify current LIVE evidence through the working GitHub ↔ Pi ↔ EIRA transport and the current canonical LIVE qualification lane before making claims or changes. This packet preserves intent and continuity; fresh LIVE evidence decides current state.

Newest continuity observation rule from Dom: use the Glass House protocol as the first passive current-state view. Read `GLASS_HOUSE_PROTOCOL.md`, then `eira2_transport_bus/from_superprobe/glass/heartbeat.json` and `eira2_transport_bus/from_superprobe/glass/latest.json` before asking Dom to run a probe. Glass is observation only; it never grants mutation authority.

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
- Glass is a window, not a door: passive Glass/GitHub observation must remain separate from Watcher/Builder mutation authority.

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

No newer terminal Builder/build receipt was found during the 2026-09-10 15:34 EDT continuity refresh. The newest commits under `from_superprobe/deployments` remain from 2026-09-09 and the newest commits under `from_superprobe/receipts` remain from 2026-09-08. Canonical Build Probe therefore remains V3.1.

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
- Newer Glass House decision: continuity inspection starts with passive Glass/GitHub evidence by default. An active probe is fallback only when the required fact is genuinely outside Glass coverage or Glass itself needs diagnosis. This supersedes the prior operational habit of sending a probe first; it does not supersede Build Probe V3.1 as the canonical build lane.

No newer explicit Dom architectural decision was found in the evidence inspected for the 2026-09-10 15:34 EDT refresh; all decisions above remain in force.

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
Current LIVE engineering worker under qualification identifies itself with schema:
`eira2_engineering_worker_opencode_aider_v6_canonical_hardened`

Fresh V6 read-only inspection evidence retained from the last verified qualification:
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

This isolates the leading V6 defect to the sandbox HOME/config mapping contract, not to a proven Ollama/model identity failure. Runtime success remains unproven until the repaired mapping is installed and re-qualified.

## COMPLETED REPAIRS
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

Glass V2.2 deployment remains a completed verified LIVE repair:
- LIVE target: `extensions/glass_viewport_ai/plugin.py`
- version: `2.2.0`
- resulting LIVE SHA256: `5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`
- successful controlled deployment result: `BUILDER=True`
- returned `AFTER=5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`
- daemon startup PID at deployment checkpoint: `653044`

Newly verified Glass observation completion evidence:
- `eira2_transport_bus/from_superprobe/glass/latest.json` is not empty.
- GitHub blob SHA: `117cc828915ed1e94400125dbfb3f234cb08667c`
- repository-reported size: `81,349,661` bytes.
- newest viewport commit observed: `b554a15ec6a5bc21b39166444bb204cbe2224445`, authored `2026-09-10T11:10:22Z` by EIRA Glass.
- This proves Glass successfully produced a large populated viewport snapshot before publication stopped; it does not prove current liveness or scan completion.

## CURRENT TRANSPORT / STORAGE STATUS
Supersession: the earlier packet described repeated `/dev/sda1` EIO as the active foundational blocker. Fresh V6 qualification successfully captured and hashed the 359-file canonical package snapshot, so the earlier EIO condition is not the currently observed execution gate.

However, prior kernel `Buffer I/O error on dev sda1` and `[Errno 5] Input/output error` evidence remains historically valid and must not be erased. It is now a storage-integrity risk requiring renewed escalation if it reappears, not the primary blocker for the current V6 qualification run.

Transport supersession: the prior Glass blocker was the Blueprint Deployment V4 → Watcher → Builder loss of `before_sha256` plus a shared Watcher stage race. Those defects were successfully worked around/fixed for the Glass transaction by preserving the before-hash through the Builder plan and using an isolated Watcher inbox/stage. That produced the verified Glass V2.2 LIVE hash above. This does NOT prove every canonical/default transport copy now contains the final race-safe lane repair.

The canonical Build Probe receipt remains V3.1. No newer terminal build/deployment receipt was found. Glass provides newer observation content than the legacy telemetry snapshot, but its publisher is not currently fresh.

## LATEST VERIFIED LIVE TELEMETRY CHECKPOINT
Latest legacy exported telemetry available through the canonical GitHub evidence lane remains:
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

## CURRENT GLASS HOUSE / VIEWPORT CHECKPOINT
The old Glass V2.1/V2.2-failed checkpoint remains superseded by verified LIVE V2.2.

Canonical protocol:
- protocol file: `GLASS_HOUSE_PROTOCOL.md`
- observation road: `EIRA LIVE -> passive read-only Glass portals -> GitHub viewport -> Orin`
- mutation road: `approved engineering -> Watcher -> Builder -> LIVE -> receipts/telemetry -> Glass/GitHub`
- architectural boundary: Glass answers “what is happening inside EIRA”; Watcher/Builder answer “what is allowed to change inside EIRA.” Keep these powers separate.

Verified deployment identity remains:
- LIVE target: `extensions/glass_viewport_ai/plugin.py`
- version: `2.2.0`
- deployed SHA256: `5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`
- deployment result: Builder invoked and returned exact matching after-hash.

Newest verified Glass publication state:
- heartbeat path: `eira2_transport_bus/from_superprobe/glass/heartbeat.json`
- heartbeat payload reports `active=true`, version `2.2.0`, canonical LIVE root, PID `653044`, cycle `113`, phase `deepening`, portal_count `33585`, blind_spot_count `10126`, `scan_complete=false`.
- heartbeat `updated_unix=1789038607.9967208`, equal to 2026-09-10 11:10:07.996721 UTC / 07:10:07 EDT.
- heartbeat Git blob SHA: `f864fc4252d59e8c37a0671346f76be142801c31`.
- `latest.json` Git blob SHA: `117cc828915ed1e94400125dbfb3f234cb08667c`.
- `latest.json` repository-reported size: `81,349,661` bytes; therefore the earlier “latest.json remains empty” statement is explicitly superseded and was incorrect for the current blob.
- newest repository Glass viewport commit observed: `b554a15ec6a5bc21b39166444bb204cbe2224445`, authored 2026-09-10 11:10:22 UTC / 07:10:22 EDT.
- at the 2026-09-10 15:34 EDT refresh, the Glass heartbeat/viewport publication stream is approximately 8 hours 24 minutes stale relative to its last observed update.

Supersession: the prior packet correctly downgraded Glass current liveness to UNKNOWN because publication stopped, but incorrectly said `latest.json` was empty. Current repository metadata proves a populated ~81 MB viewport existed at the final publication checkpoint. Glass therefore successfully built a substantial viewport before stalling. Current Glass daemon/publisher liveness still remains UNKNOWN: the historical `active=true` field cannot prove the PID is alive eight hours later, and `scan_complete=false` means the last scan had not completed.

Transport lesson retained:
1. Blueprint Deployment Lane V4 dropped `before_sha256` when generating Watcher `file_index.json`.
2. Watcher plan reconstruction also needed the before-hash restored into Builder plan rows.
3. Shared `eira_probe/watcher_inbox_v7/stage` could be consumed/cleared by the active transport daemon during another deployment.
4. Successful Glass deployment used an isolated Watcher inbox/stage for that transaction.

Unresolved transport hardening item: the successful fixes were proven in the temporary `/tmp/glass22` deployment copy for this transaction. Before declaring the transport infrastructure itself repaired canonically, synchronize/review the complete race-safe lane fix through the normal controlled engineering path. Do not mistake successful Glass V2.2 deployment for proof that every master/default/LIVE transport copy already contains those protections.

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

Important provenance correction retained: no matching V6 HOME-mapping commit was found in the accessible GitHub commit history during the prior continuity refresh. Therefore do not rely on any previously stated V6 GitHub commit SHA unless a fresh repository lookup proves it. The artifact/hash above is a reviewed candidate, not a verified GitHub-deployed or LIVE-installed state.

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
2. Apply the current applicable structured review gate. For the present V6 HOME-mapping candidate and the completed Glass V2.2 repair, that gate is 10,000 structured checks by explicit newer Dom instruction.
3. Keep PASS/FAIL/UNKNOWN auditable and never fake the count.
4. Do not claim LIVE deployment from candidate review alone.
5. If Dom authorizes LIVE replacement, mutate only the bounded canonical target, preserve backup/rollback, compile before and after, and verify resulting hashes.
6. Re-run the exact read-only qualification path after replacement.
7. Only after fresh runtime evidence shows PASS may that repair be marked complete.

For each general zone:
1. SEE current evidence. Start with Glass when applicable.
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
- canonical V3.1 Build Probe verified at `tools/eira2_orin_build_probe.py`, sha256 `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`
- stale V3.2/V3.3 activation packets quarantined
- Watcher repair Builder receipt: `ok: true`, rollback false, applying `extensions/repair_watcher_ai/plugin.py`; receipt SHA256 `918b8b4d4486ceb839f3b841c0da846e4001d471dbfc528ab712a5a4c0c81fa2`
- Universe Library V4 checkout qualification passed 50/50 tests, superseding malformed V3 checkout
- `tools/eira2_superprobe_engine.py` manifest row repaired to LIVE sha256 `8476f89f5f6aa7df4eb54d744ac6a204758e4e28e785be6e5ca0f0833f494227`, size `20138`
- subsequent V6 canonical snapshot stage passed with `359` files and no LIVE mutation during inspection
- Glass V2.2 verified LIVE at `extensions/glass_viewport_ai/plugin.py`, sha256 `5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`; Builder returned matching after-hash
- Glass successfully produced a populated viewport snapshot at `eira2_transport_bus/from_superprobe/glass/latest.json`, blob `117cc828915ed1e94400125dbfb3f234cb08667c`, repository size `81,349,661` bytes, latest observed viewport commit `b554a15ec6a5bc21b39166444bb204cbe2224445`.

Unresolved blockers, kept separate:
- ACTIVE OBSERVATION: Glass V2.2 last published at 07:10 EDT, reached cycle 113 / 33,585 portals / 10,126 accounted blind spots with `scan_complete=false`, then stopped updating. By the 15:34 EDT refresh the stream is ~8h24m stale. Current Glass liveness is therefore UNKNOWN despite its last payload saying `active=true`. The prior claim that `latest.json` was empty is superseded; it is populated but stale.
- ACTIVE V6: OpenCode sandbox HOME/config mapping defect; direct synthetic-HOME reproduction returns `EACCES` for `/home/eira` and V6 `opencode_inspect` returns server error `err_11254f49`.
- TRANSPORT HARDENING: the before-hash preservation and isolated-stage fixes succeeded for the Glass transaction, but the final race-safe lane repair is not yet proven synchronized into every canonical/default transport copy.
- DEPLOYMENT PROOF: no fresh terminal Builder receipt proves the reviewed V6 HOME-mapping repair is installed or working in LIVE.
- STORAGE RISK: prior `/dev/sda1` EIO remains a historical integrity warning; fresh snapshot PASS means it is not the currently observed qualification gate, but any recurrence immediately re-promotes it above software repair.
- PACKAGE/LIBRARY: Universe Public Library historical size drift remains separate; do not roll it back blindly.
- LIBRARY SOFTWARE: `ingest_receipts` insert contract supplies 6 values to a 7-column table.
- OPENCODE GROUNDING: model/tool connectivity exists; repository-grounded autonomous behavior still requires successful contained qualification.

## CURRENT NEXT STEP
Do not modify Eira cognition, library contents, or unrelated build infrastructure during continuity refresh.

Next exact engineering sequence after this continuity refresh:
1. Keep canonical Build Probe V3.1 unchanged.
2. Treat Glass publication freshness as the immediate continuity blocker. A populated ~81 MB viewport proves snapshot generation worked; now determine specifically why the Glass heartbeat and viewport publisher stopped after 07:10 EDT.
3. First establish whether PID `653044` / the Glass daemon is actually alive using the narrowest existing canonical diagnostic path. Do not infer process liveness from the stale heartbeat and do not infer EIRA LIVE failure from a stale Glass window.
4. Do not start a second Glass daemon or broadly kill EIRA/transport processes. If the daemon is alive, inspect its publisher/log/commit failure boundary; if it is dead, identify the terminal error before any restart.
5. Restore/verify fresh Glass publication and require advancing heartbeat/viewport commit evidence. `latest.json` no longer needs to be proven populated; that is complete. The remaining Glass completion criterion is fresh, stable publication plus explicit scan/accounting state.
6. Separately synchronize/review the complete `before_sha256` + isolated Watcher-stage race fix into the canonical transport lane before declaring transport infrastructure itself repaired.
7. After the Glass/transport observation lane is stable, return to the separate reviewed V6 HOME/config mapping candidate and re-run its fresh read-only qualification only after Dom-authorized deployment.
8. If storage EIO reappears at any point, abort software mutation/qualification and return storage integrity to primary blocker status.

No broad library rollback, no speculative filesystem repair, no speculative architecture rewrite, no duplicate subsystem, no fake pass.

---
This packet is the continuity anchor. Read it first; verify LIVE second; build third.