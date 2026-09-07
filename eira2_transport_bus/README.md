# EIRA2 Omnidirectional Superprobe Transport Bus

This directory is the GitHub-side mailbox for `EIRA2_OMNIDIRECTIONAL_SUPERPROBE_TRANSPORT_V1.py`.

- `from_eira/` — outbound packets created from a clean EIRA2 Superprobe report or blueprint export.
- `to_eira/` — inbound packets intended for Superprobe validation and Watcher handoff.
- `receipts/` — acceptance/rejection receipts returned after validation.

Transport packet schema: `eira2_superprobe_transport_packet_v1`.

The transport boundary is `eira_probe` only. Packets do not directly modify `eira2/`, `tools/`, `main.py`, or `eira2-package-manifest.json`. Inbound packets must pass schema, SHA-256 payload, SHA-256 packet, direction, and Superprobe evidence-fingerprint checks before a Watcher handoff is created.
