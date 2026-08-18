from __future__ import annotations
import ast, json
from pathlib import Path
from typing import Any, Dict
from .common import _STANDARD_CALLS

def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _safe_entrypoint(value: str) -> bool:
    if not value or value.startswith(".") or ".." in value or "/" in value or "\\" in value:
        return False
    return all(part.isidentifier() for part in value.split("."))


def _plugin_static_contract(plugin: Path, extension_name: str) -> Dict[str, Any]:
    try:
        tree = ast.parse(plugin.read_text(encoding="utf-8", errors="replace"), filename=str(plugin))
    except Exception:
        return {}
    meta: Dict[str, Any] = {}
    for item in tree.body:
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"CAPABILITIES", "ROLE", "NAME", "VERSION", "ENTRYPOINT"}:
                    value = _literal(item.value)
                    if value is not None:
                        meta[target.id.lower()] = value
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "register":
            for sub in ast.walk(item):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    value = _literal(sub.value)
                    if isinstance(value, dict):
                        for key in ("name", "version", "entrypoint", "capabilities"):
                            if key in value:
                                meta[key] = value[key]
                        break
    caps = meta.get("capabilities")
    meta["capabilities"] = [str(x).strip() for x in caps if str(x).strip()] if isinstance(caps, (list, tuple, set)) else []
    if not str(meta.get("entrypoint") or "").strip() and meta["capabilities"]:
        meta["entrypoint"] = f"extensions.{extension_name}.plugin"
    meta["discovery"] = "static_plugin_contract"
    return meta


def _extension_contract(ext: Path) -> Dict[str, Any]:
    manifest = ext / "manifest.json"
    if manifest.is_file() and not manifest.is_symlink():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            data = dict(data)
            data["discovery"] = "manifest_json"
            return data
    plugin = ext / "plugin.py"
    return _plugin_static_contract(plugin, ext.name) if plugin.is_file() and not plugin.is_symlink() else {}
