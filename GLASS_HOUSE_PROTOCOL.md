# GLASS HOUSE PROTOCOL

**EIRA continuity + permanent observation protocol**

Checkpoint: 2026-09-10
Owner / final authority: Dom
Canonical LIVE root: `/media/domenicleonetti/easystore/EIRA/LIVE`

## Purpose

Glass House replaces the old need to send an active probe merely to see EIRA. The observation path is:

`EIRA LIVE -> passive read-only Glass portals -> GitHub viewport -> Orin`

The write path remains separate:

`approved engineering -> Watcher -> Builder -> LIVE -> receipts/telemetry -> Glass/GitHub`

Glass is a window, not a door. Observation through Glass must never itself authorize or perform a LIVE mutation.

## Current verified Glass checkpoint

- LIVE target: `extensions/glass_viewport_ai/plugin.py`
- Glass version: `2.2.0`
- Exact deployed SHA-256: `5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`
- Deployment passed through Watcher -> Builder.
- Builder result: `BUILDER=True`
- Builder after SHA: `5259fd37ebae4896d13b68b1dcd8ae7d0997f0b0abc70efe1d945de275b8bdb0`
- Glass daemon was started as PID `653044` at this checkpoint. PID is historical evidence only; always use current heartbeat/liveness evidence after restart.
- GitHub heartbeat path: `eira2_transport_bus/from_superprobe/glass/heartbeat.json`
- GitHub viewport/snapshot path: `eira2_transport_bus/from_superprobe/glass/latest.json`
- Local service receipt: `eira_probe/glass_viewport/service.json`
- GitHub heartbeat was independently observed with `active=true`, `version=2.2.0`, root equal to canonical EIRA LIVE, and PID `653044`.

## Continuity checklist for every new session

1. **Start with Glass. Do not send a probe by default.** Read the GitHub Glass heartbeat and latest viewport first.
2. Confirm heartbeat freshness, `active`, version, reported root, PID/liveness evidence, cycle, portal count, scan state, and blind-spot count.
3. Read `latest.json` and use its portals as the primary passive view into LIVE.
4. Treat Glass as evidence, not authority to mutate. Never convert a read into a write automatically.
5. If a blind spot exists, identify it explicitly. The goal is zero **silent** blind spots, not a dishonest claim that every secret/kernel/external resource is visible.
6. Secrets/redacted material must remain withheld. Do not weaken redaction to increase visibility.
7. Do not ask Dom to run a probe merely because continuity was lost. Recover state from Glass/GitHub first.
8. When a LIVE modification is required, use the controlled Watcher -> Builder path and verify the resulting LIVE hash/receipt before declaring success.
9. After a successful write, confirm Glass observes the resulting state so the read and write planes agree.
10. If Glass itself is stale or down, diagnose Glass specifically. Do not infer that EIRA is down merely because the window is unavailable.

## Glass operating rules

- Passive/read-only observation only.
- Thousands of logical portals may be exposed through one bounded Glass mesh; do not create thousands of independent processes.
- Keep scanning bounded so Glass does not hammer the Easystore or monopolize EIRA.
- Large/unreadable/redacted/deferred objects must be accounted for explicitly as blind spots or deferred observations.
- Never publish secrets, credentials, tokens, private keys, environment secrets, or sensitive command-line material to GitHub.
- Avoid self-observation feedback loops: Glass output, publisher checkout, and transport-generated Glass artifacts must not recursively inflate the viewport.
- Do not trust a historical PID after reboot. Heartbeat freshness and actual current process state matter.
- `scan_complete` and portal counts are observation metadata; they do not prove semantic correctness of every component.
- GitHub is the persistent observation surface. Dom should not have to manually commit Glass telemetry.

## Deployment lesson preserved

During V2.2 deployment, two transport contract defects were exposed:

1. Blueprint Deployment Lane V4 dropped `before_sha256` while building `file_index.json`.
2. Watcher plan reconstruction dropped the before-hash again before Builder. The lane needed to restore `before_sha256` from the index into each Builder plan row.

A second race was then exposed: the shared `eira_probe/watcher_inbox_v7/stage` could be consumed/cleared by the active transport daemon's `blueprint-once` worker while another deployment used the same stage. The successful Glass deployment used an isolated Watcher inbox/stage for the Glass transaction.

**Do not regress these protections.** Builder's `before_sha256_required` gate is correct and must remain hardened.

## Known follow-up engineering item

The successful lane fixes were proven in the temporary `/tmp/glass22` deployment copy. Before treating the transport repair itself as canonical, synchronize and review the complete lane fix in GitHub/LIVE through the normal controlled engineering path. Do not mistake successful Glass V2.2 deployment for proof that every default/master transport copy already contains the final race-safe lane behavior.

## Failure protocol

If Glass heartbeat disappears or becomes stale:

- First inspect existing GitHub heartbeat/latest evidence and timestamps.
- Distinguish Glass failure from EIRA failure.
- Check whether the Glass daemon is alive before starting another instance.
- Never run duplicate Glass publishers intentionally.
- Never broadly kill EIRA/transport processes to repair Glass.
- If physical Pi action is unavoidable, give Dom one short, paste-safe command block and explain any disruptive effect before execution.

If a deployment fails:

- Do not declare success.
- Preserve the exact error and receipt.
- Verify whether Builder applied anything and whether rollback occurred.
- Continue at the exact failing contract boundary rather than rebuilding unrelated systems.
- A successful deployment requires fresh receipt/hash evidence from LIVE.

## Architecture boundary

Glass answers: **What is happening inside EIRA?**

Watcher/Builder answer: **What is allowed to change inside EIRA?**

Keep those powers separate.

## Resume instruction

On a future continuity reset, read this file first, then read:

- `eira2_transport_bus/from_superprobe/glass/heartbeat.json`
- `eira2_transport_bus/from_superprobe/glass/latest.json`

Use those as the first current-state evidence. Only fall back to an active probe when the required fact is genuinely outside Glass coverage or Glass itself must be diagnosed.

**Protocol name: GLASS HOUSE PROTOCOL**
