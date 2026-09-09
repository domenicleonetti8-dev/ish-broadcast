from __future__ import annotations

"""EIRA2 Full Book Seed Library v2.

Canonical book-level compression/retrieval layer for the Universe Library.

Invariant:
    one complete logical book/work -> one verified document_seed_id
    one seed -> many independently compressed chunks
    search -> index only
    retrieval -> decompress only matching chunks

Raw source preservation is mandatory. No source deletion API exists here.
"""

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_full_book_seed_library_v2"
ROOT_DEFAULT = "/media/domenicleonetti/easystore/EIRA/LIVE"
STATUS_REL = Path("eira_probe/universe_library/full_book_seed_status.json")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _vault(root: Path):
    from eira2.evidence.knowledge_seed_vault import KnowledgeSeedVault, default_vault
    return KnowledgeSeedVault(default_vault(root))


def _archive(root: Path):
    from eira2.evidence.universe_public_library import PublicLibraryVault
    return PublicLibraryVault()


def _book_rows(pub) -> list[sqlite3.Row]:
    pub.db.row_factory = sqlite3.Row
    return pub.db.execute(
        """SELECT document_hash,source_name,source_work_id,relative_path,bytes,indexed_unix
           FROM documents
           ORDER BY source_name,source_work_id,relative_path"""
    ).fetchall()


def build_all_books(root: Path, sleep_ms: int = 10) -> dict[str, Any]:
    status_path = root / STATUS_REL
    started = time.time()
    atomic_json(status_path, {
        "schema": SCHEMA,
        "status": "BUILDING",
        "ok": None,
        "book_granularity": True,
        "raw_source_auto_delete": False,
        "updated_unix": started,
    })

    seeded = duplicates = missing = errors = verified = 0
    source_bytes = compressed_bytes = 0
    by_corpus: dict[str, dict[str, int]] = {}

    with _archive(root) as pub, _vault(root) as seeds:
        rows = _book_rows(pub)
        total = len(rows)
        for n, row in enumerate(rows, 1):
            corpus = str(row["source_name"] or "unknown")
            bucket = by_corpus.setdefault(corpus, {"books": 0, "seeded": 0, "duplicates": 0, "missing": 0, "errors": 0})
            bucket["books"] += 1
            rel = str(row["relative_path"] or "")
            path = pub.root / rel
            if not path.is_file():
                missing += 1
                bucket["missing"] += 1
                continue
            try:
                source_bytes += int(path.stat().st_size)
                result = seeds.ingest_text_file(
                    path,
                    source_corpus=corpus,
                    source_id=str(row["source_work_id"] or rel),
                    rights="source_rights_preserved_from_universe_library",
                    dataset_version="universe_archive_full_book_v2",
                    metadata={
                        "logical_unit": "complete_book_or_work",
                        "universe_library_relative_path": rel,
                        "universe_library_document_hash": str(row["document_hash"] or ""),
                        "universe_library_indexed_unix": row["indexed_unix"],
                        "source_is_not_fact": True,
                    },
                )
                if result.get("inserted"):
                    seeded += 1
                    bucket["seeded"] += 1
                    compressed_bytes += int(result.get("compressed_bytes") or 0)
                else:
                    duplicates += 1
                    bucket["duplicates"] += 1
                if result.get("verified"):
                    verified += 1
                else:
                    raise RuntimeError("book_seed_verification_failed")
            except Exception:
                errors += 1
                bucket["errors"] += 1

            if n % 100 == 0 or n == total:
                atomic_json(status_path, {
                    "schema": SCHEMA,
                    "status": "BUILDING",
                    "ok": None,
                    "books_seen": n,
                    "books_total": total,
                    "seeded_new": seeded,
                    "duplicates": duplicates,
                    "verified": verified,
                    "missing": missing,
                    "errors": errors,
                    "source_bytes_seen": source_bytes,
                    "compressed_bytes_added": compressed_bytes,
                    "by_corpus": by_corpus,
                    "vault_stats": seeds.stats(),
                    "raw_source_auto_delete": False,
                    "updated_unix": time.time(),
                })
            if sleep_ms:
                time.sleep(max(0, sleep_ms) / 1000.0)

        stats = seeds.stats()

    out = {
        "schema": SCHEMA,
        "status": "READY" if errors == 0 else "READY_WITH_ERRORS",
        "ok": errors == 0,
        "books_total": total,
        "seeded_new": seeded,
        "duplicates": duplicates,
        "verified": verified,
        "missing": missing,
        "errors": errors,
        "source_bytes_seen": source_bytes,
        "compressed_bytes_added": compressed_bytes,
        "vault_stats": stats,
        "retrieval": {
            "search_scans_raw_books": False,
            "whole_book_decompression_required": False,
            "decompress_matching_chunks_only": True,
            "index": "sqlite_fts5_full_chunk",
        },
        "raw_source_auto_delete": False,
        "started_unix": started,
        "completed_unix": time.time(),
    }
    atomic_json(status_path, out)
    return out


def search(root: Path, query: str, limit: int = 12) -> dict[str, Any]:
    with _vault(root) as v:
        hits = v.search(query, limit)
        stats = v.stats()
    return {"schema": SCHEMA, "status": "SEARCH_COMPLETE", "query": query, "results": hits, "vault_stats": stats}


def hydrate(root: Path, query: str, limit: int = 8, max_chars: int = 16000) -> dict[str, Any]:
    with _vault(root) as v:
        hits = v.retrieve(query, limit, max_chars)
        stats = v.stats()
    return {
        "schema": SCHEMA,
        "status": "CHUNKS_HYDRATED",
        "query": query,
        "results": hits,
        "decompressed_matching_chunks_only": True,
        "whole_book_decompressed": False,
        "vault_stats": stats,
    }


def stats(root: Path) -> dict[str, Any]:
    with _vault(root) as v:
        s = v.stats()
    return {"schema": SCHEMA, "status": "STATUS", "vault_stats": s, "raw_source_auto_delete": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("EIRA_LIVE_ROOT", ROOT_DEFAULT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-all-books"); b.add_argument("--sleep-ms", type=int, default=10)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=12)
    h = sub.add_parser("hydrate"); h.add_argument("query"); h.add_argument("--limit", type=int, default=8); h.add_argument("--max-chars", type=int, default=16000)
    sub.add_parser("stats")
    a = ap.parse_args(); root = Path(a.root).resolve()
    if a.cmd == "build-all-books": out = build_all_books(root, a.sleep_ms)
    elif a.cmd == "search": out = search(root, a.query, max(1, min(a.limit, 50)))
    elif a.cmd == "hydrate": out = hydrate(root, a.query, max(1, min(a.limit, 50)), max(256, a.max_chars))
    else: out = stats(root)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
