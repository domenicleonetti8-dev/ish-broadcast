from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

SCHEMA = "eira2_universe_library_research_wing_v1"
USER_AGENT = "EIRA2-Research-Wing/1.0 (metadata-first; source-is-not-fact)"
TIMEOUT = 20
MAX_RESULTS = 20

SOURCES: dict[str, dict[str, Any]] = {
    "semantic_scholar": {
        "name": "Semantic Scholar Academic Graph",
        "mode": "remote_live",
        "endpoint": "https://api.semanticscholar.org/graph/v1/paper/search",
        "api_key_env": "SEMANTIC_SCHOLAR_API_KEY",
        "enabled": True,
        "full_text_auto_download": False,
    },
    "crossref": {
        "name": "Crossref REST API",
        "mode": "remote_live",
        "endpoint": "https://api.crossref.org/works",
        "polite_email_env": "CROSSREF_MAILTO",
        "enabled": True,
        "full_text_auto_download": False,
    },
    "pubmed": {
        "name": "PubMed via NCBI E-utilities",
        "mode": "remote_live",
        "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        "api_key_env": "NCBI_API_KEY",
        "email_env": "NCBI_EUTILS_EMAIL",
        "enabled": True,
        "full_text_auto_download": False,
    },
    "arxiv": {
        "name": "arXiv",
        "mode": "remote_live",
        "endpoint": "https://export.arxiv.org/api/query",
        "enabled": True,
        "full_text_auto_download": False,
    },
}


def _json_get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _xml_get(url: str, params: dict[str, Any] | None = None) -> bytes:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(_text(x) for x in v if _text(x))
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return str(v)


def _result(source: str, item_id: Any, title: Any, authors: Any = "", subjects: Any = "", url: Any = "",
            date: Any = "", doi: Any = "", abstract: Any = "", raw: Any = None) -> dict[str, Any]:
    return {
        "source_name": source,
        "source_work_id": _text(item_id),
        "title": _text(title),
        "authors": _text(authors),
        "subjects": _text(subjects),
        "source_url": _text(url),
        "source_release_date": _text(date),
        "doi": _text(doi),
        "abstract": _text(abstract),
        "source_is_not_fact": True,
        "remote_only": True,
        "metadata_only": True,
        "full_text_auto_download": False,
        "metadata": raw if isinstance(raw, dict) else {},
    }


class ResearchWing:
    def status(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "policy": "bounded metadata retrieval only; no automatic full-text download or bulk ingestion",
            "sources": SOURCES,
            "source_is_not_fact": True,
        }

    def semantic_scholar(self, query: str, limit: int) -> list[dict[str, Any]]:
        fields = "paperId,title,authors,year,url,abstract,externalIds,fieldsOfStudy,publicationDate,citationCount,referenceCount"
        headers = {}
        key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        if key:
            headers["x-api-key"] = key
        data = _json_get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {"query": query, "limit": limit, "fields": fields},
            headers,
        )
        out = []
        for x in (data.get("data") or [])[:limit]:
            ext = x.get("externalIds") or {}
            authors = [a.get("name") for a in (x.get("authors") or []) if isinstance(a, dict)]
            out.append(_result(
                "semantic_scholar", x.get("paperId"), x.get("title"), authors,
                x.get("fieldsOfStudy"), x.get("url"), x.get("publicationDate") or x.get("year"),
                ext.get("DOI"), x.get("abstract"), x,
            ))
        return out

    def crossref(self, query: str, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "query.bibliographic": query,
            "rows": limit,
            "select": "DOI,title,author,published,URL,subject,type,license,is-referenced-by-count,references-count",
        }
        mailto = os.environ.get("CROSSREF_MAILTO")
        if mailto:
            params["mailto"] = mailto
        data = _json_get("https://api.crossref.org/works", params)
        items = ((data.get("message") or {}).get("items") or [])
        out = []
        for x in items[:limit]:
            authors = []
            for a in x.get("author") or []:
                if isinstance(a, dict):
                    name = " ".join(y for y in [a.get("given"), a.get("family")] if y)
                    if name:
                        authors.append(name)
            title = (x.get("title") or [""])[0] if isinstance(x.get("title"), list) else x.get("title")
            date = ""
            parts = (((x.get("published") or {}).get("date-parts") or [[]])[0])
            if parts:
                date = "-".join(str(v) for v in parts)
            out.append(_result(
                "crossref", x.get("DOI"), title, authors, x.get("subject"),
                x.get("URL"), date, x.get("DOI"), "", x,
            ))
        return out

    def pubmed(self, query: str, limit: int) -> list[dict[str, Any]]:
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        common: dict[str, Any] = {"tool": "EIRA2_Universe_Library"}
        email = os.environ.get("NCBI_EUTILS_EMAIL")
        key = os.environ.get("NCBI_API_KEY")
        if email:
            common["email"] = email
        if key:
            common["api_key"] = key
        search = _json_get(base + "esearch.fcgi", {**common, "db": "pubmed", "term": query, "retmode": "json", "retmax": limit})
        ids = ((search.get("esearchresult") or {}).get("idlist") or [])[:limit]
        if not ids:
            return []
        data = _json_get(base + "esummary.fcgi", {**common, "db": "pubmed", "id": ",".join(ids), "retmode": "json", "version": "2.0"})
        res = data.get("result") or {}
        out = []
        for uid in ids:
            x = res.get(str(uid)) or {}
            authors = [a.get("name") for a in (x.get("authors") or []) if isinstance(a, dict)]
            doi = ""
            for aid in x.get("articleids") or []:
                if isinstance(aid, dict) and str(aid.get("idtype")).lower() == "doi":
                    doi = aid.get("value") or ""
                    break
            out.append(_result(
                "pubmed", uid, x.get("title"), authors, x.get("fulljournalname") or x.get("source"),
                "https://pubmed.ncbi.nlm.nih.gov/" + str(uid) + "/", x.get("pubdate"), doi, "", x,
            ))
        return out

    def arxiv(self, query: str, limit: int) -> list[dict[str, Any]]:
        raw = _xml_get("https://export.arxiv.org/api/query", {"search_query": "all:" + query, "start": 0, "max_results": limit})
        root = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        out = []
        for e in root.findall("a:entry", ns)[:limit]:
            item_id = (e.findtext("a:id", default="", namespaces=ns) or "").rstrip("/").split("/")[-1]
            title = " ".join((e.findtext("a:title", default="", namespaces=ns) or "").split())
            summary = " ".join((e.findtext("a:summary", default="", namespaces=ns) or "").split())
            authors = [a.findtext("a:name", default="", namespaces=ns) for a in e.findall("a:author", ns)]
            cats = [c.attrib.get("term", "") for c in e.findall("a:category", ns)]
            doi = e.findtext("arxiv:doi", default="", namespaces=ns) or ""
            out.append(_result(
                "arxiv", item_id, title, authors, cats,
                e.findtext("a:id", default="", namespaces=ns), e.findtext("a:published", default="", namespaces=ns),
                doi, summary, {},
            ))
        return out

    def search_source(self, source: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        n = max(1, min(int(limit), MAX_RESULTS))
        fn = {
            "semantic_scholar": self.semantic_scholar,
            "crossref": self.crossref,
            "pubmed": self.pubmed,
            "arxiv": self.arxiv,
        }.get(source)
        if not fn:
            raise ValueError("unsupported_source:" + source)
        return fn(query, n)

    def search(self, query: str, sources: list[str] | None = None, limit_per_source: int = 5) -> dict[str, Any]:
        requested = sources or ["semantic_scholar", "crossref", "pubmed", "arxiv"]
        results: list[dict[str, Any]] = []
        failures: dict[str, str] = {}
        for source in requested:
            try:
                results.extend(self.search_source(source, query, limit_per_source))
            except Exception as e:
                failures[source] = f"{type(e).__name__}:{e}"[:500]
        return {
            "schema": SCHEMA,
            "query": query,
            "sources_requested": requested,
            "result_count": len(results),
            "failures": failures,
            "source_is_not_fact": True,
            "metadata_only": True,
            "full_text_auto_download": False,
            "unix": time.time(),
            "results": results,
        }


def describe() -> dict[str, Any]:
    return ResearchWing().status()


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2, sort_keys=True))
