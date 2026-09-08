from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_gutenberg_document_indexer_v1"
ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
STATE = ROOT / "eira_probe" / "universe_library" / "gutenberg_document_index_state.json"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _work_id(path: Path) -> str:
    # Gutenberg bulk text names normally contain the numeric ebook id.
    nums = re.findall(r"\d+", path.stem)
    return nums[-1] if nums else "file_" + hashlib.sha256(path.name.encode()).hexdigest()[:24]


def _atomic(obj: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, STATE)


def index_all() -> dict[str, Any]:
    from eira2.evidence.universe_public_library import PublicLibraryVault

    started = time.time()
    with PublicLibraryVault() as vault:
        text_root = vault.root / "project_gutenberg" / "texts"
        if not text_root.is_dir():
            raise RuntimeError(f"gutenberg_text_root_missing:{text_root}")
        files = sorted(p for p in text_root.rglob("*.txt") if p.is_file())
        indexed = duplicates = errors = 0
        error_samples: list[str] = []
        now = time.time()
        for n, p in enumerate(files, 1):
            try:
                digest = _sha(p)
                wid = _work_id(p)
                rel = p.relative_to(vault.root).as_posix()
                cur = vault.db.execute(
                    "INSERT OR IGNORE INTO documents(document_hash,source_name,source_work_id,relative_path,bytes,indexed_unix) VALUES(?,?,?,?,?,?)",
                    (digest, "project_gutenberg", wid, rel, p.stat().st_size, now),
                )
                if cur.rowcount == 1:
                    indexed += 1
                else:
                    duplicates += 1
            except Exception as exc:
                errors += 1
                if len(error_samples) < 20:
                    error_samples.append(f"{p.name}:{type(exc).__name__}:{exc}")
            if n % 1000 == 0:
                _atomic({
                    "schema": SCHEMA,
                    "status": "INDEXING",
                    "ok": None,
                    "files_seen": n,
                    "files_total": len(files),
                    "indexed": indexed,
                    "duplicates": duplicates,
                    "errors": errors,
                    "updated_unix": time.time(),
                })
        stats = vault.stats()
    result = {
        "schema": SCHEMA,
        "status": "INDEX_COMPLETE",
        "ok": errors == 0,
        "files_total": len(files),
        "indexed": indexed,
        "duplicates": duplicates,
        "errors": errors,
        "error_samples": error_samples,
        "vault_stats": stats,
        "started_unix": started,
        "completed_unix": time.time(),
        "source_is_not_fact": True,
    }
    _atomic(result)
    return result


def wait_for_extract_and_index(timeout_seconds: int = 86400) -> dict[str, Any]:
    from eira2.evidence.universe_public_library import PublicLibraryVault
    started = time.time()
    while time.time() - started < timeout_seconds:
        with PublicLibraryVault() as vault:
            text_root = vault.root / "project_gutenberg" / "texts"
            if text_root.is_dir() and any(text_root.glob("*.txt")):
                return index_all()
        _atomic({"schema": SCHEMA, "status": "WAITING_FOR_GUTENBERG_EXTRACT", "ok": None, "updated_unix": time.time()})
        time.sleep(30)
    raise TimeoutError("gutenberg_extract_wait_timeout")


def self_test() -> dict[str, Any]:
    checks = {
        "schema": SCHEMA.endswith("_v1"),
        "state_under_universe_library": "universe_library" in STATE.parts,
        "numeric_id": _work_id(Path("pg12345.txt")) == "12345",
        "fallback_id": _work_id(Path("alpha.txt")).startswith("file_"),
    }
    return {"schema": SCHEMA + "_self_test", "ok": all(checks.values()), "checks": checks}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--wait-index", action="store_true")
    ap.add_argument("--timeout", type=int, default=86400)
    a = ap.parse_args()
    if a.wait_index:
        out = wait_for_extract_and_index(a.timeout)
    elif a.index:
        out = index_all()
    else:
        out = self_test()
    print(json.dumps(out, indent=2, sort_keys=True))
    raise SystemExit(0 if out.get("ok") is not False else 1)
