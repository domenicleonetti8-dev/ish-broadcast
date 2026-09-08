#!/usr/bin/env python3
from __future__ import annotations

import json, os, sqlite3, time
from pathlib import Path

ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
LIB = ROOT / "eira_probe" / "universe_library"
VAULT = LIB / "source_vault"
DB = VAULT / "source_index.sqlite3"
TEXTS = VAULT / "project_gutenberg" / "texts"
BULK = VAULT / "project_gutenberg" / "bulk" / "txt-files.tar.zip"

def count(q):
    if not DB.is_file(): return None
    uri = f"file:{DB.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=15)
    try: return int(con.execute(q).fetchone()[0])
    finally: con.close()

def grouped():
    if not DB.is_file(): return {}
    uri = f"file:{DB.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=15)
    try:
        return {str(k): int(v) for k,v in con.execute("SELECT source_name,COUNT(*) FROM works GROUP BY source_name ORDER BY source_name")}
    finally: con.close()

def file_stats():
    files=0; total=0
    if TEXTS.is_dir():
        for p in TEXTS.rglob("*.txt"):
            try: total += p.stat().st_size; files += 1
            except OSError: pass
    return files,total

def read_json(path):
    try:
        x=json.loads(path.read_text(encoding="utf-8")); return x if isinstance(x,dict) else None
    except Exception: return None

text_files,text_bytes=file_stats()
result={
  "schema":"eira2_live_library_documentation_v1",
  "ok":True,
  "mutates_live":False,
  "root":str(ROOT),
  "library_root":str(LIB),
  "vault":str(VAULT),
  "db_exists":DB.is_file(),
  "works":count("SELECT COUNT(*) FROM works"),
  "documents":count("SELECT COUNT(*) FROM documents"),
  "ingest_receipts":count("SELECT COUNT(*) FROM ingest_receipts"),
  "works_by_source":grouped(),
  "gutenberg_extracted_text_files":text_files,
  "gutenberg_extracted_text_bytes":text_bytes,
  "gutenberg_bulk_archive_exists":BULK.is_file(),
  "gutenberg_bulk_archive_bytes":BULK.stat().st_size if BULK.is_file() else 0,
  "mass_stock_process":read_json(LIB/"mass_stock_process.json"),
  "mass_expansion_state":read_json(LIB/"mass_expansion_state.json"),
  "generated_unix":time.time(),
}
print(json.dumps(result,sort_keys=True))
