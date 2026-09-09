from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "eira2_universe_library_federation_v1"
ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
VAULT = ROOT / "eira_probe" / "universe_library" / "source_vault"
DB = VAULT / "source_index.sqlite3"
CACHE = ROOT / "eira_probe" / "universe_library" / "federation_cache"
USER_AGENT = "EIRA2-Universe-Library-Federation/1.0 (metadata-first; source-is-not-fact)"
TIMEOUT = 20

FEDERATED_SOURCES: dict[str, dict[str, Any]] = {
    "local_library": {
        "name": "EIRA Local Public Library",
        "mode": "local_index",
        "authority_class": "mixed_source_archive",
        "stores_full_text": "existing_local_only",
        "enabled": True,
    },
    "library_of_congress": {
        "name": "Library of Congress",
        "mode": "remote_live",
        "authority_class": "national_library",
        "endpoint": "https://www.loc.gov/books/",
        "stores_full_text": False,
        "cache": "metadata_only",
        "rights_rule": "Never infer reuse rights from availability; preserve item-level rights/access fields.",
        "enabled": True,
    },
    "nasa_ntrs": {
        "name": "NASA Technical Reports Server",
        "mode": "remote_live",
        "authority_class": "government_scientific_archive",
        "endpoint": "https://ntrs.nasa.gov/api/citations/search",
        "stores_full_text": False,
        "cache": "metadata_only",
        "enabled": True,
    },
    "doe_osti": {
        "name": "DOE OSTI.GOV",
        "mode": "remote_live",
        "authority_class": "government_scientific_archive",
        "endpoint": "https://www.osti.gov/api/v1/records",
        "stores_full_text": False,
        "cache": "metadata_only",
        "enabled": True,
    },
    "usgs_publications": {
        "name": "USGS Publications Warehouse",
        "mode": "remote_live",
        "authority_class": "government_scientific_archive",
        "endpoint": "https://pubs.usgs.gov/pubs-services/publication",
        "stores_full_text": False,
        "cache": "metadata_only",
        "enabled": True,
    },
    "ncbi_bookshelf": {
        "name": "NCBI Bookshelf",
        "mode": "remote_live",
        "authority_class": "government_biomedical_library",
        "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        "stores_full_text": False,
        "cache": "metadata_only",
        "rights_rule": "Bookshelf availability is not blanket OA permission; inspect title-specific copyright/permissions before persistence.",
        "enabled": True,
    },
    "open_library": {
        "name": "Open Library",
        "mode": "remote_live",
        "authority_class": "bibliographic_discovery",
        "endpoint": "https://openlibrary.org/search.json",
        "stores_full_text": False,
        "cache": "metadata_only",
        "enabled": True,
    },
    "govinfo": {
        "name": "GovInfo",
        "mode": "remote_live_keyed",
        "authority_class": "official_federal_document_repository",
        "endpoint": "https://api.govinfo.gov/",
        "api_key_env": "GOVINFO_API_KEY",
        "stores_full_text": False,
        "cache": "metadata_only",
        "enabled": bool(os.environ.get("GOVINFO_API_KEY")),
    },
    "smithsonian_open_access": {
        "name": "Smithsonian Open Access",
        "mode": "remote_live_keyed",
        "authority_class": "national_museum_archive",
        "endpoint": "https://api.si.edu/openaccess/api/v1.0/search",
        "api_key_env": "SMITHSONIAN_API_KEY",
        "stores_full_text": False,
        "cache": "metadata_only",
        "enabled": bool(os.environ.get("SMITHSONIAN_API_KEY")),
    },
}


def _json_get(url: str, params: dict[str, Any] | None = None) -> Any:
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(_text(x) for x in v if _text(x))
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return str(v)


def _result(source: str, item_id: Any, title: Any, authors: Any = "", subjects: Any = "", url: Any = "", rights: Any = "", date: Any = "", raw: Any = None) -> dict[str, Any]:
    return {
        "source_name": source,
        "source_work_id": _text(item_id),
        "title": _text(title),
        "authors": _text(authors),
        "subjects": _text(subjects),
        "source_url": _text(url),
        "rights": _text(rights),
        "source_release_date": _text(date),
        "source_is_not_fact": True,
        "remote_only": True,
        "metadata": raw if isinstance(raw, dict) else {},
    }


class FederatedLibrary:
    def __init__(self, db_path: str | Path = DB):
        self.db_path = Path(db_path)
        CACHE.mkdir(parents=True, exist_ok=True)

    def source_status(self) -> dict[str, Any]:
        return {k: {**v, "configured": bool(v.get("enabled"))} for k, v in FEDERATED_SOURCES.items()}

    def _local(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not self.db_path.is_file():
            return []
        con = sqlite3.connect(str(self.db_path), timeout=20)
        con.row_factory = sqlite3.Row
        try:
            like = f"%{query}%"
            rows = con.execute(
                "SELECT source_name,source_work_id,title,authors,subjects,source_url,rights,source_release_date,metadata_json "
                "FROM works WHERE title LIKE ? OR authors LIKE ? OR subjects LIKE ? LIMIT ?",
                (like, like, like, limit),
            ).fetchall()
            out = []
            for r in rows:
                try: raw = json.loads(r["metadata_json"] or "{}")
                except Exception: raw = {}
                x = _result(r["source_name"], r["source_work_id"], r["title"], r["authors"], r["subjects"], r["source_url"], r["rights"], r["source_release_date"], raw)
                x["remote_only"] = False
                out.append(x)
            return out
        finally:
            con.close()

    def _loc(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = _json_get("https://www.loc.gov/books/", {"fo": "json", "q": query, "c": limit})
        out = []
        for x in data.get("results", [])[:limit]:
            out.append(_result("library_of_congress", x.get("id") or x.get("url"), x.get("title"), x.get("contributor") or x.get("creator"), x.get("subject"), x.get("id") or x.get("url"), x.get("rights") or x.get("access_restricted"), x.get("date"), x))
        return out

    def _openlibrary(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = _json_get("https://openlibrary.org/search.json", {"q": query, "limit": limit})
        out = []
        for x in data.get("docs", [])[:limit]:
            key = x.get("key", "")
            out.append(_result("open_library", key, x.get("title"), x.get("author_name"), x.get("subject", [])[:12], "https://openlibrary.org" + key if key else "", "discovery_metadata_only", x.get("first_publish_year"), x))
        return out

    def _osti(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = _json_get("https://www.osti.gov/api/v1/records", {"q": query, "rows": limit})
        if not isinstance(data, list): data = data.get("records", []) if isinstance(data, dict) else []
        return [_result("doe_osti", x.get("osti_id"), x.get("title"), x.get("authors"), x.get("subjects"), x.get("product_url") or x.get("doi"), x.get("license") or x.get("access_limitation"), x.get("publication_date"), x) for x in data[:limit]]

    def _usgs(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = _json_get("https://pubs.usgs.gov/pubs-services/publication", {"q": query, "page_size": limit})
        if isinstance(data, dict):
            rows = data.get("records") or data.get("publications") or data.get("data") or []
        else: rows = data if isinstance(data, list) else []
        out = []
        for x in rows[:limit]:
            out.append(_result("usgs_publications", x.get("id") or x.get("indexId") or x.get("publicationId"), x.get("title"), x.get("authors") or x.get("author"), x.get("topics") or x.get("keywords"), x.get("publicationUrl") or x.get("url"), "USGS item-level access terms apply", x.get("publicationYear") or x.get("publicationDate"), x))
        return out

    def _nasa(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = _json_get("https://ntrs.nasa.gov/api/citations/search", {"q": query, "size": limit})
        rows = data.get("results") or data.get("items") or data.get("records") or [] if isinstance(data, dict) else []
        out = []
        for x in rows[:limit]:
            out.append(_result("nasa_ntrs", x.get("id") or x.get("stiTypeDetails"), x.get("title"), x.get("authorAffiliations") or x.get("authors"), x.get("keywords"), "https://ntrs.nasa.gov/citations/" + str(x.get("id", "")), x.get("copyright") or x.get("distribution"), x.get("publicationDate") or x.get("createdAt"), x))
        return out

    def _ncbi(self, query: str, limit: int) -> list[dict[str, Any]]:
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        params = {"db": "books", "term": query, "retmode": "json", "retmax": limit, "tool": "EIRA2_Universe_Library"}
        email = os.environ.get("NCBI_EUTILS_EMAIL")
        if email: params["email"] = email
        key = os.environ.get("NCBI_API_KEY")
        if key: params["api_key"] = key
        ids = (_json_get(base + "esearch.fcgi", params).get("esearchresult") or {}).get("idlist") or []
        if not ids: return []
        sparams = {"db": "books", "id": ",".join(ids), "retmode": "json", "version": "2.0", "tool": "EIRA2_Universe_Library"}
        if email: sparams["email"] = email
        if key: sparams["api_key"] = key
        data = _json_get(base + "esummary.fcgi", sparams).get("result") or {}
        out = []
        for i in ids:
            x = data.get(str(i), {})
            out.append(_result("ncbi_bookshelf", i, x.get("title"), x.get("authors"), "biomedical_bookshelf", "https://www.ncbi.nlm.nih.gov/books/" + str(i), "title_specific_permissions_required", x.get("pubdate"), x))
        return out[:limit]

    def search_source(self, source: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 20))
        funcs = {
            "local_library": self._local,
            "library_of_congress": self._loc,
            "nasa_ntrs": self._nasa,
            "doe_osti": self._osti,
            "usgs_publications": self._usgs,
            "ncbi_bookshelf": self._ncbi,
            "open_library": self._openlibrary,
        }
        if source not in funcs:
            raise ValueError(f"source_not_directly_searchable:{source}")
        return funcs[source](query, limit)

    def search(self, query: str, *, sources: list[str] | None = None, limit_per_source: int = 5) -> dict[str, Any]:
        requested = sources or ["local_library", "library_of_congress", "nasa_ntrs", "doe_osti", "usgs_publications", "ncbi_bookshelf", "open_library"]
        results: list[dict[str, Any]] = []
        failures: dict[str, str] = {}
        for source in requested:
            try:
                results.extend(self.search_source(source, query, limit_per_source))
            except Exception as e:
                failures[source] = f"{type(e).__name__}:{e}"[:500]
        results.sort(key=lambda x: (not bool(x.get("title")), x.get("source_name", ""), x.get("title", "").casefold()))
        receipt = {
            "schema": SCHEMA,
            "query": query,
            "sources_requested": requested,
            "result_count": len(results),
            "failures": failures,
            "source_is_not_fact": True,
            "metadata_first": True,
            "full_text_auto_download": False,
            "unix": time.time(),
            "results": results,
        }
        self._cache_receipt(receipt)
        return receipt

    def _cache_receipt(self, receipt: dict[str, Any]) -> Path:
        raw = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        qid = hashlib.sha256(raw).hexdigest()[:24]
        path = CACHE / f"query_{qid}.json"
        path.write_bytes(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode())
        return path

    def feather_into_index(self, results: list[dict[str, Any]]) -> dict[str, int]:
        """Feather remote metadata into the existing library index. Never stores remote full text."""
        if not self.db_path.is_file():
            raise FileNotFoundError(str(self.db_path))
        con = sqlite3.connect(str(self.db_path), timeout=60, isolation_level=None)
        now = time.time(); inserted = updated = skipped = 0
        try:
            for x in results:
                source = _text(x.get("source_name")); wid = _text(x.get("source_work_id"))
                if not source or not wid:
                    skipped += 1; continue
                meta = json.dumps(x.get("metadata") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                mh = hashlib.sha256(meta.encode()).hexdigest()
                old = con.execute("SELECT metadata_hash FROM works WHERE source_name=? AND source_work_id=?", (source, wid)).fetchone()
                vals = (x.get("title", ""), x.get("authors", ""), x.get("subjects", ""), "", x.get("source_url", ""), x.get("source_release_date", ""), x.get("rights", ""), meta, mh, now, source, wid)
                if old is None:
                    con.execute("INSERT INTO works(source_name,source_work_id,title,authors,subjects,language,source_url,source_release_date,rights,metadata_json,metadata_hash,first_seen_unix,last_seen_unix) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (source,wid,x.get("title",""),x.get("authors",""),x.get("subjects",""),"",x.get("source_url",""),x.get("source_release_date",""),x.get("rights",""),meta,mh,now,now)); inserted += 1
                else:
                    con.execute("UPDATE works SET title=?,authors=?,subjects=?,language=?,source_url=?,source_release_date=?,rights=?,metadata_json=?,metadata_hash=?,last_seen_unix=? WHERE source_name=? AND source_work_id=?", vals); updated += 1
            return {"inserted": inserted, "updated": updated, "skipped": skipped}
        finally:
            con.close()


def describe() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "root": str(ROOT),
        "index": str(DB),
        "policy": "remote-first, metadata-first, no automatic full-text mirroring",
        "sources": FEDERATED_SOURCES,
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2, sort_keys=True))
