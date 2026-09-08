from __future__ import annotations

import json, os, sqlite3
from pathlib import Path

ROOT=Path(os.environ.get("EIRA_LIVE_ROOT","/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
BASE=ROOT/"eira_probe"/"universe_library"
VAULT=BASE/"source_vault"
DB=VAULT/"source_index.sqlite3"

def load(p:Path):
 try:
  v=json.loads(p.read_text(encoding="utf-8"));return v if isinstance(v,dict) else {}
 except Exception:return {}

def alive(pid):
 try:os.kill(int(pid),0);return True
 except Exception:return False

def main():
 out={"schema":"eira2_universe_library_live_status_v1","ok":True,"mutates_live":False,"base":str(BASE)}
 if DB.is_file():
  try:
   db=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=10)
   out["works"]=int(db.execute("SELECT COUNT(*) FROM works").fetchone()[0])
   out["documents"]=int(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
   out["works_by_source"]={str(a):int(b) for a,b in db.execute("SELECT source_name,COUNT(*) FROM works GROUP BY source_name")}
   db.close()
  except Exception as e:out["db_error"]=f"{type(e).__name__}:{e}";out["ok"]=False
 else:out["works"]=0;out["documents"]=0;out["works_by_source"]={}
 texts=VAULT/"project_gutenberg"/"texts"; out["gutenberg_extracted_text_files"]=sum(1 for _ in texts.rglob("*.txt")) if texts.is_dir() else 0
 archive=VAULT/"project_gutenberg"/"bulk"/"txt-files.tar.zip"; out["gutenberg_bulk_archive_bytes"]=archive.stat().st_size if archive.is_file() else 0
 for name in ("mass_stock_process.json","mass_expansion_state.json","gutenberg_refresh_state.json","gutenberg_index_process.json","gutenberg_document_index_state.json","open_book_oai_process.json","open_book_oai_state.json"):
  v=load(BASE/name)
  if v and "pid" in v:v["pid_alive"]=alive(v.get("pid"))
  out[name[:-5]]=v
 print(json.dumps(out,sort_keys=True))
 return 0
if __name__=="__main__":raise SystemExit(main())
