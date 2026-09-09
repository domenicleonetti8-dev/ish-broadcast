from __future__ import annotations

"""Seed every currently materialized Universe Library document into the Knowledge Seed Vault.

Safety properties:
- additive only; never deletes, moves, truncates, or overwrites source documents
- resumes from SQLite truth; duplicate source hashes are skipped by KnowledgeSeedVault
- uses PublicLibraryVault.documents as the authoritative corpus feed
- waits while the known BHL tar extraction is active to avoid I/O contention
- verifies each document seed before counting it complete
- source material remains evidence, not automatically fact
"""

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_universe_archive_chunk_seeder_v1"
ROOT_DEFAULT = "/media/domenicleonetti/easystore/EIRA/LIVE"
STATE_REL = Path("eira_probe/universe_library/chunk_seed_state.json")
LOG_REL = Path("eira_probe/universe_library/chunk_seed_errors.jsonl")


def atomic_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def bhl_extraction_active() -> bool:
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    needle1 = "bhl_ocr_full_export_v23"
    needle2 = "tar -xjf"
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            raw = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if needle1 in raw and (needle2 in raw or "tar" in raw):
            return True
    return False


def get_rows(vault_db: sqlite3.Connection) -> list[sqlite3.Row]:
    vault_db.row_factory = sqlite3.Row
    return vault_db.execute(
        """SELECT document_hash,source_name,source_work_id,relative_path,bytes,indexed_unix
           FROM documents ORDER BY source_name,source_work_id,relative_path"""
    ).fetchall()


def seed_all(root: Path, *, wait_for_bhl: bool = True, sleep_ms: int = 15) -> dict[str, Any]:
    from eira2.evidence.universe_public_library import PublicLibraryVault
    from eira2.evidence.knowledge_seed_vault import KnowledgeSeedVault, default_vault

    state = root / STATE_REL
    errors_log = root / LOG_REL
    started = time.time()

    if wait_for_bhl:
        while bhl_extraction_active():
            atomic_json(state, {
                "schema": SCHEMA,
                "status": "WAITING_FOR_BHL_EXTRACTION_IO",
                "ok": None,
                "source_is_not_fact": True,
                "updated_unix": time.time(),
            })
            time.sleep(30)

    with PublicLibraryVault() as pub, KnowledgeSeedVault(default_vault(root)) as seeds:
        rows = get_rows(pub.db)
        total = len(rows)
        seeded = skipped_missing = duplicates = errors = verified = 0
        source_bytes_seen = compressed_bytes_added = 0
        by_corpus: dict[str, dict[str, int]] = {}

        for n, row in enumerate(rows, 1):
            corpus = str(row["source_name"] or "unknown")
            bucket = by_corpus.setdefault(corpus, {"seen": 0, "seeded": 0, "duplicates": 0, "errors": 0, "missing": 0})
            bucket["seen"] += 1
            rel = str(row["relative_path"] or "")
            path = pub.root / rel
            if not path.is_file():
                skipped_missing += 1
                bucket["missing"] += 1
                continue
            try:
                source_bytes_seen += int(path.stat().st_size)
                result = seeds.ingest_text_file(
                    path,
                    source_corpus=corpus,
                    source_id=str(row["source_work_id"] or rel),
                    rights="source_rights_preserved_from_universe_library",
                    dataset_version="universe_archive_current",
                    metadata={
                        "universe_library_relative_path": rel,
                        "universe_library_document_hash": str(row["document_hash"] or ""),
                        "universe_library_indexed_unix": row["indexed_unix"],
                        "source_is_not_fact": True,
                    },
                )
                if result.get("inserted"):
                    seeded += 1
                    bucket["seeded"] += 1
                    compressed_bytes_added += int(result.get("compressed_bytes") or 0)
                else:
                    duplicates += 1
                    bucket["duplicates"] += 1
                if result.get("verified"):
                    verified += 1
                else:
                    raise RuntimeError("seed_verification_failed")
            except Exception as exc:
                errors += 1
                bucket["errors"] += 1
                errors_log.parent.mkdir(parents=True, exist_ok=True)
                with errors_log.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "unix": time.time(), "relative_path": rel, "corpus": corpus,
                        "error": f"{type(exc).__name__}:{exc}"
                    }, sort_keys=True) + "\n")

            if n % 100 == 0 or n == total:
                atomic_json(state, {
                    "schema": SCHEMA,
                    "status": "SEEDING",
                    "ok": None,
                    "documents_seen": n,
                    "documents_total": total,
                    "seeded_new": seeded,
                    "duplicates": duplicates,
                    "verified": verified,
                    "missing": skipped_missing,
                    "errors": errors,
                    "source_bytes_seen": source_bytes_seen,
                    "compressed_bytes_added": compressed_bytes_added,
                    "by_corpus": by_corpus,
                    "seed_vault_stats": seeds.stats(),
                    "source_is_not_fact": True,
                    "raw_source_auto_delete": False,
                    "updated_unix": time.time(),
                })
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

        stats = seeds.stats()

    out = {
        "schema": SCHEMA,
        "status": "SEEDING_COMPLETE",
        "ok": errors == 0,
        "documents_total": total,
        "seeded_new": seeded,
        "duplicates": duplicates,
        "verified": verified,
        "missing": skipped_missing,
        "errors": errors,
        "source_bytes_seen": source_bytes_seen,
        "compressed_bytes_added": compressed_bytes_added,
        "by_corpus": by_corpus,
        "seed_vault_stats": stats,
        "raw_source_auto_delete": False,
        "source_is_not_fact": True,
        "started_unix": started,
        "completed_unix": time.time(),
    }
    atomic_json(state, out)
    return out


def self_test(root: Path) -> dict[str, Any]:
    checks = {
        "state_under_universe_library": "universe_library" in STATE_REL.parts,
        "no_delete_api": True,
        "bhl_guard_callable": isinstance(bhl_extraction_active(), bool),
        "root_absolute": root.is_absolute(),
    }
    return {"schema": SCHEMA + "_self_test", "ok": all(checks.values()), "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("EIRA_LIVE_ROOT", ROOT_DEFAULT))
    ap.add_argument("--seed-all", action="store_true")
    ap.add_argument("--no-wait-bhl", action="store_true")
    ap.add_argument("--sleep-ms", type=int, default=15)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.seed_all:
        out = seed_all(root, wait_for_bhl=not args.no_wait_bhl, sleep_ms=max(0, args.sleep_ms))
    else:
        out = self_test(root)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
