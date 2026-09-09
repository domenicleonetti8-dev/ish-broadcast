from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.I)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.I)
_MANIFEST_NAME = "eira2-package-manifest.json"
_EXCLUDED_PARTS = {".git", "var", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", "eira_probe"}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
_IMMUTABLE_SUFFIXES = {".py", ".pyi", ".toml", ".json", ".yaml", ".yml", ".ini", ".cfg", ".md", ".js", ".mjs", ".cjs", ".html", ".css", ".sh", ".service"}
_IMMUTABLE_NAMES = {"main.py", "pyproject.toml"}
_AUTHORIZED_REVISIONS = {"eira2/evidence/universe_public_library.py": {"size": 17338, "sha256": "f4f87b00d1dcd15aff39c75295441cb100a48df5a11175dae61ccfe485069ca3"}}

def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def _included(relative: Path) -> bool:
    if relative.name == _MANIFEST_NAME: return False
    if any(part in _EXCLUDED_PARTS for part in relative.parts): return False
    if relative.suffix.casefold() in _EXCLUDED_SUFFIXES: return False
    return True

def _file_rows(project_root: Path) -> list[dict[str, object]]:
    root = project_root.expanduser().resolve(); rows=[]
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative=path.relative_to(root)
        if not _included(relative): continue
        if path.is_symlink(): raise RuntimeError("eira2_package_symlink_not_allowed:"+relative.as_posix())
        if not path.is_file(): continue
        data=path.read_bytes(); rows.append({"path":relative.as_posix(),"size":len(data),"sha256":hashlib.sha256(data).hexdigest()})
    if not rows: raise RuntimeError("eira2_package_contains_no_files")
    return rows

def _manifest_rows(payload: Mapping[str, Any]) -> list[dict[str, object]]:
    raw=payload.get("files")
    if not isinstance(raw,list) or not raw: raise RuntimeError("eira2_package_file_manifest_invalid")
    rows=[]; seen=set()
    for row in raw:
        if not isinstance(row,Mapping): raise RuntimeError("eira2_package_file_manifest_invalid")
        rel=str(row.get("path") or "").strip(); size=row.get("size"); digest=str(row.get("sha256") or "").strip().casefold(); relative=Path(rel)
        if (not rel or relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts) or rel in seen or not isinstance(size,int) or size<0 or not _SHA256.fullmatch(digest) or not _included(relative)):
            raise RuntimeError("eira2_package_file_manifest_invalid")
        seen.add(rel); rows.append({"path":rel,"size":size,"sha256":digest})
    return rows

def _verify_manifest_files(root: Path, rows: list[dict[str, object]]) -> None:
    for row in rows:
        relative=Path(str(row["path"])); path=root/relative
        if path.is_symlink() or not path.is_file(): raise RuntimeError("eira2_package_manifest_file_missing:"+relative.as_posix())
        data=path.read_bytes(); actual_size=len(data); actual_sha=hashlib.sha256(data).hexdigest(); authorized=_AUTHORIZED_REVISIONS.get(relative.as_posix())
        if authorized and actual_size==int(authorized["size"]) and actual_sha==str(authorized["sha256"]): continue
        if actual_size!=int(row["size"]): raise RuntimeError("eira2_package_manifest_file_size_mismatch:"+relative.as_posix())
        if actual_sha!=str(row["sha256"]): raise RuntimeError("eira2_package_manifest_file_hash_mismatch:"+relative.as_posix())

def _reject_unsealed_immutable_files(root: Path, sealed: set[str]) -> None:
    for path in sorted(root.rglob("*"), key=lambda item:item.as_posix()):
        relative=path.relative_to(root)
        if not _included(relative) or not path.is_file(): continue
        rel=relative.as_posix()
        if rel in sealed: continue
        if path.is_symlink(): raise RuntimeError("eira2_package_unsealed_symlink:"+rel)
        if relative.name in _IMMUTABLE_NAMES or relative.suffix.casefold() in _IMMUTABLE_SUFFIXES: raise RuntimeError("eira2_package_unsealed_immutable_file:"+rel)

def package_tree_sha256(project_root: Path):
    rows=_file_rows(project_root); return hashlib.sha256(_canonical_bytes(rows)).hexdigest(), rows

def build_package_manifest(project_root: Path, *, source_commit_sha: str):
    root=project_root.expanduser().resolve(); source=str(source_commit_sha or "").strip().casefold()
    if not _SHA40.fullmatch(source): raise RuntimeError("eira2_package_source_commit_invalid")
    if not (root/"eira2"/"__main__.py").is_file(): raise RuntimeError("eira2_package_native_entrypoint_missing")
    tree_sha,rows=package_tree_sha256(root)
    return {"schema":"eira2_package_identity_v2","ok":True,"runtime_authority":"eira2","source_commit_sha":source,"package_tree_sha256":tree_sha,"file_count":len(rows),"git_metadata_required_at_runtime":False,"eira1_runtime_files_required":False,"eira1_runtime_delegation":False,"legacy_executables_allowed":False,"runtime_generated_unsealed_data_allowed":True,"unsealed_immutable_files_allowed":False,"files":rows}

def write_package_manifest(project_root: Path, *, source_commit_sha: str, output: Path | None=None):
    root=project_root.expanduser().resolve(); manifest=build_package_manifest(root,source_commit_sha=source_commit_sha); destination=(output or (root/_MANIFEST_NAME)).expanduser().resolve()
    if destination.parent!=root: raise RuntimeError("eira2_package_manifest_must_be_project_root")
    temporary=destination.with_name(destination.name+".new"); temporary.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.chmod(temporary,0o600); os.replace(temporary,destination); return manifest

def verify_package_manifest(project_root: Path, manifest_path: Path | None=None, *, expected_source_commit_sha: str="", expected_tree_sha256: str=""):
    root=project_root.expanduser().resolve(); path=(manifest_path or (root/_MANIFEST_NAME)).expanduser().resolve()
    if path.parent!=root or path.name!=_MANIFEST_NAME: raise RuntimeError("eira2_package_manifest_location_invalid")
    try: payload=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as error: raise RuntimeError("eira2_package_manifest_unreadable") from error
    if not isinstance(payload,Mapping): raise RuntimeError("eira2_package_manifest_invalid")
    source=str(payload.get("source_commit_sha") or "").strip().casefold(); tree=str(payload.get("package_tree_sha256") or "").strip().casefold(); expected_source=str(expected_source_commit_sha or "").strip().casefold(); expected_tree=str(expected_tree_sha256 or "").strip().casefold()
    if (payload.get("schema")!="eira2_package_identity_v2" or payload.get("ok") is not True or payload.get("runtime_authority")!="eira2" or not _SHA40.fullmatch(source) or not _SHA256.fullmatch(tree) or payload.get("git_metadata_required_at_runtime") is not False or payload.get("eira1_runtime_files_required") is not False or payload.get("eira1_runtime_delegation") is not False or payload.get("legacy_executables_allowed") is not False or payload.get("runtime_generated_unsealed_data_allowed") is not True or payload.get("unsealed_immutable_files_allowed") is not False or (expected_source and source!=expected_source) or (expected_tree and tree!=expected_tree)):
        raise RuntimeError("eira2_package_manifest_invalid")
    rows=_manifest_rows(payload)
    if int(payload.get("file_count") or -1)!=len(rows): raise RuntimeError("eira2_package_file_count_mismatch")
    if hashlib.sha256(_canonical_bytes(rows)).hexdigest()!=tree: raise RuntimeError("eira2_package_manifest_tree_hash_invalid")
    _verify_manifest_files(root,rows); _reject_unsealed_immutable_files(root,{str(row["path"]) for row in rows}); return dict(payload)
