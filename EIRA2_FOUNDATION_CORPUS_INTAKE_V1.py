from __future__ import annotations

TARGET = "eira2/evidence/universe_foundation_intake.py"

NEW = r'''from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "eira2_foundation_corpus_intake_v1"
USER_AGENT = "EIRA2-FoundationCorpus/1.0 (+local research archive)"
DEFAULT_TIMEOUT = 45

PROVIDERS = {
    "loc_books": {
        "name": "Library of Congress Books",
        "authority": "national_library",
        "domain": "world_history",
        "rights_mode": "record_specific",
        "freshness": "moderate",
        "endpoint": "https://www.loc.gov/books/",
    },
    "ncbi_books": {
        "name": "NCBI Bookshelf",
        "authority": "national_medical_library",
        "domain": "medicine",
        "rights_mode": "record_specific",
        "freshness": "fast",
        "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    },
    "usgs_publications": {
        "name": "USGS Publications Warehouse",
        "authority": "government_science_agency",
        "domain": "geology",
        "rights_mode": "record_specific",
        "freshness": "fast",
        "endpoint": "https://pubs.usgs.gov/search/",
    },
}

class IntakeError(RuntimeError): pass


def _stable(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip())


def source_identity(provider: str, canonical_url: str, external_id: str, title: str) -> str:
    payload = {"provider": provider, "canonical_url": canonical_url.strip(), "external_id": external_id.strip(), "title": _norm(title).casefold()}
    return "source_" + _sha_text(_stable(payload))


def _http_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _first(v: Any, default: str = "") -> str:
    if isinstance(v, list): return _norm(v[0]) if v else default
    return _norm(v) or default


def _loc_records(page: int, count: int) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"fo": "json", "c": max(1, min(count, 100)), "sp": max(1, page)})
    data = _http_json(PROVIDERS["loc_books"]["endpoint"] + "?" + q)
    out = []
    for row in data.get("results") or []:
        title = _norm(row.get("title"))
        url = _norm(row.get("id") or row.get("url"))
        external_id = _norm(row.get("control_number") or row.get("id"))
        if not title or not url: continue
        out.append({
            "provider": "loc_books", "external_id": external_id, "title": title,
            "canonical_url": url, "date": _first(row.get("date")), "creator": _first(row.get("contributor")),
            "subjects": list(row.get("subject") or []), "languages": list(row.get("language") or []),
            "formats": list(row.get("original_format") or []), "rights": _norm(row.get("rights") or row.get("rights_advisory")),
            "raw_metadata": row,
        })
    return out


def _ncbi_book_ids(retmax: int) -> list[str]:
    params = urllib.parse.urlencode({"db": "books", "term": "all[filter]", "retmax": max(1, min(retmax, 100000)), "retmode": "json"})
    data = _http_json(PROVIDERS["ncbi_books"]["endpoint"] + "esearch.fcgi?" + params)
    return [str(x) for x in ((data.get("esearchresult") or {}).get("idlist") or [])]


def _ncbi_summaries(ids: list[str]) -> list[dict[str, Any]]:
    if not ids: return []
    params = urllib.parse.urlencode({"db": "books", "id": ",".join(ids[:200]), "retmode": "json"})
    data = _http_json(PROVIDERS["ncbi_books"]["endpoint"] + "esummary.fcgi?" + params)
    result = data.get("result") or {}; out=[]
    for uid in result.get("uids") or []:
        row = result.get(str(uid)) or {}; title=_norm(row.get("title") or row.get("booktitle") or row.get("name"))
        if not title: continue
        url=f"https://www.ncbi.nlm.nih.gov/books/{uid}/"
        out.append({"provider":"ncbi_books","external_id":str(uid),"title":title,"canonical_url":url,"date":_norm(row.get("pubdate") or row.get("sortpubdate")),"creator":_norm(row.get("authors") or row.get("author")),"subjects":list(row.get("attributes") or []),"languages":[],"formats":["book_or_document"],"rights":"record_specific","raw_metadata":row})
    return out


def _usgs_records(page: int, page_size: int) -> list[dict[str, Any]]:
    candidates = [
        {"format":"json","page_size":max(1,min(page_size,100)),"page":max(1,page)},
        {"format":"json","page-size":max(1,min(page_size,100)),"page":max(1,page)},
    ]
    last = None
    for params in candidates:
        try:
            data = _http_json(PROVIDERS["usgs_publications"]["endpoint"] + "?" + urllib.parse.urlencode(params))
            rows = data.get("records") or data.get("results") or data.get("publications") or []
            out=[]
            for row in rows:
                title=_norm(row.get("title")); url=_norm(row.get("url") or row.get("publicationUrl") or row.get("indexId")); ext=_norm(row.get("indexId") or row.get("id") or url)
                if not title or not url: continue
                out.append({"provider":"usgs_publications","external_id":ext,"title":title,"canonical_url":url,"date":_norm(row.get("publicationYear") or row.get("year") or row.get("date")),"creator":_norm(row.get("authors") or row.get("contributors")),"subjects":list(row.get("topics") or row.get("subjects") or []),"languages":[],"formats":[_norm(row.get("publicationType") or "publication")],"rights":"record_specific","raw_metadata":row})
            if out: return out
        except Exception as exc: last=exc
    if last: raise IntakeError(f"usgs_fetch_failed:{last}")
    return []


class FoundationCorpusIntake:
    """Source-vault intake only; does not promote factual truth.

    Stores source metadata and queues source records for downstream claim extraction.
    It deliberately does not write accepted factual seeds directly.
    """
    def __init__(self, db_path: str | Path):
        self.db_path=Path(db_path); self.db_path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(self.db_path),timeout=30,isolation_level=None); self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS foundation_sources(
          source_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          external_id TEXT NOT NULL,
          title TEXT NOT NULL,
          canonical_url TEXT NOT NULL,
          publication_date TEXT NOT NULL DEFAULT '',
          creator TEXT NOT NULL DEFAULT '',
          authority_class TEXT NOT NULL,
          domain TEXT NOT NULL,
          freshness_class TEXT NOT NULL,
          rights_mode TEXT NOT NULL,
          rights_text TEXT NOT NULL DEFAULT '',
          subjects_json TEXT NOT NULL DEFAULT '[]',
          languages_json TEXT NOT NULL DEFAULT '[]',
          formats_json TEXT NOT NULL DEFAULT '[]',
          raw_metadata_json TEXT NOT NULL,
          metadata_sha256 TEXT NOT NULL,
          first_seen_unix REAL NOT NULL,
          last_seen_unix REAL NOT NULL,
          UNIQUE(provider,external_id),
          UNIQUE(provider,canonical_url,title)
        );
        CREATE TABLE IF NOT EXISTS foundation_candidate_queue(
          source_id TEXT PRIMARY KEY REFERENCES foundation_sources(source_id) ON DELETE CASCADE,
          state TEXT NOT NULL DEFAULT 'pending',
          priority INTEGER NOT NULL DEFAULT 50,
          attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '',
          updated_unix REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_foundation_provider ON foundation_sources(provider);
        CREATE INDEX IF NOT EXISTS idx_foundation_domain ON foundation_sources(domain);
        CREATE INDEX IF NOT EXISTS idx_foundation_date ON foundation_sources(publication_date);
        CREATE INDEX IF NOT EXISTS idx_foundation_queue_state ON foundation_candidate_queue(state,priority);
        """)
    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self,*_): self.close()
    def archive_record(self, record: dict[str,Any]) -> tuple[str,bool]:
        provider=_norm(record.get("provider")); cfg=PROVIDERS.get(provider)
        if not cfg: raise IntakeError("unknown_provider")
        title=_norm(record.get("title")); url=_norm(record.get("canonical_url")); ext=_norm(record.get("external_id"))
        if not title or not url or not ext: raise IntakeError("record_requires_title_url_external_id")
        sid=source_identity(provider,url,ext,title); raw=dict(record.get("raw_metadata") or {}); meta_hash=_sha_text(_stable(raw)); now=time.time()
        before=self.db.total_changes
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT OR IGNORE INTO foundation_sources(source_id,provider,external_id,title,canonical_url,publication_date,creator,authority_class,domain,freshness_class,rights_mode,rights_text,subjects_json,languages_json,formats_json,raw_metadata_json,metadata_sha256,first_seen_unix,last_seen_unix) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,provider,ext,title,url,_norm(record.get("date")),_norm(record.get("creator")),cfg["authority"],cfg["domain"],cfg["freshness"],cfg["rights_mode"],_norm(record.get("rights")),_stable(list(record.get("subjects") or [])),_stable(list(record.get("languages") or [])),_stable(list(record.get("formats") or [])),_stable(raw),meta_hash,now,now))
            inserted=self.db.total_changes>before
            if not inserted:
                self.db.execute("UPDATE foundation_sources SET last_seen_unix=?,raw_metadata_json=?,metadata_sha256=? WHERE provider=? AND external_id=?",(now,_stable(raw),meta_hash,provider,ext))
                row=self.db.execute("SELECT source_id FROM foundation_sources WHERE provider=? AND external_id=?",(provider,ext)).fetchone(); sid=str(row[0])
            self.db.execute("INSERT OR IGNORE INTO foundation_candidate_queue(source_id,state,priority,updated_unix) VALUES(?,'pending',50,?)",(sid,now))
            self.db.execute("COMMIT"); return sid,inserted
        except Exception:
            self.db.execute("ROLLBACK"); raise
    def ingest_records(self, records: Iterable[dict[str,Any]]) -> dict[str,int]:
        seen=inserted=0
        for rec in records:
            seen+=1; _,new=self.archive_record(rec); inserted+=int(new)
        return {"seen":seen,"inserted":inserted,"duplicates":seen-inserted}
    def ingest_loc(self,pages:int=10,count:int=100):
        total={"seen":0,"inserted":0,"duplicates":0}
        for p in range(1,max(1,pages)+1):
            r=self.ingest_records(_loc_records(p,count))
            for k in total: total[k]+=r[k]
        return total
    def ingest_ncbi(self,limit:int=2000):
        ids=_ncbi_book_ids(limit); total={"seen":0,"inserted":0,"duplicates":0}
        for i in range(0,len(ids),200):
            r=self.ingest_records(_ncbi_summaries(ids[i:i+200]))
            for k in total: total[k]+=r[k]
        return total
    def ingest_usgs(self,pages:int=10,page_size:int=100):
        total={"seen":0,"inserted":0,"duplicates":0}
        for p in range(1,max(1,pages)+1):
            r=self.ingest_records(_usgs_records(p,page_size))
            for k in total: total[k]+=r[k]
        return total
    def stats(self):
        c=lambda q:int(self.db.execute(q).fetchone()[0])
        return {"schema":SCHEMA,"sources":c("SELECT COUNT(*) FROM foundation_sources"),"pending":c("SELECT COUNT(*) FROM foundation_candidate_queue WHERE state='pending'"),"providers":{r[0]:int(r[1]) for r in self.db.execute("SELECT provider,COUNT(*) FROM foundation_sources GROUP BY provider")}}


def self_test_25x2():
    import tempfile
    checks=[]
    fake={"provider":"loc_books","external_id":"1","title":"A History of Earth","canonical_url":"https://example.invalid/1","date":"1900","creator":"A","subjects":["history"],"languages":["eng"],"formats":["book"],"rights":"public domain","raw_metadata":{"x":1}}
    for r in (1,2):
        with tempfile.TemporaryDirectory() as td:
            with FoundationCorpusIntake(Path(td)/"f.sqlite3") as x:
                sid,new=x.archive_record(fake)
                checks += [(f"r{r}_01_schema",x.stats()["schema"]==SCHEMA),(f"r{r}_02_id",sid.startswith("source_") and len(sid)==71),(f"r{r}_03_insert",new),(f"r{r}_04_count",x.stats()["sources"]==1),(f"r{r}_05_pending",x.stats()["pending"]==1)]
                sid2,new2=x.archive_record(fake)
                checks += [(f"r{r}_06_same_id",sid2==sid),(f"r{r}_07_dedup",not new2),(f"r{r}_08_count_stable",x.stats()["sources"]==1),(f"r{r}_09_queue_stable",x.stats()["pending"]==1)]
                fake2={**fake,"external_id":"2","canonical_url":"https://example.invalid/2","title":"Physics"}; batch=x.ingest_records([fake,fake2])
                checks += [(f"r{r}_10_batch_seen",batch["seen"]==2),(f"r{r}_11_batch_insert",batch["inserted"]==1),(f"r{r}_12_batch_dup",batch["duplicates"]==1),(f"r{r}_13_two_sources",x.stats()["sources"]==2),(f"r{r}_14_provider_count",x.stats()["providers"].get("loc_books")==2)]
                row=x.db.execute("SELECT authority_class,domain,freshness_class,rights_mode,rights_text,metadata_sha256 FROM foundation_sources WHERE source_id=?",(sid,)).fetchone()
                checks += [(f"r{r}_15_authority",row[0]=="national_library"),(f"r{r}_16_domain",row[1]=="world_history"),(f"r{r}_17_freshness",row[2]=="moderate"),(f"r{r}_18_rights_mode",row[3]=="record_specific"),(f"r{r}_19_rights_text",row[4]=="public domain"),(f"r{r}_20_hash",len(row[5])==64)]
                checks += [(f"r{r}_21_identity_deterministic",source_identity("loc_books",fake["canonical_url"],"1",fake["title"])==sid),(f"r{r}_22_queue_fk",x.db.execute("SELECT COUNT(*) FROM foundation_candidate_queue q JOIN foundation_sources s ON s.source_id=q.source_id").fetchone()[0]==2),(f"r{r}_23_wal",x.db.execute("PRAGMA journal_mode").fetchone()[0].lower()=="wal"),(f"r{r}_24_indexes",len(x.db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_foundation_%'").fetchall())>=4),(f"r{r}_25_provider_registry",set(PROVIDERS)=={"loc_books","ncbi_books","usgs_publications"})]
    failed=[n for n,ok in checks if not ok]
    return {"schema":"eira2_foundation_corpus_intake_qualification_v1","distinct_tests":25,"rounds":2,"clean_passes":sum(int(ok) for _,ok in checks),"total":len(checks),"failed":failed,"pass":len(checks)==50 and not failed}

if __name__ == "__main__":
    print(json.dumps(self_test_25x2(),indent=2,sort_keys=True))
'''

if __name__ == "__main__":
    ns={"__name__":"eira2_foundation_corpus_payload"}
    exec(compile(NEW,TARGET,"exec"),ns,ns)
    result=ns["self_test_25x2"]()
    print(json.dumps(result,indent=2,sort_keys=True))
    raise SystemExit(0 if result.get("pass") else 1)
