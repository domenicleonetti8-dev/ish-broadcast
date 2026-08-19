from __future__ import annotations
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from .models import Edge, Node


class MeshStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._txn_depth = 0
        self._conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init()

    @contextmanager
    def _db(self):
        with self._lock:
            try:
                yield self._conn
                if self._txn_depth == 0:
                    self._conn.commit()
            except Exception:
                if self._txn_depth == 0:
                    self._conn.rollback()
                raise

    @contextmanager
    def transaction(self):
        with self._lock:
            outer = self._txn_depth == 0
            if outer:
                self._conn.execute("BEGIN IMMEDIATE")
            self._txn_depth += 1
            try:
                yield self
                self._txn_depth -= 1
                if outer:
                    self._conn.commit()
            except Exception:
                self._txn_depth -= 1
                if outer:
                    self._conn.rollback()
                raise

    def close(self):
        with self._lock:
            conn=getattr(self,'_conn',None)
            if conn is None:
                return
            try:
                conn.commit()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            self._conn=None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _init(self):
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes(
              node_id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              name TEXT NOT NULL,
              path TEXT NOT NULL DEFAULT '',
              state TEXT NOT NULL,
              aliases_json TEXT NOT NULL,
              capabilities_json TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              semantic_sha256 TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              first_seen REAL NOT NULL,
              last_seen REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);
            CREATE INDEX IF NOT EXISTS idx_nodes_state ON nodes(state);
            CREATE INDEX IF NOT EXISTS idx_nodes_content ON nodes(content_sha256);
            CREATE INDEX IF NOT EXISTS idx_nodes_semantic ON nodes(semantic_sha256);
            CREATE TABLE IF NOT EXISTS aliases(
              alias_norm TEXT NOT NULL,
              alias TEXT NOT NULL,
              node_id TEXT NOT NULL,
              UNIQUE(alias_norm,node_id),
              FOREIGN KEY(node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_alias_norm ON aliases(alias_norm);
            CREATE TABLE IF NOT EXISTS edges(
              edge_id TEXT PRIMARY KEY,
              source TEXT NOT NULL,
              target TEXT NOT NULL,
              relation TEXT NOT NULL,
              confidence REAL NOT NULL,
              evidence_json TEXT NOT NULL,
              first_seen REAL NOT NULL,
              last_seen REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
            CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
            CREATE TABLE IF NOT EXISTS scans(
              scan_id TEXT PRIMARY KEY,
              started REAL NOT NULL,
              finished REAL,
              root TEXT NOT NULL,
              nodes INTEGER NOT NULL DEFAULT 0,
              edges INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS lineage(
              old_node_id TEXT NOT NULL,
              new_node_id TEXT NOT NULL,
              relation TEXT NOT NULL,
              reason TEXT NOT NULL,
              seen REAL NOT NULL,
              UNIQUE(old_node_id,new_node_id,relation)
            );
            """)

    @staticmethod
    def _j(v):
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _norm_alias(value: str) -> str:
        import re
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    def upsert_node(self, node: Node, now: float | None = None):
        now = float(now or time.time())
        aliases = sorted({x.strip() for x in [node.name, node.path, *node.aliases, *node.capabilities] if str(x).strip()})
        with self._lock, self._db() as db:
            old = db.execute("SELECT first_seen FROM nodes WHERE node_id=?", (node.node_id,)).fetchone()
            first = float(old[0]) if old else now
            db.execute("""
                INSERT INTO nodes(node_id,kind,name,path,state,aliases_json,capabilities_json,content_sha256,semantic_sha256,metadata_json,first_seen,last_seen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET
                  kind=excluded.kind,name=excluded.name,path=excluded.path,state=excluded.state,
                  aliases_json=excluded.aliases_json,capabilities_json=excluded.capabilities_json,
                  content_sha256=excluded.content_sha256,semantic_sha256=excluded.semantic_sha256,
                  metadata_json=excluded.metadata_json,last_seen=excluded.last_seen
            """, (node.node_id,node.kind,node.name,node.path,node.state,self._j(aliases),self._j(sorted(set(node.capabilities))),node.content_sha256,node.semantic_sha256,self._j(node.metadata),first,now))
            db.execute("DELETE FROM aliases WHERE node_id=?", (node.node_id,))
            for alias in aliases:
                n = self._norm_alias(alias)
                if n:
                    db.execute("INSERT OR IGNORE INTO aliases(alias_norm,alias,node_id) VALUES(?,?,?)", (n,alias,node.node_id))

    def upsert_edge(self, edge: Edge, now: float | None = None):
        now = float(now or time.time())
        with self._lock, self._db() as db:
            old = db.execute("SELECT first_seen FROM edges WHERE edge_id=?", (edge.edge_id,)).fetchone()
            first = float(old[0]) if old else now
            db.execute("""
                INSERT INTO edges(edge_id,source,target,relation,confidence,evidence_json,first_seen,last_seen)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(edge_id) DO UPDATE SET confidence=excluded.confidence,evidence_json=excluded.evidence_json,last_seen=excluded.last_seen
            """, (edge.edge_id,edge.source,edge.target,edge.relation,float(edge.confidence),self._j(edge.evidence),first,now))

    def begin_scan(self, scan_id: str, root: str, started: float):
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO scans(scan_id,started,root) VALUES(?,?,?)", (scan_id,started,root))

    def finish_scan(self, scan_id: str, *, finished: float, nodes: int, edges: int):
        with self._db() as db:
            db.execute("UPDATE scans SET finished=?,nodes=?,edges=? WHERE scan_id=?", (finished,nodes,edges,scan_id))

    def mark_unseen_missing(self, scan_started: float, root_prefix: str):
        with self._db() as db:
            if root_prefix:
                db.execute("UPDATE nodes SET state='missing' WHERE state='active' AND last_seen < ? AND (path=? OR path LIKE ?)", (scan_started,root_prefix,root_prefix + "/%"))
            else:
                db.execute("UPDATE nodes SET state='missing' WHERE state='active' AND last_seen < ?", (scan_started,))

    def node(self, node_id: str):
        with self._db() as db:
            row = db.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    def nodes(self, *, state: str | None = None):
        with self._db() as db:
            if state:
                rows = db.execute("SELECT * FROM nodes WHERE state=? ORDER BY path,node_id", (state,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM nodes ORDER BY path,node_id").fetchall()
        return [dict(x) for x in rows]

    def edges(self):
        with self._db() as db:
            rows = db.execute("SELECT * FROM edges ORDER BY relation,source,target").fetchall()
        return [dict(x) for x in rows]

    def aliases(self, query_norm: str, limit: int = 100):
        like = "%" + query_norm + "%"
        with self._db() as db:
            rows = db.execute("""
                SELECT n.*,a.alias,a.alias_norm FROM aliases a JOIN nodes n USING(node_id)
                WHERE a.alias_norm=? OR a.alias_norm LIKE ? ORDER BY CASE WHEN a.alias_norm=? THEN 0 ELSE 1 END, length(a.alias_norm),n.path LIMIT ?
            """, (query_norm,like,query_norm,int(limit))).fetchall()
        return [dict(x) for x in rows]

    def by_hash(self, digest: str, *, semantic: bool = False):
        col = "semantic_sha256" if semantic else "content_sha256"
        with self._db() as db:
            rows = db.execute(f"SELECT * FROM nodes WHERE {col}=? AND ?!='' ORDER BY path", (digest,digest)).fetchall()
        return [dict(x) for x in rows]

    def neighborhood(self, node_ids: Iterable[str], depth: int = 1, limit: int = 500):
        frontier = set(node_ids)
        seen = set(frontier)
        found = []
        with self._db() as db:
            for _ in range(max(0,int(depth))):
                if not frontier or len(found) >= limit:
                    break
                q = ",".join("?" for _ in frontier)
                rows = db.execute(f"SELECT * FROM edges WHERE source IN ({q}) OR target IN ({q}) LIMIT ?", (*frontier,*frontier,limit-len(found))).fetchall()
                nxt=set()
                for r in rows:
                    d=dict(r);found.append(d)
                    for k in (d['source'],d['target']):
                        if k not in seen:
                            seen.add(k);nxt.add(k)
                frontier=nxt
        return found, seen

    def lineage(self, old_id: str, new_id: str, relation: str, reason: str):
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO lineage(old_node_id,new_node_id,relation,reason,seen) VALUES(?,?,?,?,?)", (old_id,new_id,relation,reason,time.time()))

    def counts(self):
        with self._db() as db:
            n=db.execute("SELECT count(*) FROM nodes").fetchone()[0]
            active=db.execute("SELECT count(*) FROM nodes WHERE state='active'").fetchone()[0]
            unresolved=db.execute("SELECT count(*) FROM nodes WHERE state='unresolved'").fetchone()[0]
            missing=db.execute("SELECT count(*) FROM nodes WHERE state='missing'").fetchone()[0]
            e=db.execute("SELECT count(*) FROM edges").fetchone()[0]
        return {"nodes":n,"active":active,"unresolved":unresolved,"missing":missing,"edges":e}
