from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Iterable

from .models import Edge, Node
from .normalize import edge_id, stable_id

_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules"}
_VOLATILE = {"omnivenom.sqlite3", "omnivenom.sqlite3-wal", "omnivenom.sqlite3-shm"}
_TEXT_SUFFIXES = {".py",".json",".md",".txt",".toml",".yaml",".yml",".ini",".cfg",".sh",".js",".ts",".swift",".html",".css",".scad"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _semantic_python(text: str) -> str:
    try:
        tree=ast.parse(text)
    except SyntaxError:
        return ""
    return _sha(ast.dump(tree, annotate_fields=True, include_attributes=False).encode())


def _module_from_rel(rel: str) -> str:
    p=Path(rel)
    if p.suffix != ".py":
        return ""
    parts=list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts=parts[:-1]
    return ".".join(parts)


def _rel_from_module(module: str) -> tuple[str,str]:
    base=module.replace(".","/")
    return base+".py", base+"/__init__.py"


class LiveCrawler:
    def __init__(self, live_root: str | Path, store, *, max_parse_bytes: int = 2_000_000):
        self.root=Path(live_root).expanduser().resolve()
        self.store=store
        self.max_parse_bytes=int(max_parse_bytes)
        self.root_id=stable_id("live_root", str(self.root))

    def _emit(self,node: Node,seen:set[str], now:float):
        self.store.upsert_node(node,now);seen.add(node.node_id)

    def _edge(self,source,target,relation,seen:set[str], now:float,confidence=1.0,evidence=None):
        e=Edge(edge_id(source,target,relation),source,target,relation,confidence,evidence or {})
        self.store.upsert_edge(e,now);seen.add(e.edge_id)

    def scan(self):
        if not self.root.is_dir():
            raise FileNotFoundError(self.root)
        with self.store.transaction():
            return self._scan_transaction()

    def _scan_transaction(self):
        started=time.time(); scan_id="scan_"+uuid.uuid4().hex
        self.store.begin_scan(scan_id,str(self.root),started)
        seen_nodes:set[str]=set();seen_edges:set[str]=set()
        self._emit(Node(self.root_id,"live_root",self.root.name,path="",aliases=["LIVE","Eira LIVE","root"]),seen_nodes,started)
        path_nodes={"":self.root_id}
        module_nodes={}
        pending_imports=[]
        # directories first, without following symlinks
        for current,dirs,files in os.walk(self.root,followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
            cur=Path(current)
            rel_cur=cur.relative_to(self.root).as_posix()
            if rel_cur==".": rel_cur=""
            parent_id=path_nodes.get(rel_cur,self.root_id)
            for d in list(dirs):
                p=cur/d; rel=p.relative_to(self.root).as_posix()
                if p.is_symlink():
                    nid=stable_id("symlink",rel)
                    try: target=os.readlink(p)
                    except OSError: target=""
                    self._emit(Node(nid,"symlink",d,path=rel,aliases=[d],metadata={"target":target}),seen_nodes,started)
                    self._edge(parent_id,nid,"contains",seen_edges,started)
                    dirs.remove(d)
                    continue
                nid=stable_id("directory",rel);path_nodes[rel]=nid
                self._emit(Node(nid,"directory",d,path=rel,aliases=[d,rel]),seen_nodes,started)
                self._edge(parent_id,nid,"contains",seen_edges,started)
            for name in sorted(files):
                if name in _VOLATILE: continue
                p=cur/name; rel=p.relative_to(self.root).as_posix()
                parent=path_nodes.get(rel_cur,self.root_id)
                if p.is_symlink():
                    nid=stable_id("symlink",rel)
                    try: target=os.readlink(p)
                    except OSError: target=""
                    self._emit(Node(nid,"symlink",name,path=rel,aliases=[name,rel],metadata={"target":target}),seen_nodes,started)
                    self._edge(parent,nid,"contains",seen_edges,started)
                    continue
                try: data=p.read_bytes()
                except OSError: continue
                digest=_sha(data); semantic=""; caps=[]; meta={"size":len(data),"suffix":p.suffix.lower()}
                text=""
                if len(data)<=self.max_parse_bytes and p.suffix.lower() in _TEXT_SUFFIXES:
                    try: text=data.decode("utf-8")
                    except UnicodeDecodeError: text=""
                if p.suffix.lower()==".py" and text:
                    semantic=_semantic_python(text)
                if name=="manifest.json" and text:
                    try:
                        obj=json.loads(text)
                        raw=obj.get("capabilities") or []
                        if isinstance(raw,list): caps=[str(x).strip() for x in raw if str(x).strip()]
                        for k in ("name","version","entrypoint","description"):
                            if k in obj: meta[k]=obj[k]
                    except Exception as exc:
                        meta["manifest_error"]=type(exc).__name__
                nid=stable_id("file",rel); aliases=[name,rel]
                module=_module_from_rel(rel)
                if module: aliases.append(module);module_nodes[module]=nid;meta["module"]=module
                self._emit(Node(nid,"file",name,path=rel,aliases=aliases,capabilities=caps,content_sha256=digest,semantic_sha256=semantic,metadata=meta),seen_nodes,started)
                self._edge(parent,nid,"contains",seen_edges,started)
                if caps:
                    for cap in caps:
                        cid=stable_id("capability",cap)
                        self._emit(Node(cid,"capability",cap,aliases=[cap],metadata={"declared_by":rel}),seen_nodes,started)
                        self._edge(nid,cid,"declares_capability",seen_edges,started)
                if p.suffix.lower()==".py" and text:
                    self._parse_python(rel,nid,module,text,seen_nodes,seen_edges,started,pending_imports)
        self._resolve_imports(module_nodes,pending_imports,seen_nodes,seen_edges,started)
        self.store.mark_unseen_missing(started,"")
        self.store.finish_scan(scan_id,finished=time.time(),nodes=len(seen_nodes),edges=len(seen_edges))
        return {"scan_id":scan_id,"nodes_seen":len(seen_nodes),"edges_seen":len(seen_edges),**self.store.counts()}

    def _parse_python(self,rel,file_id,module,text,seen_nodes,seen_edges,now,pending):
        try: tree=ast.parse(text,filename=rel)
        except SyntaxError: return
        parent_module=module.rsplit(".",1)[0] if module and "." in module else ""
        for item in tree.body:
            if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                kind="class" if isinstance(item,ast.ClassDef) else "function"
                qual=(module+"." if module else "")+item.name
                sid=stable_id(kind,qual or rel+":"+item.name)
                self._emit(Node(sid,kind,item.name,path=f"{rel}#{item.name}",aliases=[item.name,qual],metadata={"module":module,"lineno":getattr(item,"lineno",0)}),seen_nodes,now)
                self._edge(file_id,sid,"defines",seen_edges,now)
            if isinstance(item,ast.Import):
                for alias in item.names: pending.append((file_id,alias.name,rel,"import"))
            elif isinstance(item,ast.ImportFrom):
                base=item.module or ""
                if item.level:
                    parts=module.split(".") if module else []
                    pkg=parts[:-1] if rel.endswith(".py") and not rel.endswith("/__init__.py") else parts
                    climb=max(0,item.level-1)
                    if climb: pkg=pkg[:-climb] if climb<=len(pkg) else []
                    base=".".join([*pkg,base] if base else pkg)
                if base: pending.append((file_id,base,rel,"from_import"))
        # static call-name edges are intentionally local/symbolic only; never import code.
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=""
                if isinstance(node.func,ast.Name): name=node.func.id
                elif isinstance(node.func,ast.Attribute): name=node.func.attr
                if name:
                    cid=stable_id("callsite_symbol",name)
                    self._emit(Node(cid,"callsite_symbol",name,aliases=[name],state="symbolic"),seen_nodes,now)
                    self._edge(file_id,cid,"calls_symbol",seen_edges,now,0.45,{"static_only":True})

    def _resolve_imports(self,module_nodes,pending,seen_nodes,seen_edges,now):
        for source,module,rel,relation in pending:
            target=module_nodes.get(module)
            if not target:
                # parent package __init__ is a valid target
                target=module_nodes.get(module.rstrip("."))
            if target:
                self._edge(source,target,"imports",seen_edges,now,1.0,{"module":module})
                continue
            # classify namespace-local references as unresolved; others as external dependencies.
            first=module.split(".",1)[0] if module else ""
            internal = first in {"extensions","brain","core","engine","council","routers","voice","memory","reasoning","speech","tools","services","systems"}
            kind="unresolved" if internal else "external_dependency"
            state="unresolved" if internal else "external"
            uid=stable_id(kind,module)
            self._emit(Node(uid,kind,module or "unknown",aliases=[module],state=state,metadata={"expected_module":module,"referenced_from":rel}),seen_nodes,now)
            self._edge(source,uid,"imports_missing" if internal else "imports_external",seen_edges,now,0.95 if internal else 0.8,{"module":module})
