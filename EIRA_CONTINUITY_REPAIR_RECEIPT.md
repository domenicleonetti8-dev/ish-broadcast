# EIRA Continuity Repair Receipt

- Repair scope: continuity/control-record correction only; EIRA LIVE not modified.
- Stale blocker superseded: old `Supervisor V3` verification gate must not be used as a current blocker without fresh LIVE evidence.
- Canonical working branch: `orin-bridge-forensic-only`.
- Canonical working lane: Orin ⇄ GitHub ⇄ Pi ext4 control plane ⇄ Superprobe/Watcher ⇄ EIRA LIVE ⇄ receipts/telemetry back to Orin.
- Verified transport artifacts present on branch: `EIRA2_AUTONOMOUS_TRANSPORT_V6.py`, `EIRA2_AUTONOMOUS_TRANSPORT_V7.py`, `EIRA2_AUTONOMOUS_TRANSPORT_V8.py`.
- Previously verified LIVE worker: `tools/eira2_orin_build_probe.py`, SHA-256 `984bef79101a2fa238542debe16e668b85e705138d87a54b4c9c33408295802b`.
- New architectural requirement from Dom: internal evidence/state/memory/capabilities first for ordinary conversation; external information only when internal evidence is insufficient or current/external retrieval is explicitly required.
- Safety rule: surgical changes only; preserve single outward EIRA authority; no Ollama/base-model authority for identity/provenance/runtime truth.
- Next build: isolate and qualify internal-first conversation routing, then invoke only through canonical transport and require fresh LIVE deployment receipt before declaring success.
