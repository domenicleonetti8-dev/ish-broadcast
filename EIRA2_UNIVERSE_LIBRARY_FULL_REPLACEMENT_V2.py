from __future__ import annotations

TARGET = "eira2/evidence/universe_library.py"

NEW = r'''from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 2
TRUTH_STATES = {"candidate", "accepted", "contested", "superseded", "rejected", "unknown"}
EPISTEMIC_CLASSES = {
    "fact", "measurement", "observation", "historical_record", "derived_result",
    "scientific_model", "consensus", "hypothesis", "procedure", "equation", "fiction_culture"
}

class UniverseLibraryError(RuntimeError): pass
class InvalidSeedError(UniverseLibraryError): pass
class DuplicateConflictError(UniverseLibraryError): pass

class ArchiveResult:
    __slots__ = ("seed_id", "inserted", "merged_provenance")
    def __init__(self, seed_id: str, inserted: bool, merged_provenance: int):
        self.seed_id = seed_id; self.inserted = bool(inserted); self.merged_provenance = int(merged_provenance)
    def __repr__(self):
        return f"ArchiveResult(seed_id={self.seed_id!r}, inserted={self.inserted!r}, merged_provenance={self.merged_provenance!r})"


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"\s+", " ", value)

def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def canonical_seed_id(*, subject: str, claim: str, temporal_scope: str, epistemic_class: str) -> str:
    payload = {"subject": _norm(subject), "claim": _norm(claim), "temporal_scope": _norm(temporal_scope), "epistemic_class": _norm(epistemic_class)}
    return "seed_" + _sha256_text(_stable_json(payload))

def content_hash(seed: Mapping[str, Any]) -> str:
    payload = {k: seed[k] for k in sorted(seed) if k not in {"source_refs", "sources", "relationships", "seed_hash"}}
    return _sha256_text(_stable_json(payload))

def _require_text(seed: Mapping[str, Any], key: str) -> str:
    v = str(seed.get(key, "")).strip()
    if not v: raise InvalidSeedError(f"missing_or_empty:{key}")
    return v

def validate_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    subject = _require_text(seed, "subject"); claim = _require_text(seed, "canonical_claim"); domain = _require_text(seed, "domain")
    epistemic = _require_text(seed, "epistemic_class"); temporal = _require_text(seed, "temporal_scope"); truth = _require_text(seed, "truth_state")
    if epistemic not in EPISTEMIC_CLASSES: raise InvalidSeedError("invalid_epistemic_class")
    if truth not in TRUTH_STATES: raise InvalidSeedError("invalid_truth_state")
    try: confidence = float(seed.get("confidence"))
    except Exception as exc: raise InvalidSeedError("invalid_confidence") from exc
    if not 0.0 <= confidence <= 1.0: raise InvalidSeedError("confidence_out_of_range")
    version = int(seed.get("version", 1))
    if version < 1: raise InvalidSeedError("invalid_version")
    out = {
        "seed_id": canonical_seed_id(subject=subject, claim=claim, temporal_scope=temporal, epistemic_class=epistemic),
        "subject": subject, "canonical_claim": claim, "domain": domain, "epistemic_class": epistemic,
        "temporal_scope": temporal, "geographic_or_cosmic_scope": str(seed.get("geographic_or_cosmic_scope", "unspecified")).strip() or "unspecified",
        "truth_state": truth, "confidence": confidence, "version": version,
        "contradictions": list(seed.get("contradictions") or []), "metadata": dict(seed.get("metadata") or {})
    }
    out["seed_hash"] = content_hash(out)
    return out

class UniverseLibrary:
    """Storage/retrieval archive only. It never decides truth and never speaks for Eira."""
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None); self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON"); self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def _init_schema(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seeds(
          seed_id TEXT PRIMARY KEY, seed_hash TEXT NOT NULL, subject TEXT NOT NULL, normalized_subject TEXT NOT NULL,
          canonical_claim TEXT NOT NULL, normalized_claim TEXT NOT NULL, domain TEXT NOT NULL, epistemic_class TEXT NOT NULL,
          temporal_scope TEXT NOT NULL, scope TEXT NOT NULL, truth_state TEXT NOT NULL,
          confidence REAL NOT NULL CHECK(confidence>=0 AND confidence<=1), version INTEGER NOT NULL CHECK(version>=1),
          contradictions_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(normalized_subject,normalized_claim,temporal_scope,epistemic_class));
        CREATE TABLE IF NOT EXISTS sources(
          source_id TEXT PRIMARY KEY, source_uri TEXT NOT NULL, source_title TEXT NOT NULL DEFAULT '', publisher TEXT NOT NULL DEFAULT '',
          source_date TEXT NOT NULL DEFAULT '', retrieved_at TEXT NOT NULL, source_hash TEXT NOT NULL, source_kind TEXT NOT NULL DEFAULT 'unknown',
          metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source_hash,source_uri));
        CREATE TABLE IF NOT EXISTS seed_sources(seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,relation TEXT NOT NULL DEFAULT 'supports',PRIMARY KEY(seed_id,source_id,relation));
        CREATE TABLE IF NOT EXISTS edges(from_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,relation TEXT NOT NULL,to_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,metadata_json TEXT NOT NULL DEFAULT '{}',PRIMARY KEY(from_seed_id,relation,to_seed_id));
        CREATE TABLE IF NOT EXISTS supersession(old_seed_id TEXT PRIMARY KEY REFERENCES seeds(seed_id) ON DELETE CASCADE,new_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,CHECK(old_seed_id<>new_seed_id));
        CREATE INDEX IF NOT EXISTS idx_seeds_domain ON seeds(domain); CREATE INDEX IF NOT EXISTS idx_seeds_truth ON seeds(truth_state);
        CREATE INDEX IF NOT EXISTS idx_seeds_subject ON seeds(normalized_subject); CREATE INDEX IF NOT EXISTS idx_seeds_temporal ON seeds(temporal_scope);
        CREATE INDEX IF NOT EXISTS idx_sources_uri ON sources(source_uri); CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_seed_id);
        ''')
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS seed_fts USING fts5(seed_id UNINDEXED,subject,canonical_claim,domain,content='')")
            self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts5','1')")
        except sqlite3.OperationalError:
            self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts5','0')")
    def schema_version(self): return int(self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
    def _source(self, source: Mapping[str, Any]):
        uri = str(source.get("source_uri", "")).strip(); retrieved = str(source.get("retrieved_at", "")).strip(); sh = str(source.get("source_hash", "")).strip()
        if not uri or not retrieved or not sh: raise InvalidSeedError("source_requires_uri_retrieved_at_hash")
        sid = "src_" + _sha256_text(_stable_json({"uri": uri, "hash": sh}))
        return sid, {"source_id":sid,"source_uri":uri,"source_title":str(source.get("source_title","")).strip(),"publisher":str(source.get("publisher","")).strip(),"source_date":str(source.get("source_date","")).strip(),"retrieved_at":retrieved,"source_hash":sh,"source_kind":str(source.get("source_kind","unknown")).strip() or "unknown","metadata_json":_stable_json(dict(source.get("metadata") or {}))}
    def archive_seed(self, seed: Mapping[str, Any], sources: Sequence[Mapping[str, Any]] = ()):
        n = validate_seed(seed); sid = n["seed_id"]; merged = 0; self.db.execute("BEGIN IMMEDIATE")
        try:
            ex = self.db.execute("SELECT * FROM seeds WHERE seed_id=?",(sid,)).fetchone(); inserted = ex is None
            if ex is None:
                self.db.execute("INSERT INTO seeds(seed_id,seed_hash,subject,normalized_subject,canonical_claim,normalized_claim,domain,epistemic_class,temporal_scope,scope,truth_state,confidence,version,contradictions_json,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,n["seed_hash"],n["subject"],_norm(n["subject"]),n["canonical_claim"],_norm(n["canonical_claim"]),n["domain"],n["epistemic_class"],n["temporal_scope"],n["geographic_or_cosmic_scope"],n["truth_state"],n["confidence"],n["version"],_stable_json(n["contradictions"]),_stable_json(n["metadata"])))
                try: self.db.execute("INSERT INTO seed_fts(seed_id,subject,canonical_claim,domain) VALUES(?,?,?,?)",(sid,n["subject"],n["canonical_claim"],n["domain"]))
                except sqlite3.OperationalError: pass
            else:
                if (ex["normalized_subject"],ex["normalized_claim"],ex["temporal_scope"],ex["epistemic_class"]) != (_norm(n["subject"]),_norm(n["canonical_claim"]),n["temporal_scope"],n["epistemic_class"]): raise DuplicateConflictError("canonical_seed_identity_conflict")
                self.db.execute("UPDATE seeds SET truth_state=?,confidence=?,version=MAX(version,?),contradictions_json=?,metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE seed_id=?",(n["truth_state"],n["confidence"],n["version"],_stable_json(n["contradictions"]),_stable_json(n["metadata"]),sid))
            for source in sources:
                src_id,row=self._source(source); self.db.execute("INSERT OR IGNORE INTO sources(source_id,source_uri,source_title,publisher,source_date,retrieved_at,source_hash,source_kind,metadata_json) VALUES(:source_id,:source_uri,:source_title,:publisher,:source_date,:retrieved_at,:source_hash,:source_kind,:metadata_json)",row)
                before=self.db.total_changes; self.db.execute("INSERT OR IGNORE INTO seed_sources(seed_id,source_id,relation) VALUES(?,?,?)",(sid,src_id,str(source.get("relation","supports")).strip() or "supports")); merged += int(self.db.total_changes>before)
            self.db.execute("COMMIT"); return ArchiveResult(sid,inserted,merged)
        except Exception: self.db.execute("ROLLBACK"); raise
    def get_seed(self, seed_id: str):
        row=self.db.execute("SELECT * FROM seeds WHERE seed_id=?",(seed_id,)).fetchone()
        if row is None:return None
        out=dict(row); out["contradictions"]=json.loads(out.pop("contradictions_json")); out["metadata"]=json.loads(out.pop("metadata_json")); out["sources"]=[dict(r) for r in self.db.execute("SELECT s.*,ss.relation FROM sources s JOIN seed_sources ss ON ss.source_id=s.source_id WHERE ss.seed_id=? ORDER BY s.source_id",(seed_id,))]; return out
    def add_edge(self, a: str, relation: str, b: str, metadata: Mapping[str,Any]|None=None):
        if a==b: raise UniverseLibraryError("self_edge_forbidden")
        relation=str(relation).strip();
        if not relation: raise UniverseLibraryError("empty_relation")
        before=self.db.total_changes; self.db.execute("INSERT OR IGNORE INTO edges(from_seed_id,relation,to_seed_id,metadata_json) VALUES(?,?,?,?)",(a,relation,b,_stable_json(dict(metadata or {})))); return self.db.total_changes>before
    def supersede(self, old: str, new: str, reason: str=""):
        if old==new: raise UniverseLibraryError("self_supersession_forbidden")
        self.db.execute("BEGIN IMMEDIATE")
        try:self.db.execute("INSERT OR REPLACE INTO supersession(old_seed_id,new_seed_id,reason) VALUES(?,?,?)",(old,new,str(reason))); self.db.execute("UPDATE seeds SET truth_state='superseded',updated_at=CURRENT_TIMESTAMP WHERE seed_id=?",(old,)); self.db.execute("COMMIT")
        except Exception:self.db.execute("ROLLBACK"); raise
    def search(self, query: str, *, limit: int=25, truth_state: str|None=None):
        query=str(query).strip(); limit=max(1,min(int(limit),500))
        if not query:return []
        if truth_state is not None and truth_state not in TRUTH_STATES: raise UniverseLibraryError("invalid_truth_filter")
        like=f"%{_norm(query)}%"; params=[like,like,like]; extra=""
        if truth_state is not None: extra=" AND truth_state=?"; params.append(truth_state)
        params.append(limit)
        return [dict(r) for r in self.db.execute(f"SELECT seed_id,subject,canonical_claim,domain,epistemic_class,temporal_scope,scope,truth_state,confidence,version FROM seeds WHERE (normalized_subject LIKE ? OR normalized_claim LIKE ? OR lower(domain) LIKE ?){extra} ORDER BY confidence DESC,seed_id LIMIT ?",params)]
    def timeline(self, *, limit: int=100): return [dict(r) for r in self.db.execute("SELECT seed_id,subject,canonical_claim,temporal_scope,truth_state,confidence FROM seeds ORDER BY temporal_scope,seed_id LIMIT ?",(max(1,min(int(limit),5000)),))]
    def stats(self):
        c=lambda t:int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        return {"schema_version":self.schema_version(),"seeds":c("seeds"),"sources":c("sources"),"seed_source_links":c("seed_sources"),"edges":c("edges"),"supersessions":c("supersession"),"by_domain":{r[0]:int(r[1]) for r in self.db.execute("SELECT domain,COUNT(*) FROM seeds GROUP BY domain ORDER BY domain")},"by_truth_state":{r[0]:int(r[1]) for r in self.db.execute("SELECT truth_state,COUNT(*) FROM seeds GROUP BY truth_state ORDER BY truth_state")}}
    def export_seed(self, seed_id: str):
        seed=self.get_seed(seed_id)
        if seed is None: raise UniverseLibraryError("seed_not_found")
        return _stable_json(seed)

def _sample_seed(subject="Earth", claim="Earth orbits the Sun", truth="accepted"):
    return {"subject":subject,"canonical_claim":claim,"domain":"astronomy","epistemic_class":"fact","temporal_scope":"current","geographic_or_cosmic_scope":"Solar System","truth_state":truth,"confidence":0.99,"version":1,"contradictions":[],"metadata":{"test":True}}
def _sample_source(uri="https://example.invalid/source",h="abc"):
    return {"source_uri":uri,"source_title":"Source","publisher":"Test","source_date":"2026-09-07","retrieved_at":"2026-09-07T00:00:00Z","source_hash":h,"source_kind":"test","relation":"supports"}
def self_test_25x2():
    checks=[]
    for r in (1,2):
        with tempfile.TemporaryDirectory(prefix=f"eira_universe_library_r{r}_") as td:
            db=Path(td)/"library.sqlite3"
            with UniverseLibrary(db) as lib:
                a=_sample_seed(); s=_sample_source(); x=lib.archive_seed(a,[s]); sid=x.seed_id
                checks += [(f"r{r}_01_schema",lib.schema_version()==2),(f"r{r}_02_db",db.exists()),(f"r{r}_03_insert",x.inserted),(f"r{r}_04_id_prefix",sid.startswith("seed_")),(f"r{r}_05_id_len",len(sid)==69),(f"r{r}_06_seed_count",lib.stats()["seeds"]==1),(f"r{r}_07_source_count",lib.stats()["sources"]==1),(f"r{r}_08_link_count",lib.stats()["seed_source_links"]==1)]
                y=lib.archive_seed(a,[s]); checks += [(f"r{r}_09_dedup",not y.inserted),(f"r{r}_10_seed_still_one",lib.stats()["seeds"]==1),(f"r{r}_11_source_still_one",lib.stats()["sources"]==1)]
                z=lib.archive_seed(a,[_sample_source("https://example.invalid/source2","def")]); checks.append((f"r{r}_12_provenance_merge",z.merged_provenance==1 and lib.stats()["sources"]==2))
                got=lib.get_seed(sid); checks += [(f"r{r}_13_lookup",got and got["subject"]=="Earth"),(f"r{r}_14_sources",got and len(got["sources"])==2),(f"r{r}_15_search",bool(lib.search("orbits"))),(f"r{r}_16_truth_filter",len(lib.search("Earth",truth_state="accepted"))==1),(f"r{r}_17_export",json.loads(lib.export_seed(sid))["seed_id"]==sid),(f"r{r}_18_deterministic",canonical_seed_id(subject=" Earth ",claim="Earth  orbits the Sun",temporal_scope="current",epistemic_class="fact")==sid)]
                rb=lib.archive_seed(_sample_seed("Sun","The Sun is a star"),[_sample_source("https://example.invalid/sun","sun")]); checks.append((f"r{r}_19_second_seed",lib.stats()["seeds"]==2)); checks.append((f"r{r}_20_edge",lib.add_edge(sid,"orbits",rb.seed_id) and lib.stats()["edges"]==1))
                ok=False
                try:lib.add_edge(sid,"related_to",sid)
                except UniverseLibraryError:ok=True
                checks.append((f"r{r}_21_self_edge",ok)); rc=lib.archive_seed(_sample_seed("Earth","Earth revolves around the Sun once per sidereal year"),[_sample_source("https://example.invalid/new","new")]); lib.supersede(sid,rc.seed_id,"test"); checks.append((f"r{r}_22_supersede",lib.get_seed(sid)["truth_state"]=="superseded" and lib.stats()["supersessions"]==1))
                ok=False
                try:lib.archive_seed({**a,"truth_state":"certain"})
                except InvalidSeedError:ok=True
                checks.append((f"r{r}_23_bad_truth",ok)); ok=False
                try:lib.archive_seed({**a,"confidence":1.5})
                except InvalidSeedError:ok=True
                checks.append((f"r{r}_24_bad_conf",ok)); ok=False
                try:lib.archive_seed({"subject":"x"})
                except InvalidSeedError:ok=True
                checks.append((f"r{r}_25_missing",ok))
    failed=[n for n,ok in checks if not ok]
    return {"schema":"eira2_universe_library_qualification_v2","distinct_tests":25,"rounds":2,"clean_passes":sum(1 for _,ok in checks if ok),"total":len(checks),"failed":failed,"pass":len(checks)==50 and not failed}
'''

if __name__ == "__main__":
    ns = {"__name__": "eira2_universe_library_payload_test"}
    exec(compile(NEW, TARGET, "exec"), ns, ns)
    result = ns["self_test_25x2"]()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result.get("pass"):
        raise SystemExit(1)
