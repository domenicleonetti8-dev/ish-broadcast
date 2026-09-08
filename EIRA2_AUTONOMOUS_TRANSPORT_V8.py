#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
V6_CANDIDATES = [
    HERE / "EIRA2_AUTONOMOUS_TRANSPORT_V6.py",
    Path("/media/domenicleonetti/easystore/EIRA/LIVE/eira_probe/transport_runtime_v6/repo/EIRA2_AUTONOMOUS_TRANSPORT_V6.py"),
]
VOLATILE_KEYS = {
    "updated_unix",
    "started_unix",
    "completed_unix",
    "published_unix",
    "return_transport_commit",
    "publish_attempt",
}
TERMINAL = {"DEPLOYED_SUCCESSFULLY", "INSPECTION_COMPLETE", "SUPERSEDED_ABORTED"}


def _load_v6():
    for path in V6_CANDIDATES:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("eira2_transport_v6_runtime", path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("transport_v6_source_not_found")


v6 = _load_v6()
_original_publish = v6.publish


def _semantic(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _semantic(v) for k, v in sorted(value.items()) if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_semantic(v) for v in value]
    return value


def _semantic_equal(a: Any, b: Any) -> bool:
    return _semantic(a) == _semantic(b)


def publish_once(repo: Path, request_id: str, receipt: dict[str, Any]) -> str:
    """Publish only when the receipt's semantic state changed.

    Repeated timestamps, retry clocks, and publish-attempt counters never create Git commits.
    """
    v6.sync_repo(repo)
    rel = v6.RETURN_ROOT / f"{request_id}__receipt.json"
    current = repo / rel
    if current.is_file():
        try:
            old = json.loads(current.read_text(encoding="utf-8"))
            if _semantic_equal(old, receipt):
                return v6.run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=120).stdout.strip()
        except Exception:
            pass
    return _original_publish(repo, request_id, receipt)


v6.publish = publish_once


def _owner_lock(root: Path):
    runtime = root / "eira_probe" / "transport_runtime_v8"
    runtime.mkdir(parents=True, exist_ok=True)
    lock_path = runtime / "owner.lock"
    fh = lock_path.open("a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        fh.close()
        raise RuntimeError("transport_owner_already_active") from exc
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()) + "\n")
    fh.flush()
    os.fsync(fh.fileno())
    return fh


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--root", required=True)
    known, _ = ap.parse_known_args()
    root = Path(known.root).resolve()
    owner = _owner_lock(root)
    try:
        return v6.main()
    finally:
        try:
            fcntl.flock(owner.fileno(), fcntl.LOCK_UN)
        finally:
            owner.close()


if __name__ == "__main__":
    raise SystemExit(main())
