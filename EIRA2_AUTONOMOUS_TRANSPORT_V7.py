#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
V6_PATH = HERE / "EIRA2_AUTONOMOUS_TRANSPORT_V6.py"
PUBLISH_RETRY_SECONDS = 1.0
PUBLISH_MAX_ATTEMPTS = 60


def _load_v6():
    spec = importlib.util.spec_from_file_location("eira2_transport_v6_runtime", V6_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("transport_v6_import_failed")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v6 = _load_v6()
_original_publish = v6.publish


def _receipt_is_terminal(receipt: dict[str, Any]) -> bool:
    return str(receipt.get("status") or "") in {
        "DEPLOYED_SUCCESSFULLY",
        "INSPECTION_COMPLETE",
        "SUPERSEDED_ABORTED",
    }


def durable_publish(repo: Path, request_id: str, receipt: dict[str, Any]) -> str:
    """Publish receipt synchronously and do not let the queue outrun terminal evidence."""
    terminal = _receipt_is_terminal(receipt)
    last_error = ""
    for attempt in range(1, PUBLISH_MAX_ATTEMPTS + 1):
        try:
            commit = _original_publish(repo, request_id, receipt)
            if terminal:
                marker = {
                    "schema": "eira2_transport_immediate_return_v1",
                    "request_id": request_id,
                    "status": receipt.get("status"),
                    "ok": receipt.get("ok"),
                    "completion_sha256": receipt.get("completion_sha256"),
                    "return_transport_commit": commit,
                    "publish_attempt": attempt,
                    "published_unix": time.time(),
                    "receipt_visible_before_queue_advance": True,
                }
                runtime = Path(os.environ.get(
                    "EIRA_LIVE_ROOT",
                    "/media/domenicleonetti/easystore/EIRA/LIVE",
                )) / "eira_probe" / "transport_runtime_v7" / "immediate_returns"
                v6.atomic(runtime / f"{request_id}.json", marker)
            return commit
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{exc}"[:4000]
            try:
                v6.heal_git_state(repo)
                v6.sync_repo(repo)
            except Exception:
                pass
            if attempt < PUBLISH_MAX_ATTEMPTS:
                time.sleep(PUBLISH_RETRY_SECONDS)
    raise RuntimeError("durable_receipt_publish_exhausted:" + last_error)


v6.publish = durable_publish


def main() -> int:
    return v6.main()


if __name__ == "__main__":
    raise SystemExit(main())
