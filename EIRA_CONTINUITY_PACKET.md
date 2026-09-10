# EIRA Continuity Packet

## Canonical working lane

Orin ⇄ GitHub ⇄ Pi ext4 control plane ⇄ Superprobe/Watcher ⇄ EIRA LIVE ⇄ receipts/telemetry back to Orin.

Current verified LIVE execution evidence shows the active transport/build path includes Transport Runtime V10 plus `EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py`, with writes still bounded behind Watcher authorization and the canonical Builder.

## Current verified transport/build state

- Canonical continuity branch: `orin-bridge-forensic-only`.
- GitHub control ref observed by LIVE telemetry: `master`.
- Latest verified LIVE telemetry artifact: `eira2_transport_bus/from_superprobe/telemetry/orin_eira_live_latest.json`.
- Telemetry blob SHA: `578c8bf7e13582809a91db387eca9b4c32f8396f`.
- Latest telemetry return commit observed: `6935bad92ff632b85a82ea36a1e00e5d7eda74dc` (`Return EIRA LIVE telemetry through Orin bridge`, 2026-09-09T08:51:16Z).
- LIVE execution evidence shows `eira_probe/transport_runtime_v10/EIRA2_AUTONOMOUS_TRANSPORT_V10.py` running against `/media/domenicleonetti/easystore/EIRA/LIVE` and `EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py` actively executing through the canonical lane.
- The older previously verified LIVE worker `tools/eira2_orin_build_probe.py` remains historically verified at SHA-256 `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`; do not treat that older hash as proof of current V10 liveness when fresher telemetry exists.

## Latest completed verified repair

Watcher V7 deployment is verified complete through the canonical Builder lane:

- Request: `watcher_v7_full_deploy`.
- Receipt: `eira2_transport_bus/from_superprobe/bridge_receipts/watcher_v7_full_deploy__receipt.json`.
- Receipt blob SHA: `92738798633970b65da5a759cc1b133dba78f7e4`.
- Target: `extensions/repair_watcher_ai/plugin.py`.
- Before SHA-256: `81bd5fcca4f1937f6d409eeffc38851843c9e549c2277c7e787b64fcd2aa4914`.
- Verified after/completion SHA-256: `7dfcfe353a71806e89333a1c22c89849d66a88052cfd190597d0ca4bb9044cf4`.
- Builder invoked: true.
- Watcher authorized: true.
- Builder receipt schema: `eira2_builder_receipt_v3`.
- Blueprint lane receipt schema: `eira2_blueprint_lane_v4_receipt`.
- Terminal status: `DEPLOYED_SUCCESSFULLY`.
- Exact-target verification passed even though the bounded Superprobe subcheck timed out; the receipt records `superprobe_timeout_exact_target_verification_preserved` and no rollback was performed.

## Current unresolved blocker

The hardened engineering worker V2 is built and queued on GitHub but is **not yet verified installed in LIVE**.

Expected receipt still absent:

`eira2_transport_bus/from_superprobe/receipts/engineering_worker_opencode_aider_v2_hardened_deploy_20260909__receipt.json`

Do not claim `extensions/engineering_worker_ai/plugin.py` is running V2 until a fresh terminal deployment receipt proves `DEPLOYED_SUCCESSFULLY`, Watcher authorization, Builder invocation, exact target path, and completion SHA-256.

A separate forensic discrepancy also remains in the latest telemetry: package identity verification reported `eira2_package_manifest_file_size_mismatch:eira2/evidence/universe_public_library.py`. Treat this as evidence to inspect, not as permission to modify library contents during continuity work.

## Superseded blocker — DO NOT RESURRECT

The old `Supervisor V3` verification gate is superseded as a continuity blocker. Repository inspection of the current working branch produced no `SUPERVISOR_V3` or `supervisor heartbeat` match supporting that gate as a current canonical prerequisite.

Do not stop future work on that stale blocker unless a new LIVE receipt or explicit Dom instruction re-establishes it with fresh evidence.

## Current architectural decisions from Dom

### Internal-first conversation authority

For normal thoughts and conversation, EIRA must pull from her own internals first: verified runtime evidence, memory, capabilities, state, architecture knowledge, and other canonical internal sources. She should reason over those internal sources before considering outsourced information.

External retrieval is a fallback only when internal evidence is genuinely insufficient, or when Dom explicitly asks for current/external/search information. Outsourced models or services are never authoritative for EIRA identity, provenance, architecture introspection, or verified runtime truth.

### Autonomous engineering worker architecture

Newer explicit Dom direction supersedes any implication that routine engineering requires constant human prompting. The engineering path should be freely autonomous for safe/recoverable work, with occasional Dom input only when genuinely required.

Canonical engineering-worker roles:

- EIRA remains the authority and only outward conversation identity.
- OpenCode is the broad repository inspector/planner/reviewer.
- Aider is the isolated sandbox code surgeon.
- Ollama is a local model/candidate backend only and receives no authority over identity, provenance, tools, architecture truth, or final LIVE mutation.
- OpenCode and Aider must not write EIRA LIVE directly.
- Candidate work occurs in isolation/sandbox first.
- LIVE mutation remains exclusively behind Watcher authorization and the canonical Builder lane.
- Routine inspect/plan/edit/test/review/retry/reject/evidence/handoff actions should continue autonomously when safe.
- Dom input is reserved for genuine ambiguity around destructive intent, conflicting owner directives, missing required credentials/secrets, irreversible external action, explicit owner-approval gates, or unrecoverable verification failure.

## Non-negotiable safety/build rules

- Make only surgical changes that are actually needed.
- Do not perform unrelated rewrites.
- Do not create a second conversation authority.
- Do not give Ollama/base-model output authority over identity, provenance, tools, or runtime truth.
- Preserve the single outward EIRA voice.
- Use the canonical transport/build lane and require receipts/telemetry before declaring a deployment successful.
- Inspect before changing; verify after changing; if invocation fails, diagnose from the returned evidence and retry only the failed layer.
- Do not modify EIRA LIVE merely to refresh continuity records.
- Do not modify library contents, cognition, or build infrastructure merely to refresh continuity records.

## Immediate next exact step

Re-check only the canonical return lane for:

`eira2_transport_bus/from_superprobe/receipts/engineering_worker_opencode_aider_v2_hardened_deploy_20260909__receipt.json`

If it appears, validate terminal `DEPLOYED_SUCCESSFULLY`, Watcher authorization, `builder_invoked`, target `extensions/engineering_worker_ai/plugin.py`, and the exact completion SHA-256 before recording V2 as installed. If it remains absent, inspect the freshest Transport V10 telemetry/receipt state to determine why that queued request was not consumed; do not bypass Watcher/Builder and do not modify LIVE during diagnosis.

After V2 deployment is proven, qualify the worker read-only: verify OpenCode, Aider, and Ollama executable/model status through the worker/bridge before selecting any model or allowing engineering jobs.

## Continuity correction

A prior assistant response incorrectly reintroduced the stale Supervisor V3 gate after it had ceased to be supported by current repository evidence. This packet explicitly supersedes that mistake so future sessions do not use it as a blocker again.
