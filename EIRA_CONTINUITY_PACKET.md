# EIRA Continuity Packet

## Canonical working lane

Orin ⇄ GitHub ⇄ Pi ext4 control plane ⇄ Superprobe/Watcher ⇄ EIRA LIVE ⇄ receipts/telemetry back to Orin.

## Current verified transport state

- Canonical working branch: `orin-bridge-forensic-only`
- Current transport artifacts present on that branch include:
  - `EIRA2_AUTONOMOUS_TRANSPORT_V6.py`
  - `EIRA2_AUTONOMOUS_TRANSPORT_V7.py`
  - `EIRA2_AUTONOMOUS_TRANSPORT_V8.py`
- Canonical LIVE worker remains `tools/eira2_orin_build_probe.py` at verified SHA-256 `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b` from the latest previously verified build receipt.

## Superseded blocker — DO NOT RESURRECT

The old `Supervisor V3` verification gate is superseded as a continuity blocker. Repository inspection of the current working branch produced no `SUPERVISOR_V3` or `supervisor heartbeat` match supporting that gate as a current canonical prerequisite.

Do not stop future work on that stale blocker unless a new LIVE receipt or explicit Dom instruction re-establishes it with fresh evidence.

## Current architectural decision from Dom

For normal thoughts and conversation, EIRA must pull from her own internals first: verified runtime evidence, memory, capabilities, state, architecture knowledge, and other canonical internal sources. She should reason over those internal sources before considering outsourced information.

External retrieval is a fallback only when internal evidence is genuinely insufficient, or when Dom explicitly asks for current/external/search information. Outsourced models or services are never authoritative for EIRA identity, provenance, architecture introspection, or verified runtime truth.

## Non-negotiable safety/build rules

- Make only surgical changes that are actually needed.
- Do not perform unrelated rewrites.
- Do not create a second conversation authority.
- Do not give Ollama/base-model output authority over identity, provenance, tools, or runtime truth.
- Preserve the single outward EIRA voice.
- Use the canonical transport/build lane and require receipts/telemetry before declaring a deployment successful.
- Inspect before changing; verify after changing; if invocation fails, diagnose from the returned evidence and retry only the failed layer.
- Do not modify EIRA LIVE merely to refresh continuity records.

## Immediate next step

Build and qualify the internal-first general-conversation routing change in isolation, then invoke it only through the canonical working transport lane. Require repeated qualification and a fresh LIVE receipt proving the exact deployed artifact/hash before calling the repair complete.

## Continuity correction

A prior assistant response incorrectly reintroduced the stale Supervisor V3 gate after it had ceased to be supported by current repository evidence. This packet explicitly supersedes that mistake so future sessions do not use it as a blocker again.
