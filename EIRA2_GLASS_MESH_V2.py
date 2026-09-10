#!/usr/bin/env python3
from __future__ import annotations

import ast, hashlib, json, os, re, subprocess, tempfile, time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_glass_mesh_v2"
VERSION = "2.0.0"
DEFAULT_INTERVAL = 15.0
MAX_PORTALS = 100_000
MAX_TEXT_BYTES = 512_000
HASH_CHUNK = 1024 * 1024
TEXT_SUFFIXES = {".py",".json",".html",".js",".md",".txt",".toml",".yaml",".yml",".css",".sh"}
SECRET_NAME_MARKERS = ("secret","token","password","passwd","credential","private_key",".env","id_rsa","id_ed25519")
SECRET_JSON_PATTERN = re.compile(r"""(?i)(["'](?:api[_-]?key|token|secret|password|passwd|authorization)["']\s*:\s*["'])([^"']*)(["'])""")
SECRET_ASSIGN_PATTERN = re.compile(r"""(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\s*=\s*(["']?)([^"'\s,;]+)(["']?)""")
SECRET_TOKEN_PATTERNS = (
    re.compile(r'(?i)\b(sk-[A-Za-z0-9_-]{12,})\b'),
    re.compile(r'(?i)\b(gh[pousr]_[A-Za-z0-9_]{12,})\b'),
    re.compile(r'(?i)\b(Bearer\s+[A-Za-z0-9._~+/=-]{8,})\b'),
)
EXCLUDE_PREFIXES = (
    ".git/",
    "eira_probe/glass_viewport/",
    "eira_probe/transport_runtime_v6/repo/",
    "eira2_transport_bus/from_superprobe/glass/",
)
GITHUB_REL = Path("eira2_transport_bus/from_superprobe/glass/latest.json")
LOCAL_REL = Path("eira_probe/glass_viewport/latest.json")
STATE_REL = Path("eira_probe/glass_viewport/state.json")

def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()

def _norm_rel(value: str) -> str:
    s = str(value or "").replace("\\","/")
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")

def _excluded(rel: str) -> bool:
    r = _norm_rel(rel)
    return any(r == p.rstrip("/") or r.startswith(p) for p in EXCLUDE_PREFIXES)

def _secretish_path(rel: str) -> bool:
    low = _norm_rel(rel).casefold()
    parts = [p.casefold() for p in Path(low).parts]
    return any(m in low or m in parts for m in SECRET_NAME_MARKERS)

def _redact_text(text: str) -> tuple[str,int]:
    out = text
    n = 0
    def repl_json(m):
        nonlocal n
        n += 1
        return m.group(1) + "<REDACTED>" + m.group(3)
    def repl_assign(m):
        nonlocal n
        n += 1
        return m.group(1) + "=" + m.group(2) + "<REDACTED>" + m.group(4)
    out = SECRET_JSON_PATTERN.sub(repl_json, out)
    out = SECRET_ASSIGN_PATTERN.sub(repl_assign, out)
    for pat in SECRET_TOKEN_PATTERNS:
        def repl_token(m):
            nonlocal n
            n += 1
            return "<REDACTED>"
        out = pat.sub(repl_token, out)
    return out, n

def _safe_root(root: str|Path) -> Path:
    p = Path(root).resolve()
    if not p.is_dir():
        raise RuntimeError("glass_root_missing:"+str(p))
    return p

def _symbol_portals(rel: str, text: str) -> tuple[list[dict[str,Any]], list[dict[str,str]]]:
    rows=[]; errs=[]
    if not rel.endswith(".py"):
        return rows, errs
    try:
        tree=ast.parse(text)
    except Exception as exc:
        errs.append({"path":rel,"kind":"python_parse","error":f"{type(exc).__name__}:{exc}"[:500]})
        return rows, errs
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            kind="class" if isinstance(node,ast.ClassDef) else "function"
            rows.append({
                "portal_id":f"{kind}:{rel}:{node.name}:{getattr(node,'lineno',0)}",
                "kind":kind,"path":rel,"name":node.name,
                "lineno":getattr(node,"lineno",None),
                "end_lineno":getattr(node,"end_lineno",None),
            })
    return rows, errs

def _file_portal(root: Path,p:Path,cache:dict[str,Any]) -> tuple[dict[str,Any],list[dict[str,Any]],list[dict[str,str]],dict[str,Any]]:
    rel=p.relative_to(root).as_posix()
    st=p.stat()
    key=rel
    meta={"size":st.st_size,"mtime_ns":st.st_mtime_ns,"inode":st.st_ino}
    row={"portal_id":"file:"+rel,"kind":"file","path":rel,"bytes":st.st_size,"mtime_ns":st.st_mtime_ns,"mode":st.st_mode,"suffix":p.suffix.lower(),"redacted":_secretish_path(rel)}
    extra=[]; blind=[]; newcache={"meta":meta}
    old=cache.get(key) if isinstance(cache.get(key),dict) else None
    if row["redacted"]:
        blind.append({"path":rel,"kind":"redacted_secret_path","reason":"content intentionally not exported"})
        return row,extra,blind,newcache
    if old and old.get("meta")==meta and isinstance(old.get("portal"),dict):
        reused=dict(old["portal"])
        reused["reused"]=True
        return reused, old.get("symbols",[]) or [], [], old
    try:
        digest=_sha_file(p)
        row["sha256"]=digest
    except Exception as exc:
        blind.append({"path":rel,"kind":"hash_error","reason":f"{type(exc).__name__}:{exc}"[:500]})
        return row,extra,blind,newcache
    if p.suffix.lower() in TEXT_SUFFIXES:
        if st.st_size > MAX_TEXT_BYTES:
            blind.append({"path":rel,"kind":"oversized_text","reason":f"content omitted above {MAX_TEXT_BYTES} bytes"})
        else:
            try:
                raw=p.read_bytes()
                text=raw.decode("utf-8",errors="replace")
                text,redactions=_redact_text(text)
                row["source"]=text
                row["encoding"]="utf-8-replace"
                row["content_redactions"]=redactions
                syms,errs=_symbol_portals(rel,text)
                extra.extend(syms); blind.extend(errs)
            except Exception as exc:
                blind.append({"path":rel,"kind":"content_read_error","reason":f"{type(exc).__name__}:{exc}"[:500]})
    else:
        blind.append({"path":rel,"kind":"binary_content","reason":"metadata and sha256 visible; binary body not exported"})
    newcache={"meta":meta,"portal":row,"symbols":extra}
    return row,extra,blind,newcache

def _process_portals(limit:int) -> tuple[list[dict[str,Any]],list[dict[str,str]]]:
    rows=[]; blind=[]
    proc=Path("/proc")
    if not proc.is_dir():
        return rows,[{"path":"/proc","kind":"proc_unavailable","reason":"process filesystem unavailable"}]
    for p in sorted((x for x in proc.iterdir() if x.name.isdigit()),key=lambda x:int(x.name)):
        if len(rows)>=limit:
            blind.append({"path":"/proc","kind":"process_portal_limit","reason":"process portal budget exhausted"})
            break
        try:
            pid=int(p.name)
            cmd=(p/"cmdline").read_bytes().replace(b"\0",b" ").decode("utf-8",errors="replace").strip()
            if not cmd:
                cmd=(p/"comm").read_text(errors="replace").strip()
            cmd,redactions=_redact_text(cmd)
            rows.append({"portal_id":f"process:{pid}","kind":"process","pid":pid,"cmd":cmd[:4000],"content_redactions":redactions})
        except Exception as exc:
            blind.append({"path":str(p),"kind":"process_read_error","reason":f"{type(exc).__name__}:{exc}"[:300]})
    return rows,blind

def snapshot(root:str|Path, previous_state:dict[str,Any]|None=None) -> tuple[dict[str,Any],dict[str,Any]]:
    live=_safe_root(root)
    cache=(previous_state or {}).get("cache") if isinstance(previous_state,dict) else {}
    if not isinstance(cache,dict): cache={}
    newcache={}
    portals=[]; blind=[]; scanned=0; excluded=0
    for p in live.rglob("*"):
        if len(portals)>=MAX_PORTALS:
            blind.append({"path":".","kind":"portal_limit","reason":f"portal budget {MAX_PORTALS} exhausted"})
            break
        try:
            rel=p.relative_to(live).as_posix()
            if _excluded(rel):
                excluded += 1
                continue
            if p.is_symlink():
                portals.append({"portal_id":"symlink:"+rel,"kind":"symlink","path":rel,"target":os.readlink(p)})
                continue
            if p.is_dir():
                portals.append({"portal_id":"dir:"+rel,"kind":"directory","path":rel})
                continue
            if not p.is_file():
                blind.append({"path":rel,"kind":"unsupported_fs_object","reason":"not regular file/dir/symlink"})
                continue
            scanned += 1
            row,extra,miss,nc=_file_portal(live,p,cache)
            portals.append(row)
            for x in extra:
                if len(portals)>=MAX_PORTALS:
                    blind.append({"path":rel,"kind":"portal_limit","reason":"symbol portal budget exhausted"})
                    break
                portals.append(x)
            blind.extend(miss); newcache[rel]=nc
        except Exception as exc:
            blind.append({"path":str(p),"kind":"scan_error","reason":f"{type(exc).__name__}:{exc}"[:500]})
    remaining=max(0,MAX_PORTALS-len(portals))
    prows,pblind=_process_portals(remaining)
    portals.extend(prows); blind.extend(pblind)
    portals.sort(key=lambda x:str(x.get("portal_id") or ""))
    blind.sort(key=lambda x:(x.get("kind",""),x.get("path","")))
    coverage={
        "root":str(live),
        "portal_count":len(portals),
        "files_scanned":scanned,
        "excluded_entries":excluded,
        "blind_spot_count":len(blind),
        "blind_spots":blind[:5000],
        "blind_spots_truncated":len(blind)>5000,
        "explicit_noncoverage":[
            "kernel memory not exposed as files",
            "hardware state not exposed by mounted LIVE or /proc",
            "remote services not mirrored into LIVE",
            "secret values intentionally redacted",
            "binary bodies intentionally not exported",
        ],
    }
    out={"schema":SCHEMA,"version":VERSION,"ok":True,"mutates_observed_live":False,"generated_unix":time.time(),"coverage":coverage,"portals":portals}
    raw=json.dumps(out,sort_keys=True,separators=(",",":")).encode()
    out["snapshot_sha256"]=_sha_bytes(raw)
    state={"schema":SCHEMA,"updated_unix":time.time(),"cache":newcache,"snapshot_sha256":out["snapshot_sha256"]}
    return out,state

def _atomic_json(path:Path,obj:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".tmp.",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(obj,f,indent=2,sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def _load_state(root:Path)->dict[str,Any]:
    p=root/STATE_REL
    if not p.is_file(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}

def write_local(root:str|Path,snap:dict[str,Any],state:dict[str,Any])->dict[str,str]:
    live=_safe_root(root)
    _atomic_json(live/LOCAL_REL,snap)
    _atomic_json(live/STATE_REL,state)
    return {"snapshot":str(live/LOCAL_REL),"state":str(live/STATE_REL)}

def capabilities()->dict[str,Any]:
    return {"schema":SCHEMA,"extension":"eira.glass.viewport","read_only_observation":True,"live_application_write":False,"logical_portals":"files+dirs+python-symbols+processes","blind_spot_accounting":True,"secret_value_redaction":True,"max_portals":MAX_PORTALS}

def ask(payload:dict[str,Any]|None=None)->dict[str,Any]:
    payload=payload or {}
    root=_safe_root(payload.get("root") or Path.cwd())
    mode=str(payload.get("mode") or "snapshot").casefold()
    if mode=="snapshot":
        snap,state=snapshot(root,_load_state(root))
        paths=write_local(root,snap,state)
        return {"schema":SCHEMA,"ok":True,"portal_count":snap["coverage"]["portal_count"],"blind_spot_count":snap["coverage"]["blind_spot_count"],"snapshot_sha256":snap["snapshot_sha256"],"paths":paths,"mutates_observed_live":False}
    if mode=="capabilities":
        return capabilities()
    raise RuntimeError("unsupported_mode:"+mode)
