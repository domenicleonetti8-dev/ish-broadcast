# EIRA2 GitHub Transport Bus

This directory is ONLY the GitHub-side omnidirectional mailbox that ChatGPT can access.

The Superprobe itself lives inside EIRA LIVE on Dom's machine. GitHub does not contain, run, replace, or emulate the Superprobe.

Canonical path:

EIRA LIVE Superprobe -> GitHub transport bus -> ChatGPT
ChatGPT -> GitHub transport bus -> EIRA LIVE Superprobe -> Watcher

Mailboxes:
- `from_superprobe/` — packets exported by the real Superprobe in EIRA LIVE for ChatGPT to inspect.
- `to_superprobe/` — packets, blueprints, or instructions placed by ChatGPT for the real Superprobe to retrieve and verify.
- `receipts/` — delivery/acceptance/rejection receipts produced by the transport path.

This GitHub surface has no authority to mutate EIRA 2 directly. It is transport only. The real Superprobe remains the forensic/verification boundary and Watcher remains the evaluator/router on the EIRA side.

Packet schema: `eira2_superprobe_transport_packet_v1`.
