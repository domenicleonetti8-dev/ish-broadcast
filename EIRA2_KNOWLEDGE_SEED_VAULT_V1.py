from __future__ import annotations

"""EIRA2 Knowledge Seed Vault v1.

Additive document cold-storage/retrieval layer for Universe Library.
This is deliberately separate from UniverseLibrary's claim-level evidence seeds.
It compresses complete text documents into independently retrievable chunks,
keeps provenance and integrity metadata in SQLite, and never deletes source data.

Source material remains evidence, not automatically truth.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "eira2_knowledge_seed_vault_v1"
DEFAULT_CHUNK_BYTES = 384 * 1024
MIN_CHUNK_BYTES = 64 * 1024
MAX_CHUNK_BYTES = 2 * 1024 * 1024


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_component(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:120] or "unknown"


def _chunk_text_bytes(data: bytes, target: int) -> Iterable[bytes]:
    """Chunk UTF-8 bytes near paragraph boundaries without requiring whole-corpus scans."""
    if not MIN_CHUNK_BYTES <= target <= MAX_CHUNK_BYTES:
        raise ValueError("chunk_bytes_out_of_range")
    start = 0
    n = len(data)
    while start < n:
        hard_end = min(n, start + target)
        if hard_end == n:
            yield data[start:n]
            return
        search_lo = max(start + target // 2, start + 1)
        cut = data.rfind(b"\n\n", search_lo, min(n, hard_end + 64 * 1024))
        if cut < search_lo:
            cut = data.rfind(b"\n", search_lo, min(n, hard_end + 32 * 1024))
        if cut < search_lo:
            cut = hard_end
        else:
            cut += 2 if data[cut:cut + 2] == b"\n\n" else 1
        if cut <= start:
            cut = hard_end
        yield data[start:cut]
        start = cut


class KnowledgeSeedVault:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "knowledge_seed_index.sqlite3"
        self.db = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _init_schema(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents(
            document_seed_id TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL UNIQUE,
            source_bytes INTEGER NOT NULL,
            text_encoding TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            source_corpus TEXT NOT NULL,
            source_id TEXT NOT NULL DEFAULT '',
            source_uri TEXT NOT NULL DEFAULT '',
            publication_date TEXT NOT NULL DEFAULT '',
            rights TEXT NOT NULL DEFAULT '',
            dataset_version TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            chunk_count INTEGER NOT NULL,
            compressed_bytes INTEGER NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
            verified_at REAL,
            source_preservation_required INTEGER NOT NULL DEFAULT 1 CHECK(source_preservation_required=1),
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks(
            document_seed_id TEXT NOT NULL REFERENCES documents(document_seed_id) ON DELETE CASCADE,
            chunk_no INTEGER NOT NULL,
            uncompressed_bytes INTEGER NOT NULL,
            compressed_bytes INTEGER NOT NULL,
            chunk_sha256 TEXT NOT NULL,
            object_relpath TEXT NOT NULL,
            preview TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(document_seed_id, chunk_no)
        );
        CREATE INDEX IF NOT EXISTS idx_documents_corpus ON documents(source_corpus);
        CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(source_id);
        CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title);
        CREATE INDEX IF NOT EXISTS idx_chunks_seed ON chunks(document_seed_id, chunk_no);
        """)
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema',?)", (SCHEMA,))
        self.fts = True
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(document_seed_id UNINDEXED, chunk_no UNINDEXED, title, author, preview)")
        except sqlite3.OperationalError:
            self.fts = False

    def _object_path(self, seed_id: str, chunk_no: int) -> Path:
        digest = seed_id.removeprefix("docseed_")
        d = self.objects / digest[:2] / digest[2:4] / digest
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{chunk_no:06d}.zlib"

    def ingest_bytes(
        self,
        data: bytes,
        *,
        title: str = "",
        author: str = "",
        source_corpus: str,
        source_id: str = "",
        source_uri: str = "",
        publication_date: str = "",
        rights: str = "",
        dataset_version: str = "",
        retrieved_at: str = "",
        metadata: Mapping[str, Any] | None = None,
        encoding: str = "utf-8",
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    ) -> dict[str, Any]:
        if not source_corpus.strip():
            raise ValueError("source_corpus_required")
        source_hash = _sha256_bytes(data)
        seed_id = "docseed_" + source_hash
        existing = self.db.execute(
            "SELECT document_seed_id,verified,chunk_count,compressed_bytes FROM documents WHERE source_sha256=?",
            (source_hash,),
        ).fetchone()
        if existing:
            return {"schema": SCHEMA, "document_seed_id": seed_id, "inserted": False,
                    "verified": bool(existing["verified"]), "chunk_count": int(existing["chunk_count"]),
                    "compressed_bytes": int(existing["compressed_bytes"])}

        chunks = list(_chunk_text_bytes(data, chunk_bytes))
        staged: list[tuple[int, bytes, bytes, str, Path, str]] = []
        for i, raw in enumerate(chunks):
            comp = zlib.compress(raw, level=9)
            csha = _sha256_bytes(raw)
            path = self._object_path(seed_id, i)
            preview = raw[:4096].decode(encoding, errors="replace").replace("\x00", " ")
            staged.append((i, raw, comp, csha, path, preview))

        written: list[Path] = []
        try:
            for _, _, comp, _, path, _ in staged:
                tmp = path.with_suffix(path.suffix + ".tmp")
                with open(tmp, "wb") as fh:
                    fh.write(comp)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
                written.append(path)

            compressed_total = sum(len(x[2]) for x in staged)
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    """INSERT INTO documents(
                    document_seed_id,source_sha256,source_bytes,text_encoding,title,author,source_corpus,
                    source_id,source_uri,publication_date,rights,dataset_version,retrieved_at,metadata_json,
                    chunk_count,compressed_bytes,verified,source_preservation_required,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,1,?)""",
                    (seed_id, source_hash, len(data), encoding, title.strip(), author.strip(), source_corpus.strip(),
                     source_id.strip(), source_uri.strip(), publication_date.strip(), rights.strip(),
                     dataset_version.strip(), retrieved_at.strip(), _stable(dict(metadata or {})),
                     len(staged), compressed_total, time.time()),
                )
                for i, raw, comp, csha, path, preview in staged:
                    rel = str(path.relative_to(self.root))
                    self.db.execute(
                        "INSERT INTO chunks(document_seed_id,chunk_no,uncompressed_bytes,compressed_bytes,chunk_sha256,object_relpath,preview) VALUES(?,?,?,?,?,?,?)",
                        (seed_id, i, len(raw), len(comp), csha, rel, preview),
                    )
                    if self.fts:
                        self.db.execute(
                            "INSERT INTO chunk_fts(document_seed_id,chunk_no,title,author,preview) VALUES(?,?,?,?,?)",
                            (seed_id, i, title, author, preview),
                        )
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        except Exception:
            for p in written:
                try:
                    p.unlink()
                except OSError:
                    pass
            raise

        verification = self.verify(seed_id)
        return {"schema": SCHEMA, "document_seed_id": seed_id, "inserted": True,
                "chunk_count": len(staged), "source_bytes": len(data),
                "compressed_bytes": sum(len(x[2]) for x in staged), **verification}

    def ingest_text_file(self, path: str | Path, **metadata: Any) -> dict[str, Any]:
        p = Path(path)
        data = p.read_bytes()
        metadata.setdefault("title", p.stem)
        metadata.setdefault("source_id", str(p))
        return self.ingest_bytes(data, **metadata)

    def read_chunk(self, seed_id: str, chunk_no: int) -> bytes:
        row = self.db.execute(
            "SELECT object_relpath,chunk_sha256 FROM chunks WHERE document_seed_id=? AND chunk_no=?",
            (seed_id, int(chunk_no)),
        ).fetchone()
        if not row:
            raise KeyError("chunk_not_found")
        comp = (self.root / row["object_relpath"]).read_bytes()
        raw = zlib.decompress(comp)
        if _sha256_bytes(raw) != row["chunk_sha256"]:
            raise IOError("chunk_integrity_failure")
        return raw

    def reconstruct(self, seed_id: str) -> bytes:
        rows = self.db.execute(
            "SELECT chunk_no FROM chunks WHERE document_seed_id=? ORDER BY chunk_no", (seed_id,)
        ).fetchall()
        if not rows:
            raise KeyError("document_seed_not_found")
        return b"".join(self.read_chunk(seed_id, int(r["chunk_no"])) for r in rows)

    def verify(self, seed_id: str) -> dict[str, Any]:
        doc = self.db.execute(
            "SELECT source_sha256,source_bytes,chunk_count FROM documents WHERE document_seed_id=?", (seed_id,)
        ).fetchone()
        if not doc:
            raise KeyError("document_seed_not_found")
        h = hashlib.sha256()
        total = 0
        rows = self.db.execute(
            "SELECT chunk_no FROM chunks WHERE document_seed_id=? ORDER BY chunk_no", (seed_id,)
        ).fetchall()
        for r in rows:
            raw = self.read_chunk(seed_id, int(r["chunk_no"]))
            h.update(raw)
            total += len(raw)
        ok = h.hexdigest() == doc["source_sha256"] and total == int(doc["source_bytes"]) and len(rows) == int(doc["chunk_count"])
        self.db.execute("UPDATE documents SET verified=?,verified_at=? WHERE document_seed_id=?",
                        (1 if ok else 0, time.time() if ok else None, seed_id))
        return {"verified": ok, "reconstructed_sha256": h.hexdigest(), "reconstructed_bytes": total}

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 50))
        if self.fts:
            try:
                rows = self.db.execute(
                    """SELECT f.document_seed_id,f.chunk_no,d.title,d.author,d.source_corpus,d.source_id,
                              snippet(chunk_fts,4,'[',']',' … ',24) AS snippet
                       FROM chunk_fts f JOIN documents d ON d.document_seed_id=f.document_seed_id
                       WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?""",
                    (query, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        like = "%" + query.casefold() + "%"
        rows = self.db.execute(
            """SELECT c.document_seed_id,c.chunk_no,d.title,d.author,d.source_corpus,d.source_id,c.preview AS snippet
               FROM chunks c JOIN documents d ON d.document_seed_id=c.document_seed_id
               WHERE lower(d.title) LIKE ? OR lower(d.author) LIKE ? OR lower(c.preview) LIKE ? LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def retrieve(self, query: str, limit: int = 8, max_chars_per_chunk: int = 12000) -> list[dict[str, Any]]:
        hits = self.search(query, limit)
        out = []
        for hit in hits:
            raw = self.read_chunk(hit["document_seed_id"], int(hit["chunk_no"]))
            text = raw.decode("utf-8", errors="replace")[:max_chars_per_chunk]
            item = dict(hit)
            item["text"] = text
            out.append(item)
        return out

    def stats(self) -> dict[str, Any]:
        d = self.db.execute("SELECT COUNT(*) n,COALESCE(SUM(source_bytes),0) src,COALESCE(SUM(compressed_bytes),0) cmp,COALESCE(SUM(verified),0) ok FROM documents").fetchone()
        c = self.db.execute("SELECT COUNT(*) n FROM chunks").fetchone()
        return {"schema": SCHEMA, "documents": int(d["n"]), "chunks": int(c["n"]),
                "source_bytes": int(d["src"]), "compressed_bytes": int(d["cmp"]),
                "verified_documents": int(d["ok"]), "fts5": bool(self.fts),
                "raw_source_auto_delete": False}


def default_vault(root: Path) -> Path:
    return root / "eira_probe" / "universe_library" / "knowledge_seed_vault"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest")
    p.add_argument("path")
    p.add_argument("--corpus", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--author", default="")
    p.add_argument("--source-id", default="")
    p.add_argument("--source-uri", default="")
    p.add_argument("--rights", default="")
    p.add_argument("--dataset-version", default="")
    p.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    q = sub.add_parser("search")
    q.add_argument("query")
    q.add_argument("--limit", type=int, default=8)
    r = sub.add_parser("retrieve")
    r.add_argument("query")
    r.add_argument("--limit", type=int, default=8)
    v = sub.add_parser("verify")
    v.add_argument("seed_id")
    sub.add_parser("stats")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    with KnowledgeSeedVault(default_vault(root)) as vault:
        if args.cmd == "ingest":
            out = vault.ingest_text_file(args.path, source_corpus=args.corpus, title=args.title,
                                         author=args.author, source_id=args.source_id,
                                         source_uri=args.source_uri, rights=args.rights,
                                         dataset_version=args.dataset_version,
                                         chunk_bytes=args.chunk_bytes)
        elif args.cmd == "search":
            out = vault.search(args.query, args.limit)
        elif args.cmd == "retrieve":
            out = vault.retrieve(args.query, args.limit)
        elif args.cmd == "verify":
            out = vault.verify(args.seed_id)
        else:
            out = vault.stats()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
