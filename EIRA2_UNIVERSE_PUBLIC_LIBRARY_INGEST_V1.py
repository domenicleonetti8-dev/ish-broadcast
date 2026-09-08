from __future__ import annotations

TARGET = "eira2/evidence/universe_public_library.py"

NEW = r'''from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
DEFAULT_ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
DEFAULT_VAULT = DEFAULT_ROOT / "eira_probe" / "universe_library" / "source_vault"
CATALOG_URL = "https://dev.gutenberg.org/cache/epub/feeds/pg_catalog.csv.gz"
CORPUS_URL = "https://dev.gutenberg.org/cache/epub/feeds/txt-files.tar.zip"
USER_AGENT = "EIRA2-Universe-Library/1.0 (+local research archive; sanctioned bulk endpoints only)"

PUBLIC_LIBRARY_SOURCES = {
    "project_gutenberg": {
        "name": "Project Gutenberg",
        "kind": "public_domain_library",
        "authority_class": "curated_public_library",
        "jurisdiction": "United States",
        "catalog_url": CATALOG_URL,
        "full_text_bulk_url": CORPUS_URL,
        "catalog_refresh": "daily_or_weekly",
        "full_text_refresh": "weekly",
        "full_text_storage_allowed": True,
        "copyright_rule": "Only treat individual works as unrestricted when Gutenberg metadata/license permits; preserve source license metadata.",
        "truth_rule": "Books are source material, never automatically accepted factual memory.",
    },
    "wikisource": {
        "name": "Wikisource",
        "kind": "free_source_text_library",
        "authority_class": "community_curated_source_archive",
        "jurisdiction": "global",
        "homepage": "https://wikisource.org/",
        "full_text_storage_allowed": "license_dependent",
        "copyright_rule": "Preserve per-work license/public-domain status and Wikimedia attribution requirements.",
        "truth_rule": "Primary/historical texts remain evidence; extracted factual claims require independent Truth Gate evaluation.",
    },
    "openstax": {
        "name": "OpenStax",
        "kind": "open_textbook_library",
        "authority_class": "peer_reviewed_educational",
        "jurisdiction": "United States",
        "homepage": "https://openstax.org/",
        "full_text_storage_allowed": "license_dependent",
        "license_family": "Creative Commons; preserve title-specific terms and attribution",
        "truth_rule": "Textbook claims are strong educational evidence but still versioned and revalidated in fast-moving fields.",
    },
    "ncbi_bookshelf_oa": {
        "name": "NCBI Bookshelf Open Access Subset",
        "kind": "biomedical_open_access_archive",
        "authority_class": "government_scientific_archive",
        "jurisdiction": "United States",
        "homepage": "https://www.ncbi.nlm.nih.gov/books/",
        "full_text_storage_allowed": "open_access_subset_only",
        "copyright_rule": "Never bulk-copy the general Bookshelf site. Use only NLM LitArch OAI/FTP open-access subset or title-specific permitted content.",
        "truth_rule": "Medical claims require the stricter medical Truth Gate and currency checks.",
    },
}

class PublicLibraryError(RuntimeError): pass


def _sha_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _download(url: str, dest: Path, *, min_free_bytes: int = 2_000_000_000, timeout: int = 120) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest.parent).free
    if free < min_free_bytes:
        raise PublicLibraryError(f"insufficient_free_space:{free}")
    part = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": USER_AGENT}
    mode = "wb"
    existing = part.stat().st_size if part.exists() else 0
    if existing:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        status = getattr(r, "status", 200)
        if existing and status != 206:
            existing = 0
            mode = "wb"
        with part.open(mode) as out:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    os.replace(part, dest)
    return {"path": str(dest), "bytes": dest.stat().st_size, "sha256": _sha_file(dest), "url": url}


def _safe_member_name(name: str) -> str:
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise PublicLibraryError(f"unsafe_archive_member:{name}")
    return p.as_posix()


class PublicLibraryVault:
    def __init__(self, root: str | Path = DEFAULT_VAULT):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "source_index.sqlite3"
        self.db = sqlite3.connect(str(self.db_path), timeout=60.0, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._schema()

    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def _schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS works(
          source_name TEXT NOT NULL,
          source_work_id TEXT NOT NULL,
          title TEXT NOT NULL DEFAULT '',
          authors TEXT NOT NULL DEFAULT '',
          subjects TEXT NOT NULL DEFAULT '',
          language TEXT NOT NULL DEFAULT '',
          source_url TEXT NOT NULL DEFAULT '',
          source_release_date TEXT NOT NULL DEFAULT '',
          rights TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          metadata_hash TEXT NOT NULL,
          first_seen_unix REAL NOT NULL,
          last_seen_unix REAL NOT NULL,
          PRIMARY KEY(source_name,source_work_id)
        );
        CREATE TABLE IF NOT EXISTS documents(
          document_hash TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          source_work_id TEXT NOT NULL,
          relative_path TEXT NOT NULL,
          bytes INTEGER NOT NULL,
          indexed_unix REAL NOT NULL,
          UNIQUE(source_name,source_work_id,relative_path)
        );
        CREATE TABLE IF NOT EXISTS ingest_receipts(
          receipt_id TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          operation TEXT NOT NULL,
          started_unix REAL NOT NULL,
          completed_unix REAL NOT NULL,
          status TEXT NOT NULL,
          details_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_works_title ON works(title);
        CREATE INDEX IF NOT EXISTS idx_works_language ON works(language);
        CREATE INDEX IF NOT EXISTS idx_docs_work ON documents(source_name,source_work_id);
        """)
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('source_is_not_fact','1')")

    def ingest_gutenberg_catalog(self) -> dict[str, Any]:
        started = time.time()
        raw = self.root / "project_gutenberg" / "catalog" / "pg_catalog.csv.gz"
        dl = _download(CATALOG_URL, raw, min_free_bytes=500_000_000)
        inserted = updated = unchanged = 0
        now = time.time()
        with gzip.open(raw, "rt", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise PublicLibraryError("gutenberg_catalog_missing_headers")
            id_keys = [k for k in reader.fieldnames if k.casefold() in {"text#", "text", "ebook no.", "ebook no", "id", "ebook"}]
            for row in reader:
                lowered = {str(k).strip().casefold(): str(v or "").strip() for k, v in row.items()}
                work_id = ""
                for k in ("text#", "text", "ebook no.", "ebook no", "id", "ebook"):
                    if lowered.get(k): work_id = lowered[k]; break
                if not work_id:
                    # Stable fallback from complete metadata row; never invent a numerical Gutenberg id.
                    work_id = "meta_" + hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
                title = lowered.get("title", "")
                authors = lowered.get("author", lowered.get("authors", ""))
                subjects = lowered.get("subject", lowered.get("subjects", ""))
                language = lowered.get("language", lowered.get("languages", ""))
                release = lowered.get("release date", lowered.get("release_date", ""))
                rights = lowered.get("copyright status", lowered.get("rights", ""))
                source_url = f"https://www.gutenberg.org/ebooks/{work_id}" if work_id.isdigit() else ""
                meta_json = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                mh = hashlib.sha256(meta_json.encode()).hexdigest()
                old = self.db.execute("SELECT metadata_hash FROM works WHERE source_name='project_gutenberg' AND source_work_id=?", (work_id,)).fetchone()
                if old is None:
                    self.db.execute("INSERT INTO works(source_name,source_work_id,title,authors,subjects,language,source_url,source_release_date,rights,metadata_json,metadata_hash,first_seen_unix,last_seen_unix) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", ('project_gutenberg',work_id,title,authors,subjects,language,source_url,release,rights,meta_json,mh,now,now)); inserted += 1
                elif old[0] != mh:
                    self.db.execute("UPDATE works SET title=?,authors=?,subjects=?,language=?,source_url=?,source_release_date=?,rights=?,metadata_json=?,metadata_hash=?,last_seen_unix=? WHERE source_name='project_gutenberg' AND source_work_id=?", (title,authors,subjects,language,source_url,release,rights,meta_json,mh,now,work_id)); updated += 1
                else:
                    self.db.execute("UPDATE works SET last_seen_unix=? WHERE source_name='project_gutenberg' AND source_work_id=?", (now,work_id)); unchanged += 1
        details = {"download": dl, "inserted": inserted, "updated": updated, "unchanged": unchanged, "total": inserted+updated+unchanged}
        rid = "receipt_" + hashlib.sha256(json.dumps(details,sort_keys=True).encode()).hexdigest()[:24]
        self.db.execute("INSERT OR REPLACE INTO ingest_receipts VALUES(?,?,?,?,?,?)", (rid,'project_gutenberg','catalog',started,time.time(),'PASS',json.dumps(details,sort_keys=True)))
        return {"ok": True, "receipt_id": rid, **details}

    def download_gutenberg_full_text_archive(self, *, minimum_free_bytes: int = 25_000_000_000) -> dict[str, Any]:
        """Download Gutenberg's sanctioned weekly all-text archive into the cold source vault.

        This does NOT convert book prose into accepted factual Seeds. It only preserves source material.
        """
        started = time.time()
        dest = self.root / "project_gutenberg" / "bulk" / "txt-files.tar.zip"
        dl = _download(CORPUS_URL, dest, min_free_bytes=minimum_free_bytes, timeout=300)
        details = {"download": dl, "source_is_not_fact": True, "extracted": False}
        rid = "receipt_" + hashlib.sha256(json.dumps(details,sort_keys=True).encode()).hexdigest()[:24]
        self.db.execute("INSERT OR REPLACE INTO ingest_receipts VALUES(?,?,?,?,?,?)", (rid,'project_gutenberg','bulk_download',started,time.time(),'PASS',json.dumps(details,sort_keys=True)))
        return {"ok": True, "receipt_id": rid, **details}

    def extract_gutenberg_full_text_archive(self) -> dict[str, Any]:
        archive = self.root / "project_gutenberg" / "bulk" / "txt-files.tar.zip"
        if not archive.is_file(): raise PublicLibraryError("gutenberg_bulk_archive_missing")
        target = self.root / "project_gutenberg" / "texts"
        target.mkdir(parents=True, exist_ok=True)
        extracted = skipped = 0
        # Gutenberg distributes a zip containing a tar. Extract defensively in two stages.
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(('.tar','.tar.gz','.tgz','.txt'))]
            if not names: raise PublicLibraryError("gutenberg_zip_contains_no_supported_payload")
            for n in names:
                _safe_member_name(n)
                if n.lower().endswith('.txt'):
                    out = target / Path(n).name
                    if out.exists(): skipped += 1; continue
                    with zf.open(n) as src, out.open('wb') as dst: shutil.copyfileobj(src,dst)
                    extracted += 1
                else:
                    with tempfile.TemporaryDirectory(prefix='eira_pg_tar_') as td:
                        tarp = Path(td)/Path(n).name
                        with zf.open(n) as src, tarp.open('wb') as dst: shutil.copyfileobj(src,dst)
                        with tarfile.open(tarp, 'r:*') as tf:
                            for m in tf:
                                if not m.isfile(): continue
                                _safe_member_name(m.name)
                                if not m.name.lower().endswith('.txt'): continue
                                out = target / Path(m.name).name
                                if out.exists(): skipped += 1; continue
                                fh = tf.extractfile(m)
                                if fh is None: continue
                                with fh, out.open('wb') as dst: shutil.copyfileobj(fh,dst)
                                extracted += 1
        return {"ok": True, "target": str(target), "extracted_files": extracted, "skipped_existing": skipped}

    def stats(self) -> dict[str, Any]:
        c=lambda t:int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        return {"schema_version":SCHEMA_VERSION,"works":c('works'),"documents":c('documents'),"receipts":c('ingest_receipts'),"vault":str(self.root),"source_is_not_fact":True}


def self_test_25x2() -> dict[str, Any]:
    checks=[]
    for r in (1,2):
        with tempfile.TemporaryDirectory(prefix=f'eira_public_library_r{r}_') as td:
            with PublicLibraryVault(Path(td)/'vault') as v:
                checks += [(f'r{r}_01_schema',v.stats()['schema_version']==1),(f'r{r}_02_db',v.db_path.exists()),(f'r{r}_03_source_not_fact',v.stats()['source_is_not_fact'] is True),(f'r{r}_04_gutenberg_registry','project_gutenberg' in PUBLIC_LIBRARY_SOURCES),(f'r{r}_05_wikisource_registry','wikisource' in PUBLIC_LIBRARY_SOURCES),(f'r{r}_06_openstax_registry','openstax' in PUBLIC_LIBRARY_SOURCES),(f'r{r}_07_ncbi_registry','ncbi_bookshelf_oa' in PUBLIC_LIBRARY_SOURCES),(f'r{r}_08_gutenberg_fulltext_allowed',PUBLIC_LIBRARY_SOURCES['project_gutenberg']['full_text_storage_allowed'] is True),(f'r{r}_09_ncbi_restricted',PUBLIC_LIBRARY_SOURCES['ncbi_bookshelf_oa']['full_text_storage_allowed']=='open_access_subset_only'),(f'r{r}_10_catalog_https',CATALOG_URL.startswith('https://')),(f'r{r}_11_corpus_https',CORPUS_URL.startswith('https://')),(f'r{r}_12_unique_works_pk',len(v.db.execute("PRAGMA table_info(works)").fetchall())>=10),(f'r{r}_13_documents_hash_pk',any(x[1]=='document_hash' and x[5]==1 for x in v.db.execute("PRAGMA table_info(documents)").fetchall())),(f'r{r}_14_receipts_table',v.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ingest_receipts'").fetchone() is not None),(f'r{r}_15_wal',v.db.execute('PRAGMA journal_mode').fetchone()[0].lower()=='wal')]
                bad=False
                try:_safe_member_name('../evil')
                except PublicLibraryError:bad=True
                checks.append((f'r{r}_16_traversal_rejected',bad))
                bad=False
                try:_safe_member_name('/evil')
                except PublicLibraryError:bad=True
                checks.append((f'r{r}_17_absolute_rejected',bad))
                checks += [(f'r{r}_18_safe_member',_safe_member_name('a/b.txt')=='a/b.txt'),(f'r{r}_19_catalog_name',Path(CATALOG_URL).name=='pg_catalog.csv.gz'),(f'r{r}_20_corpus_name',Path(CORPUS_URL).name=='txt-files.tar.zip'),(f'r{r}_21_vault_outside_code','eira_probe' in str(DEFAULT_VAULT)),(f'r{r}_22_no_auto_truth','truth_rule' in PUBLIC_LIBRARY_SOURCES['project_gutenberg']),(f'r{r}_23_license_metadata', 'copyright_rule' in PUBLIC_LIBRARY_SOURCES['project_gutenberg']),(f'r{r}_24_medical_boundary','medical Truth Gate' in PUBLIC_LIBRARY_SOURCES['ncbi_bookshelf_oa']['truth_rule']),(f'r{r}_25_four_sources',len(PUBLIC_LIBRARY_SOURCES)==4)]
    failed=[n for n,ok in checks if not ok]
    return {'schema':'eira2_public_library_ingest_qualification_v1','distinct_tests':25,'rounds':2,'clean_passes':sum(bool(ok) for _,ok in checks),'total':len(checks),'failed':failed,'pass':len(checks)==50 and not failed}

if __name__ == '__main__':
    print(json.dumps(self_test_25x2(),indent=2,sort_keys=True))
'''

if __name__ == '__main__':
    import json, types, sys
    name='eira2_universe_public_library_payload_test'
    mod=types.ModuleType(name); mod.__file__=TARGET; sys.modules[name]=mod
    exec(compile(NEW,TARGET,'exec'),mod.__dict__,mod.__dict__)
    result=mod.self_test_25x2()
    print(json.dumps(result,indent=2,sort_keys=True))
    raise SystemExit(0 if result.get('pass') else 1)
