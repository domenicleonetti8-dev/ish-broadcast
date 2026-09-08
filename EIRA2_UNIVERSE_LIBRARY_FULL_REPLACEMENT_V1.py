from __future__ import annotations

# Transport-safe full replacement source.
TARGET = "eira2/evidence/universe_library.py"

NEW = r'''from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
TRUTH_STATES = {"candidate", "accepted", "contested", "superseded", "rejected", "unknown"}
EPISTEMIC_CLASSES = {
    "fact", "measurement", "observation", "historical_record", "derived_result",
    "scientific_model", "consensus", "hypothesis", "procedure", "equation", "fiction_culture"
}


class UniverseLibraryError(RuntimeError):
    pass


class InvalidSeedError(UniverseLibraryError):
    pass


class DuplicateConflictError(UniverseLibraryError):
    pass


@dataclass(frozen=True)
class ArchiveResult:
    seed_id: str
    inserted: bool
    merged_provenance: int


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_seed_id(*, subject: str, claim: str, temporal_scope: str, epistemic_class: str) -> str:
    payload = {
        "subject": _norm(subject),
        "claim": _norm(claim),
        "temporal_scope": _norm(temporal_scope),
        "epistemic_class": _norm(epistemic_class),
    }
    return "seed_" + _sha256_text(_stable_json(payload))


def content_hash(seed: Mapping[str, Any]) -> str:
    excluded = {"source_refs", "sources", "relationships", "seed_hash"}
    payload = {k: seed[k] for k in sorted(seed) if k not in excluded}
    return _sha256_text(_stable_json(payload))


def _require_text(seed: Mapping[str, Any], key: str) -> str:
    value = str(seed.get(key, "")).strip()
    if not value:
        raise InvalidSeedError(f"missing_or_empty:{key}")
    return value


def validate_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    subject = _require_text(seed, "subject")
    claim = _require_text(seed, "canonical_claim")
    domain = _require_text(seed, "domain")
    epistemic = _require_text(seed, "epistemic_class")
    temporal = _require_text(seed, "temporal_scope")
    truth = _require_text(seed, "truth_state")
    if epistemic not in EPISTEMIC_CLASSES:
        raise InvalidSeedError("invalid_epistemic_class")
    if truth not in TRUTH_STATES:
        raise InvalidSeedError("invalid_truth_state")
    try:
        confidence = float(seed.get("confidence"))
    except Exception as exc:
        raise InvalidSeedError("invalid_confidence") from exc
    if not 0.0 <= confidence <= 1.0:
        raise InvalidSeedError("confidence_out_of_range")
    cosmic_scope = str(seed.get("geographic_or_cosmic_scope", "unspecified")).strip() or "unspecified"
    seed_id = canonical_seed_id(
        subject=subject,
        claim=claim,
        temporal_scope=temporal,
        epistemic_class=epistemic,
    )
    normalized = {
        "seed_id": seed_id,
        "subject": subject.strip(),
        "canonical_claim": claim.strip(),
        "domain": domain.strip(),
        "epistemic_class": epistemic,
        "temporal_scope": temporal.strip(),
        "geographic_or_cosmic_scope": cosmic_scope,
        "truth_state": truth,
        "confidence": confidence,
        "version": int(seed.get("version", 1)),
        "contradictions": list(seed.get("contradictions") or []),
        "metadata": dict(seed.get("metadata") or {}),
    }
    if normalized["version"] < 1:
        raise InvalidSeedError("invalid_version")
    normalized["seed_hash"] = content_hash(normalized)
    return normalized


class UniverseLibrary:
    """Durable archive layer only. It never promotes truth or speaks for Eira.

    Evidence/Truth Gate authorities decide epistemic state. This class stores their
    resulting records, enforces canonical uniqueness, preserves provenance/history,
    and provides retrieval/indexing primitives.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "UniverseLibrary":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seeds(
                seed_id TEXT PRIMARY KEY,
                seed_hash TEXT NOT NULL,
                subject TEXT NOT NULL,
                normalized_subject TEXT NOT NULL,
                canonical_claim TEXT NOT NULL,
                normalized_claim TEXT NOT NULL,
                domain TEXT NOT NULL,
                epistemic_class TEXT NOT NULL,
                temporal_scope TEXT NOT NULL,
                scope TEXT NOT NULL,
                truth_state TEXT NOT NULL,
                confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
                version INTEGER NOT NULL CHECK(version >= 1),
                contradictions_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(normalized_subject, normalized_claim, temporal_scope, epistemic_class)
            );
            CREATE TABLE IF NOT EXISTS sources(
                source_id TEXT PRIMARY KEY,
                source_uri TEXT NOT NULL,
                source_title TEXT NOT NULL DEFAULT '',
                publisher TEXT NOT NULL DEFAULT '',
                source_date TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                source_kind TEXT NOT NULL DEFAULT 'unknown',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(source_hash, source_uri)
            );
            CREATE TABLE IF NOT EXISTS seed_sources(
                seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                relation TEXT NOT NULL DEFAULT 'supports',
                PRIMARY KEY(seed_id, source_id, relation)
            );
            CREATE TABLE IF NOT EXISTS edges(
                from_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
                relation TEXT NOT NULL,
                to_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(from_seed_id, relation, to_seed_id)
            );
            CREATE TABLE IF NOT EXISTS supersession(
                old_seed_id TEXT PRIMARY KEY REFERENCES seeds(seed_id) ON DELETE CASCADE,
                new_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(old_seed_id <> new_seed_id)
            );
            CREATE INDEX IF NOT EXISTS idx_seeds_domain ON seeds(domain);
            CREATE INDEX IF NOT EXISTS idx_seeds_truth ON seeds(truth_state);
            CREATE INDEX IF NOT EXISTS idx_seeds_subject ON seeds(normalized_subject);
            CREATE INDEX IF NOT EXISTS idx_seeds_temporal ON seeds(temporal_scope);
            CREATE INDEX IF NOT EXISTS idx_sources_uri ON sources(source_uri);
            CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_seed_id);
            """
        )
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        try:
            self.db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS seed_fts USING fts5(seed_id UNINDEXED, subject, canonical_claim, domain, content='')"
            )
            self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts5','1')")
        except sqlite3.OperationalError:
            self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts5','0')")

    def schema_version(self) -> int:
        row = self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row[0])

    def _source_id(self, source: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
        uri = str(source.get("source_uri", "")).strip()
        retrieved = str(source.get("retrieved_at", "")).strip()
        source_hash = str(source.get("source_hash", "")).strip()
        if not uri or not retrieved or not source_hash:
            raise InvalidSeedError("source_requires_uri_retrieved_at_hash")
        sid = "src_" + _sha256_text(_stable_json({"uri": uri, "hash": source_hash}))
        normalized = {
            "source_id": sid,
            "source_uri": uri,
            "source_title": str(source.get("source_title", "")).strip(),
            "publisher": str(source.get("publisher", "")).strip(),
            "source_date": str(source.get("source_date", "")).strip(),
            "retrieved_at": retrieved,
            "source_hash": source_hash,
            "source_kind": str(source.get("source_kind", "unknown")).strip() or "unknown",
            "metadata_json": _stable_json(dict(source.get("metadata") or {})),
        }
        return sid, normalized

    def archive_seed(self, seed: Mapping[str, Any], sources: Sequence[Mapping[str, Any]] = ()) -> ArchiveResult:
        normalized = validate_seed(seed)
        sid = normalized["seed_id"]
        merged = 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute("SELECT * FROM seeds WHERE seed_id=?", (sid,)).fetchone()
            inserted = existing is None
            if existing is not None:
                immutable = (
                    existing["normalized_subject"], existing["normalized_claim"],
                    existing["temporal_scope"], existing["epistemic_class"]
                )
                proposed = (
                    _norm(normalized["subject"]), _norm(normalized["canonical_claim"]),
                    normalized["temporal_scope"], normalized["epistemic_class"]
                )
                if immutable != proposed:
                    raise DuplicateConflictError("canonical_seed_identity_conflict")
                self.db.execute(
                    "UPDATE seeds SET truth_state=?,confidence=?,version=MAX(version,?),contradictions_json=?,metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE seed_id=?",
                    (normalized["truth_state"], normalized["confidence"], normalized["version"],
                     _stable_json(normalized["contradictions"]), _stable_json(normalized["metadata"]), sid),
                )
            else:
                self.db.execute(
                    "INSERT INTO seeds(seed_id,seed_hash,subject,normalized_subject,canonical_claim,normalized_claim,domain,epistemic_class,temporal_scope,scope,truth_state,confidence,version,contradictions_json,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, normalized["seed_hash"], normalized["subject"], _norm(normalized["subject"]),
                     normalized["canonical_claim"], _norm(normalized["canonical_claim"]), normalized["domain"],
                     normalized["epistemic_class"], normalized["temporal_scope"], normalized["geographic_or_cosmic_scope"],
                     normalized["truth_state"], normalized["confidence"], normalized["version"],
                     _stable_json(normalized["contradictions"]), _stable_json(normalized["metadata"])),
                )
                try:
                    self.db.execute(
                        "INSERT INTO seed_fts(seed_id,subject,canonical_claim,domain) VALUES(?,?,?,?)",
                        (sid, normalized["subject"], normalized["canonical_claim"], normalized["domain"]),
                    )
                except sqlite3.OperationalError:
                    pass
            for source in sources:
                source_id, row = self._source_id(source)
                self.db.execute(
                    "INSERT OR IGNORE INTO sources(source_id,source_uri,source_title,publisher,source_date,retrieved_at,source_hash,source_kind,metadata_json) VALUES(:source_id,:source_uri,:source_title,:publisher,:source_date,:retrieved_at,:source_hash,:source_kind,:metadata_json)",
                    row,
                )
                before = self.db.total_changes
                self.db.execute(
                    "INSERT OR IGNORE INTO seed_sources(seed_id,source_id,relation) VALUES(?,?,?)",
                    (sid, source_id, str(source.get("relation", "supports")).strip() or "supports"),
                )
                if self.db.total_changes > before:
                    merged += 1
            self.db.execute("COMMIT")
            return ArchiveResult(seed_id=sid, inserted=inserted, merged_provenance=merged)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def get_seed(self, seed_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM seeds WHERE seed_id=?", (seed_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["contradictions"] = json.loads(out.pop("contradictions_json"))
        out["metadata"] = json.loads(out.pop("metadata_json"))
        out["sources"] = [dict(r) for r in self.db.execute(
            "SELECT s.*,ss.relation FROM sources s JOIN seed_sources ss ON ss.source_id=s.source_id WHERE ss.seed_id=? ORDER BY s.source_id",
            (seed_id,),
        )]
        return out

    def add_edge(self, from_seed_id: str, relation: str, to_seed_id: str, metadata: Mapping[str, Any] | None = None) -> bool:
        if from_seed_id == to_seed_id:
            raise UniverseLibraryError("self_edge_forbidden")
        relation = str(relation).strip()
        if not relation:
            raise UniverseLibraryError("empty_relation")
        before = self.db.total_changes
        self.db.execute(
            "INSERT OR IGNORE INTO edges(from_seed_id,relation,to_seed_id,metadata_json) VALUES(?,?,?,?)",
            (from_seed_id, relation, to_seed_id, _stable_json(dict(metadata or {}))),
        )
        return self.db.total_changes > before

    def supersede(self, old_seed_id: str, new_seed_id: str, reason: str = "") -> None:
        if old_seed_id == new_seed_id:
            raise UniverseLibraryError("self_supersession_forbidden")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT OR REPLACE INTO supersession(old_seed_id,new_seed_id,reason) VALUES(?,?,?)",
                (old_seed_id, new_seed_id, str(reason)),
            )
            self.db.execute("UPDATE seeds SET truth_state='superseded',updated_at=CURRENT_TIMESTAMP WHERE seed_id=?", (old_seed_id,))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def search(self, query: str, *, limit: int = 25, truth_state: str | None = None) -> list[dict[str, Any]]:
        query = str(query).strip()
        limit = max(1, min(int(limit), 500))
        if not query:
            return []
        params: list[Any] = []
        where = ""
        if truth_state is not None:
            if truth_state not in TRUTH_STATES:
                raise UniverseLibraryError("invalid_truth_filter")
            where = " AND truth_state=?"
            params.append(truth_state)
        like = f"%{_norm(query)}%"
        rows = self.db.execute(
            f"SELECT seed_id,subject,canonical_claim,domain,epistemic_class,temporal_scope,scope,truth_state,confidence,version FROM seeds WHERE (normalized_subject LIKE ? OR normalized_claim LIKE ? OR lower(domain) LIKE ?){where} ORDER BY confidence DESC, seed_id LIMIT ?",
            [like, like, like, *params, limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def timeline(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seed_id,subject,canonical_claim,temporal_scope,truth_state,confidence FROM seeds ORDER BY temporal_scope,seed_id LIMIT ?",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        count = lambda table: int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        by_domain = {r[0]: int(r[1]) for r in self.db.execute("SELECT domain,COUNT(*) FROM seeds GROUP BY domain ORDER BY domain")}
        by_truth = {r[0]: int(r[1]) for r in self.db.execute("SELECT truth_state,COUNT(*) FROM seeds GROUP BY truth_state ORDER BY truth_state")}
        return {
            "schema_version": self.schema_version(),
            "seeds": count("seeds"),
            "sources": count("sources"),
            "seed_source_links": count("seed_sources"),
            "edges": count("edges"),
            "supersessions": count("supersession"),
            "by_domain": by_domain,
            "by_truth_state": by_truth,
        }

    def export_seed(self, seed_id: str) -> str:
        seed = self.get_seed(seed_id)
        if seed is None:
            raise UniverseLibraryError("seed_not_found")
        return _stable_json(seed)


def _sample_seed(subject: str = "Earth", claim: str = "Earth orbits the Sun", truth: str = "accepted") -> dict[str, Any]:
    return {
        "subject": subject,
        "canonical_claim": claim,
        "domain": "astronomy",
        "epistemic_class": "fact",
        "temporal_scope": "current",
        "geographic_or_cosmic_scope": "Solar System",
        "truth_state": truth,
        "confidence": 0.99,
        "version": 1,
        "contradictions": [],
        "metadata": {"test": True},
    }


def _sample_source(uri: str = "https://example.invalid/source", h: str = "abc") -> dict[str, Any]:
    return {
        "source_uri": uri,
        "source_title": "Source",
        "publisher": "Test",
        "source_date": "2026-09-07",
        "retrieved_at": "2026-09-07T00:00:00Z",
        "source_hash": h,
        "source_kind": "test",
        "relation": "supports",
    }


def self_test_25x2() -> dict[str, Any]:
    checks: list[tuple[str, Any]] = []
    for round_no in (1, 2):
        with tempfile.TemporaryDirectory(prefix=f"eira_universe_library_r{round_no}_") as td:
            db = Path(td) / "library.sqlite3"
            with UniverseLibrary(db) as lib:
                a = _sample_seed()
                src = _sample_source()
                r1 = lib.archive_seed(a, [src])
                sid = r1.seed_id
                checks.extend([
                    (f"r{round_no}_01_schema", lib.schema_version() == 1),
                    (f"r{round_no}_02_db_exists", db.exists()),
                    (f"r{round_no}_03_inserted", r1.inserted is True),
                    (f"r{round_no}_04_seed_id_prefix", sid.startswith("seed_")),
                    (f"r{round_no}_05_seed_id_len", len(sid) == 69),
                    (f"r{round_no}_06_seed_count_one", lib.stats()["seeds"] == 1),
                    (f"r{round_no}_07_source_count_one", lib.stats()["sources"] == 1),
                    (f"r{round_no}_08_link_count_one", lib.stats()["seed_source_links"] == 1),
                ])
                r2 = lib.archive_seed(a, [src])
                checks.extend([
                    (f"r{round_no}_09_duplicate_not_inserted", r2.inserted is False),
                    (f"r{round_no}_10_duplicate_seed_count_still_one", lib.stats()["seeds"] == 1),
                    (f"r{round_no}_11_duplicate_source_count_still_one", lib.stats()["sources"] == 1),
                ])
                src2 = _sample_source("https://example.invalid/source2", "def")
                r3 = lib.archive_seed(a, [src2])
                checks.append((f"r{round_no}_12_new_provenance_merged", r3.merged_provenance == 1 and lib.stats()["sources"] == 2))
                got = lib.get_seed(sid)
                checks.extend([
                    (f"r{round_no}_13_lookup", got is not None and got["subject"] == "Earth"),
                    (f"r{round_no}_14_two_sources_attached", got is not None and len(got["sources"]) == 2),
                    (f"r{round_no}_15_search", bool(lib.search("orbits"))),
                    (f"r{round_no}_16_truth_filter", len(lib.search("Earth", truth_state="accepted")) == 1),
                    (f"r{round_no}_17_export_json", json.loads(lib.export_seed(sid))["seed_id"] == sid),
                    (f"r{round_no}_18_deterministic_id", canonical_seed_id(subject=" Earth ", claim="Earth  orbits the Sun", temporal_scope="current", epistemic_class="fact") == sid),
                ])
                b = _sample_seed("Sun", "The Sun is a star")
                rb = lib.archive_seed(b, [_sample_source("https://example.invalid/sun", "sun")])
                checks.append((f"r{round_no}_19_second_unique_seed", lib.stats()["seeds"] == 2))
                checks.append((f"r{round_no}_20_edge_insert", lib.add_edge(sid, "orbits", rb.seed_id) is True and lib.stats()["edges"] == 1))
                self_edge_failed = False
                try:
                    lib.add_edge(sid, "related_to", sid)
                except UniverseLibraryError:
                    self_edge_failed = True
                checks.append((f"r{round_no}_21_self_edge_rejected", self_edge_failed))
                c = _sample_seed("Earth", "Earth revolves around the Sun once per sidereal year")
                rc = lib.archive_seed(c, [_sample_source("https://example.invalid/new", "new")])
                lib.supersede(sid, rc.seed_id, "test")
                checks.append((f"r{round_no}_22_supersession", lib.get_seed(sid)["truth_state"] == "superseded" and lib.stats()["supersessions"] == 1))
                bad_truth = False
                try:
                    lib.archive_seed({**a, "truth_state": "certain"})
                except InvalidSeedError:
                    bad_truth = True
                checks.append((f"r{round_no}_23_invalid_truth_rejected", bad_truth))
                bad_conf = False
                try:
                    lib.archive_seed({**a, "confidence": 1.5})
                except InvalidSeedError:
                    bad_conf = True
                checks.append((f"r{round_no}_24_invalid_confidence_rejected", bad_conf))
                missing = False
                try:
                    lib.archive_seed({"subject": "x"})
                except InvalidSeedError:
                    missing = True
                checks.append((f"r{round_no}_25_missing_fields_rejected", missing))
    failed = [name for name, ok in checks if not ok]
    return {
        "schema": "eira2_universe_library_qualification_v1",
        "distinct_tests": 25,
        "rounds": 2,
        "clean_passes": sum(1 for _, ok in checks if ok),
        "total": len(checks),
        "failed": failed,
        "pass": len(checks) == 50 and not failed,
    }


if __name__ == "__main__":
    print(json.dumps(self_test_25x2(), indent=2, sort_keys=True))
'''

if __name__ == "__main__":
    # The transport executes this wrapper for qualification. It tests the exact
    # payload that Builder will deploy without mutating LIVE.
    ns: dict[str, object] = {"__name__": "eira2_universe_library_payload_test"}
    exec(compile(NEW, TARGET, "exec"), ns, ns)
    result = ns["self_test_25x2"]()
    print(__import__("json").dumps(result, indent=2, sort_keys=True))
    if not result.get("pass"):
        raise SystemExit(1)
