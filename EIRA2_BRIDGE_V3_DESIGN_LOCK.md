EIRA2 Bridge V3 build branch. No deployment from this branch. Design lock only.

Canonical path:
ChatGPT/Orin <-> GitHub durable bus <-> Pi ext4 bridge daemon <-> EIRA LIVE

Inbound executable path:
GitHub blueprint/artifact -> exact cursor-selected inbox -> storage admission -> native Watcher authorization -> Builder -> scoped Superprobe qualification -> signed/hash-bound receipt -> GitHub

Outbound path:
EIRA diagnostics/jobs/build requests/artifacts/receipts -> ext4 outbox -> GitHub -> ChatGPT/Orin

Non-negotiable protections:
- no historical replay
- no full LIVE recursive crawl
- no raw arbitrary shell execution from GitHub
- declared target boundaries only
- source/target SHA verification
- atomic writes and rollback
- ext4 control plane independent of Easystore availability
- no legacy Watcher fallback for deploy authorization
- no direct Builder bypass
- receipts only after verification
