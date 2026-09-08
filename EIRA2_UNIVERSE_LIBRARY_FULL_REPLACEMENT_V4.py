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

SCHEMA_VERSION = 4
TRUTH_STATES = {"candidate","accepted","contested","superseded","rejected","unknown"}
EPISTEMIC_CLASSES = {"fact","measurement","observation","historical_record","derived_result","scientific_model","consensus","hypothesis","procedure","equation","fiction_culture"}
SOURCE_AUTHORITY = {"primary","official","peer_reviewed","standards_body","academic","curated_reference","reputable_news","secondary","unknown"}
FRESHNESS_CLASSES = {"static","slow","moderate","fast","realtime"}
RELATIONS = {"is_a","part_of","causes","caused_by","precedes","follows","supports","contradicts","derived_from","measured_by","located_in","orbits","evolved_from","related_to","supersedes"}

DOMAIN_PREFIXES = (
    "universe","astronomy","astrophysics","cosmology","solar_system","earth_history","geology","oceanography","climate",
    "physics","chemistry","biology","botany","medicine","mathematics","engineering","architecture","rocket_physics",
    "computer_science","agriculture","history","anthropology","archaeology","technology","innovation","culture_fiction"
)

class UniverseLibraryError(RuntimeError): pass
class InvalidSeedError(UniverseLibraryError): pass
class DuplicateConflictError(UniverseLibraryError): pass

class ArchiveResult:
    __slots__=("seed_id","inserted","merged_provenance")
    def __init__(self,seed_id:str,inserted:bool,merged_provenance:int):
        self.seed_id=seed_id; self.inserted=bool(inserted); self.merged_provenance=int(merged_provenance)

def _norm(v:Any)->str:
    return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",str(v or "")).strip().casefold())
def _stable(v:Any)->str:
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _sha(v:str)->str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()
def _req(m:Mapping[str,Any],k:str)->str:
    v=str(m.get(k,"")).strip()
    if not v: raise InvalidSeedError(f"missing_or_empty:{k}")
    return v

def semantic_key(subject:str,claim:str,temporal_scope:str,epistemic_class:str)->str:
    # Deterministic canonical identity. True semantic equivalence beyond normalization
    # must be decided upstream by Eira's evidence/reconciliation layer, never guessed here.
    return _sha(_stable({"subject":_norm(subject),"claim":_norm(claim),"temporal_scope":_norm(temporal_scope),"epistemic_class":_norm(epistemic_class)}))
def canonical_seed_id(*,subject:str,claim:str,temporal_scope:str,epistemic_class:str)->str:
    return "seed_"+semantic_key(subject,claim,temporal_scope,epistemic_class)
def content_hash(seed:Mapping[str,Any])->str:
    excluded={"sources","source_refs","relationships","seed_hash","created_at","updated_at"}
    return _sha(_stable({k:seed[k] for k in sorted(seed) if k not in excluded}))

def validate_seed(seed:Mapping[str,Any])->dict[str,Any]:
    subject=_req(seed,"subject"); claim=_req(seed,"canonical_claim"); domain=_req(seed,"domain")
    ep=_req(seed,"epistemic_class"); temporal=_req(seed,"temporal_scope"); truth=_req(seed,"truth_state")
    if ep not in EPISTEMIC_CLASSES: raise InvalidSeedError("invalid_epistemic_class")
    if truth not in TRUTH_STATES: raise InvalidSeedError("invalid_truth_state")
    if not any(domain==p or domain.startswith(p+".") for p in DOMAIN_PREFIXES): raise InvalidSeedError("invalid_domain")
    try: confidence=float(seed.get("confidence"))
    except Exception as exc: raise InvalidSeedError("invalid_confidence") from exc
    if not 0.0<=confidence<=1.0: raise InvalidSeedError("confidence_out_of_range")
    version=int(seed.get("version",1))
    if version<1: raise InvalidSeedError("invalid_version")
    freshness=str(seed.get("freshness_class","static")).strip()
    if freshness not in FRESHNESS_CLASSES: raise InvalidSeedError("invalid_freshness_class")
    out={
        "seed_id":canonical_seed_id(subject=subject,claim=claim,temporal_scope=temporal,epistemic_class=ep),
        "semantic_key":semantic_key(subject,claim,temporal,ep),
        "subject":subject,
        "canonical_claim":claim,
        "domain":domain,
        "epistemic_class":ep,
        "temporal_scope":temporal,
        "valid_from":str(seed.get("valid_from","")).strip(),
        "valid_to":str(seed.get("valid_to","")).strip(),
        "geographic_or_cosmic_scope":str(seed.get("geographic_or_cosmic_scope","unspecified")).strip() or "unspecified",
        "truth_state":truth,
        "confidence":confidence,
        "version":version,
        "freshness_class":freshness,
        "revalidate_after":str(seed.get("revalidate_after","")).strip(),
        "truth_receipt":dict(seed.get("truth_receipt") or {}),
        "contradictions":list(seed.get("contradictions") or []),
        "metadata":dict(seed.get("metadata") or {}),
    }
    out["seed_hash"]=content_hash(out)
    return out

class UniverseLibrary:
    """Storage/retrieval archive beneath Eira's evidence authority.

    It stores, deduplicates, versions, links, schedules revalidation, and regrows context.
    It does NOT independently decide truth, browse the web, call a model, or speak for Eira.
    """
    def __init__(self,db_path:str|Path):
        self.db_path=Path(db_path); self.db_path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(self.db_path),timeout=30,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON"); self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self,*_): self.close()
    def _init_schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seeds(
            seed_id TEXT PRIMARY KEY,
            semantic_key TEXT NOT NULL UNIQUE,
            seed_hash TEXT NOT NULL,
            subject TEXT NOT NULL,
            normalized_subject TEXT NOT NULL,
            canonical_claim TEXT NOT NULL,
            normalized_claim TEXT NOT NULL,
            domain TEXT NOT NULL,
            epistemic_class TEXT NOT NULL,
            temporal_scope TEXT NOT NULL,
            valid_from TEXT NOT NULL DEFAULT '',
            valid_to TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL,
            truth_state TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence>=0 AND confidence<=1),
            version INTEGER NOT NULL CHECK(version>=1),
            freshness_class TEXT NOT NULL,
            revalidate_after TEXT NOT NULL DEFAULT '',
            truth_receipt_json TEXT NOT NULL DEFAULT '{}',
            contradictions_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(normalized_subject,normalized_claim,temporal_scope,epistemic_class)
        );
        CREATE TABLE IF NOT EXISTS sources(
            source_id TEXT PRIMARY KEY,
            source_uri TEXT NOT NULL,
            source_title TEXT NOT NULL DEFAULT '',
            publisher TEXT NOT NULL DEFAULT '',
            jurisdiction TEXT NOT NULL DEFAULT '',
            source_date TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'unknown',
            authority_class TEXT NOT NULL DEFAULT 'unknown',
            freshness_class TEXT NOT NULL DEFAULT 'static',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(source_hash,source_uri)
        );
        CREATE TABLE IF NOT EXISTS seed_sources(
            seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
            source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
            relation TEXT NOT NULL DEFAULT 'supports',
            PRIMARY KEY(seed_id,source_id,relation)
        );
        CREATE TABLE IF NOT EXISTS edges(
            from_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            to_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(from_seed_id,relation,to_seed_id)
        );
        CREATE TABLE IF NOT EXISTS lineage(
            predecessor_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
            successor_seed_id TEXT NOT NULL REFERENCES seeds(seed_id) ON DELETE CASCADE,
            relation TEXT NOT NULL DEFAULT 'supersedes',
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(predecessor_seed_id,successor_seed_id,relation),
            CHECK(predecessor_seed_id<>successor_seed_id)
        );
        CREATE TABLE IF NOT EXISTS revalidation_queue(
            seed_id TEXT PRIMARY KEY REFERENCES seeds(seed_id) ON DELETE CASCADE,
            due_at TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 50 CHECK(priority>=0 AND priority<=100),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_seed_domain ON seeds(domain);
        CREATE INDEX IF NOT EXISTS idx_seed_truth ON seeds(truth_state);
        CREATE INDEX IF NOT EXISTS idx_seed_subject ON seeds(normalized_subject);
        CREATE INDEX IF NOT EXISTS idx_seed_temporal ON seeds(temporal_scope,valid_from,valid_to);
        CREATE INDEX IF NOT EXISTS idx_seed_revalidate ON seeds(revalidate_after);
        CREATE INDEX IF NOT EXISTS idx_source_uri ON sources(source_uri);
        CREATE INDEX IF NOT EXISTS idx_source_authority ON sources(authority_class);
        CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_seed_id);
        CREATE INDEX IF NOT EXISTS idx_revalidation_due ON revalidation_queue(due_at,priority);
        """)
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",(str(SCHEMA_VERSION),))
    def schema_version(self): return int(self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
    def _source(self,s:Mapping[str,Any]):
        uri=str(s.get("source_uri","")).strip(); retrieved=str(s.get("retrieved_at","")).strip(); sh=str(s.get("source_hash","")).strip()
        if not uri or not retrieved or not sh: raise InvalidSeedError("source_requires_uri_retrieved_at_hash")
        authority=str(s.get("authority_class","unknown")).strip(); freshness=str(s.get("freshness_class","static")).strip()
        if authority not in SOURCE_AUTHORITY: raise InvalidSeedError("invalid_source_authority")
        if freshness not in FRESHNESS_CLASSES: raise InvalidSeedError("invalid_source_freshness")
        sid="src_"+_sha(_stable({"uri":uri,"hash":sh}))
        row={"source_id":sid,"source_uri":uri,"source_title":str(s.get("source_title","")).strip(),"publisher":str(s.get("publisher","")).strip(),"jurisdiction":str(s.get("jurisdiction","")).strip(),"source_date":str(s.get("source_date","")).strip(),"retrieved_at":retrieved,"source_hash":sh,"source_kind":str(s.get("source_kind","unknown")).strip() or "unknown","authority_class":authority,"freshness_class":freshness,"metadata_json":_stable(dict(s.get("metadata") or {}))}
        return sid,row
    def archive_seed(self,seed:Mapping[str,Any],sources:Sequence[Mapping[str,Any]]=()):
        n=validate_seed(seed); sid=n["seed_id"]; merged=0; self.db.execute("BEGIN IMMEDIATE")
        try:
            ex=self.db.execute("SELECT * FROM seeds WHERE semantic_key=?",(n["semantic_key"],)).fetchone(); inserted=ex is None
            if ex is None:
                self.db.execute("INSERT INTO seeds(seed_id,semantic_key,seed_hash,subject,normalized_subject,canonical_claim,normalized_claim,domain,epistemic_class,temporal_scope,valid_from,valid_to,scope,truth_state,confidence,version,freshness_class,revalidate_after,truth_receipt_json,contradictions_json,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,n["semantic_key"],n["seed_hash"],n["subject"],_norm(n["subject"]),n["canonical_claim"],_norm(n["canonical_claim"]),n["domain"],n["epistemic_class"],n["temporal_scope"],n["valid_from"],n["valid_to"],n["geographic_or_cosmic_scope"],n["truth_state"],n["confidence"],n["version"],n["freshness_class"],n["revalidate_after"],_stable(n["truth_receipt"]),_stable(n["contradictions"]),_stable(n["metadata"])))
            else:
                sid=str(ex["seed_id"])
                immutable=(ex["normalized_subject"],ex["normalized_claim"],ex["temporal_scope"],ex["epistemic_class"])
                proposed=(_norm(n["subject"]),_norm(n["canonical_claim"]),n["temporal_scope"],n["epistemic_class"])
                if immutable!=proposed: raise DuplicateConflictError("canonical_semantic_identity_conflict")
                self.db.execute("UPDATE seeds SET truth_state=?,confidence=?,version=MAX(version,?),freshness_class=?,revalidate_after=?,truth_receipt_json=?,contradictions_json=?,metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE seed_id=?",(n["truth_state"],n["confidence"],n["version"],n["freshness_class"],n["revalidate_after"],_stable(n["truth_receipt"]),_stable(n["contradictions"]),_stable(n["metadata"]),sid))
            for s in sources:
                source_id,row=self._source(s)
                self.db.execute("INSERT OR IGNORE INTO sources(source_id,source_uri,source_title,publisher,jurisdiction,source_date,retrieved_at,source_hash,source_kind,authority_class,freshness_class,metadata_json) VALUES(:source_id,:source_uri,:source_title,:publisher,:jurisdiction,:source_date,:retrieved_at,:source_hash,:source_kind,:authority_class,:freshness_class,:metadata_json)",row)
                relation=str(s.get("relation","supports")).strip() or "supports"
                if relation not in RELATIONS: raise InvalidSeedError("invalid_source_relation")
                before=self.db.total_changes
                self.db.execute("INSERT OR IGNORE INTO seed_sources(seed_id,source_id,relation) VALUES(?,?,?)",(sid,source_id,relation))
                merged+=int(self.db.total_changes>before)
            if n["revalidate_after"]:
                self.db.execute("INSERT INTO revalidation_queue(seed_id,due_at,reason,priority) VALUES(?,?,?,?) ON CONFLICT(seed_id) DO UPDATE SET due_at=excluded.due_at,reason=excluded.reason,priority=excluded.priority",(sid,n["revalidate_after"],"seed_freshness_policy",50))
            self.db.execute("COMMIT"); return ArchiveResult(sid,inserted,merged)
        except Exception:
            self.db.execute("ROLLBACK"); raise
    def get_seed(self,seed_id:str):
        row=self.db.execute("SELECT * FROM seeds WHERE seed_id=?",(seed_id,)).fetchone()
        if row is None:return None
        out=dict(row); out["truth_receipt"]=json.loads(out.pop("truth_receipt_json")); out["contradictions"]=json.loads(out.pop("contradictions_json")); out["metadata"]=json.loads(out.pop("metadata_json")); out["sources"]=[dict(r) for r in self.db.execute("SELECT s.*,ss.relation FROM sources s JOIN seed_sources ss ON ss.source_id=s.source_id WHERE ss.seed_id=? ORDER BY s.source_id",(seed_id,))]
        return out
    def add_edge(self,a:str,relation:str,b:str,metadata:Mapping[str,Any]|None=None):
        if a==b: raise UniverseLibraryError("self_edge_forbidden")
        if relation not in RELATIONS: raise UniverseLibraryError("invalid_relation")
        before=self.db.total_changes; self.db.execute("INSERT OR IGNORE INTO edges(from_seed_id,relation,to_seed_id,metadata_json) VALUES(?,?,?,?)",(a,relation,b,_stable(dict(metadata or {})))); return self.db.total_changes>before
    def supersede(self,old:str,new:str,reason:str=""):
        if old==new: raise UniverseLibraryError("self_supersession_forbidden")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT OR IGNORE INTO lineage(predecessor_seed_id,successor_seed_id,relation,reason) VALUES(?,?,?,?)",(old,new,"supersedes",str(reason)))
            self.db.execute("UPDATE seeds SET truth_state='superseded',updated_at=CURRENT_TIMESTAMP WHERE seed_id=?",(old,))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK"); raise
    def schedule_revalidation(self,seed_id:str,due_at:str,reason:str,priority:int=50):
        priority=int(priority)
        if not 0<=priority<=100: raise UniverseLibraryError("invalid_priority")
        self.db.execute("INSERT INTO revalidation_queue(seed_id,due_at,reason,priority) VALUES(?,?,?,?) ON CONFLICT(seed_id) DO UPDATE SET due_at=excluded.due_at,reason=excluded.reason,priority=excluded.priority",(seed_id,str(due_at),str(reason),priority))
    def due_revalidation(self,now_iso:str,limit:int=100):
        return [dict(r) for r in self.db.execute("SELECT q.*,s.subject,s.canonical_claim,s.domain,s.truth_state,s.confidence FROM revalidation_queue q JOIN seeds s USING(seed_id) WHERE q.due_at<=? ORDER BY q.priority DESC,q.due_at,seed_id LIMIT ?",(str(now_iso),max(1,min(int(limit),5000))))]
    def search(self,query:str,*,limit:int=25,truth_state:str|None=None,domain_prefix:str|None=None):
        q=_norm(query); limit=max(1,min(int(limit),500))
        if not q:return []
        clauses=["(normalized_subject LIKE ? OR normalized_claim LIKE ? OR lower(domain) LIKE ?)"]; params=[f"%{q}%",f"%{q}%",f"%{q}%"]
        if truth_state is not None:
            if truth_state not in TRUTH_STATES: raise UniverseLibraryError("invalid_truth_filter")
            clauses.append("truth_state=?"); params.append(truth_state)
        if domain_prefix:
            clauses.append("(domain=? OR domain LIKE ?)"); params.extend([domain_prefix,domain_prefix+".%"])
        params.append(limit)
        sql="SELECT seed_id,subject,canonical_claim,domain,epistemic_class,temporal_scope,valid_from,valid_to,scope,truth_state,confidence,version,freshness_class,revalidate_after FROM seeds WHERE "+" AND ".join(clauses)+" ORDER BY confidence DESC,seed_id LIMIT ?"
        return [dict(r) for r in self.db.execute(sql,params)]
    def regrow(self,seed_id:str,depth:int=1,edge_limit:int=100):
        depth=max(0,min(int(depth),4)); root=self.get_seed(seed_id)
        if root is None: raise UniverseLibraryError("seed_not_found")
        visited={seed_id}; frontier=[seed_id]; edges=[]; related=[]
        for _ in range(depth):
            if not frontier: break
            marks=",".join("?" for _ in frontier)
            rows=self.db.execute(f"SELECT * FROM edges WHERE from_seed_id IN ({marks}) OR to_seed_id IN ({marks}) LIMIT ?",[*frontier,*frontier,max(1,min(int(edge_limit),5000))]).fetchall()
            nxt=[]
            for row in rows:
                e=dict(row); edges.append(e)
                for k in (e["from_seed_id"],e["to_seed_id"]):
                    if k not in visited:
                        visited.add(k); nxt.append(k); related.append(self.get_seed(k))
            frontier=nxt
        lineage=[dict(r) for r in self.db.execute("SELECT * FROM lineage WHERE predecessor_seed_id=? OR successor_seed_id=? ORDER BY created_at",(seed_id,seed_id))]
        return {"root":root,"related":[x for x in related if x],"edges":edges,"lineage":lineage}
    def timeline(self,*,domain_prefix:str|None=None,limit:int=500):
        if domain_prefix:
            rows=self.db.execute("SELECT seed_id,subject,canonical_claim,domain,temporal_scope,valid_from,valid_to,truth_state,confidence FROM seeds WHERE domain=? OR domain LIKE ? ORDER BY valid_from,temporal_scope,seed_id LIMIT ?",(domain_prefix,domain_prefix+".%",max(1,min(int(limit),5000))))
        else:
            rows=self.db.execute("SELECT seed_id,subject,canonical_claim,domain,temporal_scope,valid_from,valid_to,truth_state,confidence FROM seeds ORDER BY valid_from,temporal_scope,seed_id LIMIT ?",(max(1,min(int(limit),5000)),))
        return [dict(r) for r in rows]
    def stats(self):
        c=lambda t:int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        return {"schema_version":self.schema_version(),"seeds":c("seeds"),"sources":c("sources"),"seed_source_links":c("seed_sources"),"edges":c("edges"),"lineage":c("lineage"),"revalidation_queue":c("revalidation_queue"),"by_domain":{r[0]:int(r[1]) for r in self.db.execute("SELECT domain,COUNT(*) FROM seeds GROUP BY domain ORDER BY domain")},"by_truth_state":{r[0]:int(r[1]) for r in self.db.execute("SELECT truth_state,COUNT(*) FROM seeds GROUP BY truth_state ORDER BY truth_state")},"by_freshness":{r[0]:int(r[1]) for r in self.db.execute("SELECT freshness_class,COUNT(*) FROM seeds GROUP BY freshness_class ORDER BY freshness_class")}}
    def export_seed(self,seed_id:str):
        seed=self.get_seed(seed_id)
        if seed is None: raise UniverseLibraryError("seed_not_found")
        return _stable(seed)

def _sample_seed(subject="Earth",claim="Earth orbits the Sun",domain="astronomy",truth="accepted",freshness="slow"):
    return {"subject":subject,"canonical_claim":claim,"domain":domain,"epistemic_class":"fact","temporal_scope":"current","valid_from":"2026-01-01","geographic_or_cosmic_scope":"Solar System","truth_state":truth,"confidence":0.99,"version":1,"freshness_class":freshness,"revalidate_after":"2027-01-01","truth_receipt":{"gate":"accepted","evidence_count":1},"contradictions":[],"metadata":{"test":True}}
def _sample_source(uri="https://example.invalid/source",h="abc"):
    return {"source_uri":uri,"source_title":"Source","publisher":"Test","jurisdiction":"global","source_date":"2026-09-07","retrieved_at":"2026-09-07T00:00:00Z","source_hash":h,"source_kind":"test","authority_class":"primary","freshness_class":"slow","relation":"supports"}
def self_test_25x2():
    checks=[]
    def expect(exc,fn):
        try: fn()
        except exc:return True
        return False
    for r in (1,2):
        with tempfile.TemporaryDirectory(prefix=f"eira_ul_v4_r{r}_") as td:
            db=Path(td)/"u.sqlite3"
            with UniverseLibrary(db) as lib:
                a=_sample_seed(); s=_sample_source(); x=lib.archive_seed(a,[s]); sid=x.seed_id
                checks += [(f"r{r}_01_schema",lib.schema_version()==4),(f"r{r}_02_db",db.exists()),(f"r{r}_03_insert",x.inserted),(f"r{r}_04_id",sid.startswith("seed_") and len(sid)==69),(f"r{r}_05_seed_one",lib.stats()["seeds"]==1),(f"r{r}_06_source_one",lib.stats()["sources"]==1),(f"r{r}_07_link_one",lib.stats()["seed_source_links"]==1),(f"r{r}_08_revalidation_auto",lib.stats()["revalidation_queue"]==1)]
                y=lib.archive_seed(a,[s]); checks += [(f"r{r}_09_dedup",not y.inserted),(f"r{r}_10_seed_still_one",lib.stats()["seeds"]==1)]
                z=lib.archive_seed(a,[_sample_source("https://example.invalid/2","def")]); checks += [(f"r{r}_11_provenance_merge",z.merged_provenance==1),(f"r{r}_12_two_sources",len(lib.get_seed(sid)["sources"])==2)]
                checks += [(f"r{r}_13_search",len(lib.search("orbits"))==1),(f"r{r}_14_domain_search",len(lib.search("Earth",domain_prefix="astronomy"))==1),(f"r{r}_15_truth_receipt",lib.get_seed(sid)["truth_receipt"]["gate"]=="accepted"),(f"r{r}_16_due_revalidation",len(lib.due_revalidation("2028-01-01"))==1)]
                sun=lib.archive_seed(_sample_seed("Sun","The Sun is a star"),[_sample_source("https://example.invalid/sun","sun")]).seed_id
                checks += [(f"r{r}_17_edge",lib.add_edge(sid,"orbits",sun)),(f"r{r}_18_edge_dedup",not lib.add_edge(sid,"orbits",sun)),(f"r{r}_19_regrow",len(lib.regrow(sid,1)["related"])==1),(f"r{r}_20_self_edge_reject",expect(UniverseLibraryError,lambda:lib.add_edge(sid,"related_to",sid)))]
                newer=lib.archive_seed(_sample_seed("Earth","Earth revolves around the Sun once per sidereal year"),[_sample_source("https://example.invalid/new","new")]).seed_id; lib.supersede(sid,newer,"revision")
                checks += [(f"r{r}_21_supersede",lib.get_seed(sid)["truth_state"]=="superseded"),(f"r{r}_22_lineage",len(lib.regrow(sid,0)["lineage"])==1),(f"r{r}_23_bad_domain",expect(InvalidSeedError,lambda:lib.archive_seed(_sample_seed(domain="garbage")))),(f"r{r}_24_bad_authority",expect(InvalidSeedError,lambda:lib.archive_seed(_sample_seed("Mars","Mars is a planet"),[{**_sample_source(),"authority_class":"magic"}]))),(f"r{r}_25_bad_priority",expect(UniverseLibraryError,lambda:lib.schedule_revalidation(newer,"2027-01-01","x",101)))]
    failed=[n for n,ok in checks if not ok]
    return {"schema":"eira2_universe_library_qualification_v4","distinct_tests":25,"rounds":2,"clean_passes":sum(1 for _,ok in checks if ok),"total":len(checks),"failed":failed,"pass":len(checks)==50 and not failed}

if __name__=="__main__":
    print(json.dumps(self_test_25x2(),indent=2,sort_keys=True))
'''

if __name__ == "__main__":
    ns={"__name__":"eira2_universe_library_v4_payload"}
    exec(compile(NEW,TARGET,"exec"),ns,ns)
    result=ns["self_test_25x2"]()
    print(__import__("json").dumps(result,indent=2,sort_keys=True))
    if not result.get("pass"): raise SystemExit(1)
