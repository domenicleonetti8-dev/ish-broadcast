from __future__ import annotations

"""EIRA2 Universe Archive Seed + Mass Search Runtime v1.

Canonical orchestration layer over the Knowledge Seed Vault and Universe Archive
chunk seeder. Builds verified compressed chunk seeds from materialized archive
documents, then provides indexed mass search/retrieval without scanning the raw
corpus per query.

Safety: additive only. Raw source deletion is forbidden by design.
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_universe_archive_seed_search_runtime_v1"
ROOT_DEFAULT = "/media/domenicleonetti/easystore/EIRA/LIVE"
STATUS_REL = Path("eira_probe/universe_library/seed_search_runtime_status.json")


def atomic_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def vault(root: Path):
    from eira2.evidence.knowledge_seed_vault import KnowledgeSeedVault, default_vault
    return KnowledgeSeedVault(default_vault(root))


def build(root: Path, sleep_ms: int = 15) -> dict[str, Any]:
    from eira2.evidence.universe_archive_chunk_seeder_v1 import seed_all
    status_path = root / STATUS_REL
    atomic_json(status_path, {
        "schema": SCHEMA,
        "status": "BUILD_REQUESTED",
        "ok": None,
        "raw_source_auto_delete": False,
        "source_is_not_fact": True,
        "updated_unix": time.time(),
    })
    result = seed_all(root, wait_for_bhl=True, sleep_ms=max(0, sleep_ms))
    with vault(root) as v:
        stats = v.stats()
    out = {
        "schema": SCHEMA,
        "status": "READY" if result.get("ok") else "READY_WITH_SEED_ERRORS",
        "ok": bool(result.get("ok")),
        "seed_result": result,
        "mass_search": {
            "engine": "sqlite_fts5_full_chunk",
            "fts5_full_chunk_index": bool(stats.get("fts5_full_chunk_index")),
            "query_scans_raw_archive": False,
            "decompresses_only_matching_chunks": True,
        },
        "vault_stats": stats,
        "raw_source_auto_delete": False,
        "source_is_not_fact": True,
        "updated_unix": time.time(),
    }
    atomic_json(status_path, out)
    return out


def search(root: Path, query: str, limit: int, retrieve_text: bool) -> dict[str, Any]:
    with vault(root) as v:
        results = v.retrieve(query, limit) if retrieve_text else v.search(query, limit)
        stats = v.stats()
    return {
        "schema": SCHEMA,
        "status": "SEARCH_COMPLETE",
        "query": query,
        "results": results,
        "result_count": len(results),
        "vault_stats": stats,
        "source_is_not_fact": True,
    }


def stats(root: Path) -> dict[str, Any]:
    with vault(root) as v:
        s = v.stats()
    return {
        "schema": SCHEMA,
        "status": "STATUS",
        "vault_stats": s,
        "mass_search_ready": bool(s.get("fts5_full_chunk_index")),
        "raw_source_auto_delete": False,
        "source_is_not_fact": True,
    }


def self_test(root: Path) -> dict[str, Any]:
    from eira2.evidence.knowledge_seed_vault import SCHEMA as seed_schema
    from eira2.evidence.universe_archive_chunk_seeder_v1 import SCHEMA as seeder_schema
    checks = {
        "seed_vault_v2": seed_schema == "eira2_knowledge_seed_vault_v2",
        "chunk_seeder_v1": seeder_schema == "eira2_universe_archive_chunk_seeder_v1",
        "status_under_universe_library": "universe_library" in STATUS_REL.parts,
        "raw_source_delete_disabled": True,
        "root_absolute": root.is_absolute(),
    }
    return {"schema": SCHEMA + "_self_test", "ok": all(checks.values()), "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("EIRA_LIVE_ROOT", ROOT_DEFAULT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--sleep-ms", type=int, default=15)
    q = sub.add_parser("search"); q.add_argument("query"); q.add_argument("--limit", type=int, default=12); q.add_argument("--retrieve", action="store_true")
    sub.add_parser("stats")
    sub.add_parser("self-test")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.cmd == "build": out = build(root, args.sleep_ms)
    elif args.cmd == "search": out = search(root, args.query, max(1, min(args.limit, 50)), args.retrieve)
    elif args.cmd == "stats": out = stats(root)
    else: out = self_test(root)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
