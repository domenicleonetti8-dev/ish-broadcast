from __future__ import annotations
import base64, json, os, sqlite3, time, uuid, hashlib
from pathlib import Path
from typing import Any

EXT_ROOT = Path(__file__).resolve().parent
LIVE_ROOT = EXT_ROOT.parents[1]
DATA_ROOT = Path(os.environ.get("EIRA_INVENTOR_ARCHIVE", str(EXT_ROOT / "archive"))).resolve()
FILES_ROOT = DATA_ROOT / "files"
MODELS_ROOT = DATA_ROOT / "models"
JOBS_ROOT = DATA_ROOT / "jobs"
DB_PATH = DATA_ROOT / "inventor_archive.sqlite3"

def _init() -> None:
    for p in (DATA_ROOT, FILES_ROOT, MODELS_ROOT, JOBS_ROOT):
        p.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS inventions(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
          created REAL NOT NULL, updated REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS assets(
          id TEXT PRIMARY KEY, invention_id TEXT NOT NULL, name TEXT NOT NULL,
          mime TEXT NOT NULL, relpath TEXT NOT NULL, sha256 TEXT NOT NULL,
          kind TEXT NOT NULL, created REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes(
          id TEXT PRIMARY KEY, invention_id TEXT NOT NULL, category TEXT NOT NULL,
          text TEXT NOT NULL, confidence REAL, source TEXT NOT NULL, created REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events(
          id TEXT PRIMARY KEY, invention_id TEXT, kind TEXT NOT NULL,
          payload TEXT NOT NULL, created REAL NOT NULL
        );
        """)

def status() -> dict[str, Any]:
    _init()
    return {
      "ok": True,
      "extension": "eira_inventor_holographic_lab",
      "node_id": "eira.inventor.holographic_lab",
      "archive": str(DATA_ROOT),
      "database": str(DB_PATH),
      "omnivenom_discovery": "whole-LIVE filesystem mesh",
      "voice_owner": "existing EIRA bridge / browser speech surface",
      "core_modified": False,
      "engineering3d_provider": "extensions.unified_brain_ai.providers.engineering3d",
    }

def create_invention(title: str, description: str = "") -> dict[str, Any]:
    _init()
    title=(title or "").strip()
    if not title: raise ValueError("title_required")
    now=time.time(); iid="inv_"+uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO inventions(id,title,description,created,updated,version) VALUES(?,?,?,?,?,1)",
                   (iid,title,description.strip(),now,now))
    return get_invention(iid)

def list_inventions() -> list[dict[str, Any]]:
    _init()
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM inventions ORDER BY updated DESC").fetchall()]

def get_invention(iid: str) -> dict[str, Any]:
    _init()
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT * FROM inventions WHERE id=?",(iid,)).fetchone()
        if not row: raise KeyError("invention_not_found")
        out=dict(row)
        out["assets"]=[dict(r) for r in db.execute("SELECT * FROM assets WHERE invention_id=? ORDER BY created",(iid,)).fetchall()]
        out["notes"]=[dict(r) for r in db.execute("SELECT * FROM notes WHERE invention_id=? ORDER BY created",(iid,)).fetchall()]
        return out

def add_asset(iid: str, name: str, mime: str, data: bytes, kind: str = "source") -> dict[str, Any]:
    _init(); get_invention(iid)
    safe=Path(name or "asset.bin").name.replace("\x00","")
    aid="asset_"+uuid.uuid4().hex
    folder=FILES_ROOT/iid; folder.mkdir(parents=True,exist_ok=True)
    path=folder/(aid+"_"+safe)
    path.write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO assets(id,invention_id,name,mime,relpath,sha256,kind,created) VALUES(?,?,?,?,?,?,?,?)",
                   (aid,iid,safe,mime or "application/octet-stream",str(path.relative_to(DATA_ROOT)),sha,kind,time.time()))
        db.execute("UPDATE inventions SET updated=?,version=version+1 WHERE id=?",(time.time(),iid))
    return {"id":aid,"name":safe,"mime":mime,"sha256":sha,"kind":kind,"url":f"/archive/{path.relative_to(DATA_ROOT).as_posix()}"}

def add_note(iid: str, category: str, text: str, confidence: float|None=None, source: str="eira") -> dict[str, Any]:
    _init(); get_invention(iid)
    nid="note_"+uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO notes(id,invention_id,category,text,confidence,source,created) VALUES(?,?,?,?,?,?,?)",
                   (nid,iid,category,text,confidence,source,time.time()))
    return {"id":nid,"category":category,"text":text,"confidence":confidence,"source":source}

def queue_render(iid: str, mode: str="engineering_completion") -> dict[str, Any]:
    _init(); inv=get_invention(iid)
    allowed={"faithful_concept","engineering_completion","scientific_plausibility","presentation"}
    if mode not in allowed: raise ValueError("invalid_render_mode")
    job={"job_id":"render_"+uuid.uuid4().hex,"invention_id":iid,"mode":mode,
         "created":time.time(),"status":"queued","invention":inv}
    path=JOBS_ROOT/(job["job_id"]+".json"); path.write_text(json.dumps(job,indent=2),encoding="utf-8")
    return job

def chat(text: str) -> dict[str, Any]:
    text=(text or "").strip()
    if not text: return {"status":"unresolved","response":"","errors":["empty_prompt"]}
    try:
        from extensions.omnivenom_mesh_ai.eira_bridge import chat as eira_chat
        return eira_chat(text, persist_history=True)
    except Exception as exc:
        return {"status":"unresolved","response":"EIRA conversation bridge is not available in this process.",
                "errors":[f"{type(exc).__name__}:{str(exc)[:200]}"]}

_init()


def engineering3d_status() -> dict[str, Any]:
    try:
        from .engineering3d_bridge import provider_contract
        return provider_contract()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{str(exc)[:500]}"}

def process_next_render() -> dict[str, Any]:
    from .blender_bridge import run_once
    return run_once()
