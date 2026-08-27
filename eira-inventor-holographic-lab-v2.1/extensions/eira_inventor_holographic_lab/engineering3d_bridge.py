from __future__ import annotations

import base64
import hashlib
import importlib
import inspect
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from . import plugin

PROVIDER_MODULE = "extensions.unified_brain_ai.providers.engineering3d"
ENGINEERING_PACKAGE = "extensions.unified_brain_ai.engineering3d"
PROVIDER_BASE = "extensions.unified_brain_ai.provider_base"
SCHEMA_MODULE = "extensions.unified_brain_ai.schema"
REQUIRED_SUBMODULES = ("schema", "validate", "exploded", "export", "materials", "physics")
FALLBACK_CAPABILITIES = (
    "scientific_3d_render",
    "engineering3d",
    "engineering_3d_blueprint",
    "engineering_3d_validate",
    "engineering_exploded_view",
    "engineering_physics_validate",
)

class Engineering3DContractError(RuntimeError):
    pass

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _sig(obj) -> str:
    try:
        return str(inspect.signature(obj))
    except Exception:
        return "<?>"

def _request_type(provider_mod):
    cls = getattr(provider_mod, "CapabilityRequest", None)
    if inspect.isclass(cls):
        return cls
    for module_name in (SCHEMA_MODULE, PROVIDER_BASE):
        try:
            mod = importlib.import_module(module_name)
        except Exception:
            continue
        cls = getattr(mod, "CapabilityRequest", None)
        if inspect.isclass(cls):
            return cls
    return None

def _media_type():
    for module_name in (SCHEMA_MODULE, PROVIDER_BASE, PROVIDER_MODULE):
        try:
            mod = importlib.import_module(module_name)
        except Exception:
            continue
        cls = getattr(mod, "MediaPart", None)
        if inspect.isclass(cls):
            return cls
    return None

def _strings(obj):
    out = []
    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for k, val in v.items():
                if isinstance(k, str):
                    out.append(k)
                walk(val)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)
    walk(obj)
    return out

def _choose_capability(instance) -> tuple[str | None, dict, list[str]]:
    description = {}
    try:
        raw = instance.describe()
        if isinstance(raw, dict):
            description = raw
    except Exception as exc:
        description = {"describe_error": repr(exc)}

    advertised = []
    seen = set()
    for name in _strings(description):
        s = name.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        low = s.lower()
        if any(token in low for token in ("3d", "render", "engineering", "physics", "cad", "blueprint")):
            advertised.append(s)

    ranked = sorted(
        advertised,
        key=lambda s: (
            0 if "scientific_3d_render" in s.lower() else
            1 if ("3d" in s.lower() and "render" in s.lower()) else
            2 if "3d" in s.lower() else
            3,
            len(s), s,
        ),
    )
    for name in list(ranked) + list(FALLBACK_CAPABILITIES):
        try:
            if bool(instance.supports(name)):
                return name, description, advertised
        except Exception:
            continue
    return None, description, advertised

def find_blender() -> str | None:
    explicit = os.environ.get("EIRA_BLENDER", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())
    return shutil.which("blender")

def provider_contract() -> dict[str, Any]:
    provider_mod = importlib.import_module(PROVIDER_MODULE)
    pkg = importlib.import_module(ENGINEERING_PACKAGE)
    provider_cls = getattr(provider_mod, "Engineering3DProvider", None)
    if not inspect.isclass(provider_cls):
        return {"ok": False, "error": "Engineering3DProvider class missing"}

    try:
        instance = provider_cls()
    except Exception as exc:
        return {"ok": False, "error": "Engineering3DProvider construction failed", "detail": repr(exc)}

    execute = getattr(instance, "execute", None)
    request_cls = _request_type(provider_mod)
    media_cls = _media_type()
    capability, description, advertised = _choose_capability(instance)

    submodules = {}
    for name in REQUIRED_SUBMODULES:
        mod = importlib.import_module(f"{ENGINEERING_PACKAGE}.{name}")
        p = Path(mod.__file__).resolve()
        submodules[name] = {"path": str(p), "sha256": _sha(p)}

    path = Path(provider_mod.__file__).resolve()
    return {
        "ok": bool(callable(execute) and request_cls and capability),
        "provider_module": PROVIDER_MODULE,
        "provider_path": str(path),
        "provider_sha256": _sha(path),
        "engineering_package": ENGINEERING_PACKAGE,
        "package_path": str(Path(pkg.__file__).resolve()),
        "required_submodules": submodules,
        "entrypoint": "Engineering3DProvider.execute",
        "entrypoint_signature": _sig(execute),
        "provider_class_signature": _sig(provider_cls),
        "request_type": None if request_cls is None else f"{request_cls.__module__}.{request_cls.__name__}",
        "request_signature": None if request_cls is None else _sig(request_cls),
        "media_type": None if media_cls is None else f"{media_cls.__module__}.{media_cls.__name__}",
        "media_signature": None if media_cls is None else _sig(media_cls),
        "capability": capability,
        "advertised_capabilities": advertised,
        "provider_description": description,
        "configured": bool(instance.configured()) if callable(getattr(instance, "configured", None)) else None,
        "blender_executable": find_blender(),
    }

def build_task(job: dict[str, Any]) -> dict[str, Any]:
    inv = plugin.get_invention(job["invention_id"])
    assets = []
    for asset in inv.get("assets", []):
        row = dict(asset)
        path = (plugin.DATA_ROOT / row["relpath"]).resolve()
        row["absolute_path"] = str(path)
        row["url"] = "/archive/" + Path(row["relpath"]).as_posix()
        assets.append(row)
    return {
        "operation": "render_invention",
        "job_id": job["job_id"],
        "invention_id": job["invention_id"],
        "mode": job["mode"],
        "title": inv["title"],
        "description": inv["description"],
        "assets": assets,
        "notes": inv.get("notes", []),
        "output_root": str((plugin.MODELS_ROOT / job["job_id"]).resolve()),
        "requested_outputs": ["blend", "glb", "gltf", "exploded_view", "animation", "turntable", "engineering_report"],
        "scene_requirements": {
            "named_parts": True,
            "part_hierarchy": True,
            "separable_components": True,
            "exploded_view_origins": True,
            "animation_tracks": True,
            "units_and_dimensions": True,
            "materials": True,
            "physics_annotations": True,
            "cross_section_ready": True,
            "transparent_shell_ready": True,
        },
        "scientific_policy": {
            "preserve_inventor_intent": True,
            "do_not_silently_invent_certainty": True,
            "record_every_inferred_gap": True,
            "distinguish_measured_estimated_inferred_speculative": True,
            "validate_physical_claims_when_possible": True,
            "dimensionally_consistent": True,
            "mathematically_sound": True,
            "material_properties_required_when_claimed": True,
            "loads_and_constraints_must_be_explicit_or_labeled_assumed": True,
        },
    }

def _construct_media(media_cls, asset: dict[str, Any]):
    path = Path(asset["absolute_path"])
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    mime = str(asset.get("mime") or "application/octet-stream")
    name = str(asset.get("name") or path.name)
    kind = "image" if mime.startswith("image/") else "document"
    sig = inspect.signature(media_cls)
    mapping = {
        "type": kind,
        "kind": kind,
        "media_type": kind,
        "mime": mime,
        "mime_type": mime,
        "content_type": mime,
        "name": name,
        "filename": name,
        "path": str(path),
        "file_path": str(path),
        "local_path": str(path),
        "url": asset.get("url"),
        "uri": asset.get("url"),
        "data": raw,
        "bytes": raw,
        "content": raw,
        "data_base64": b64,
        "base64": b64,
        "b64": b64,
        "sha256": asset.get("sha256"),
        "metadata": {
            "asset_id": asset.get("id"),
            "sha256": asset.get("sha256"),
            "source": "inventor_archive",
            "provenance": "user_uploaded",
        },
    }
    kwargs = {}
    missing = []
    for p in sig.parameters.values():
        if p.name in ("self", "cls"):
            continue
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.name in mapping and mapping[p.name] is not None:
            kwargs[p.name] = mapping[p.name]
        elif p.default is inspect._empty:
            missing.append(p.name)
    if missing:
        raise Engineering3DContractError(
            f"MediaPart required fields unresolved: {missing}; signature={sig}; asset={name}"
        )
    try:
        return media_cls(**kwargs)
    except Exception as exc:
        raise Engineering3DContractError(
            f"MediaPart construction failed: {exc!r}; signature={sig}; supplied={sorted(kwargs)}"
        ) from exc

def _media_parts(task: dict[str, Any]) -> list[Any]:
    media_cls = _media_type()
    visual_assets = [
        a for a in task["assets"]
        if str(a.get("mime") or "").startswith("image/")
        or Path(str(a.get("name") or "")).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".heic"}
    ]
    if not visual_assets:
        return []
    if media_cls is None:
        raise Engineering3DContractError("CapabilityRequest supports media but MediaPart class could not be resolved")
    return [_construct_media(media_cls, a) for a in visual_assets]

def _prompt(task: dict[str, Any]) -> str:
    return (
        "Interpret the attached inventor drawing(s) as the primary geometric evidence. "
        "Create a mathematically coherent, dimensionally consistent engineering assembly that preserves the inventor's intent. "
        "Do not treat missing dimensions, materials, loads, tolerances, or internal details as measured facts: infer only when needed, "
        "label each inference/estimate/speculation explicitly, and distinguish it from user-provided evidence. "
        "Validate geometry, interfaces, materials, motion, loads and physical claims where the available engineering tools permit. "
        "Return a structured Engineering3D assembly/blueprint suitable for parse_assembly() and Blender export. "
        f"Invention title: {task['title']}. Description: {task['description'] or '(no text description supplied)'}. "
        f"Mode: {task['mode']}."
    )

def _make_request(request_cls, capability: str, task: dict[str, Any]):
    sig = inspect.signature(request_cls)
    media = _media_parts(task)
    kwargs = {}
    missing = []
    mapping = {
        "request_id": task["job_id"],
        "capability": capability,
        "prompt": _prompt(task),
        "messages": [],
        "media": media,
        "context": {
            "source": "eira_inventor_holographic_lab",
            "job_id": task["job_id"],
            "invention_id": task["invention_id"],
            "title": task["title"],
            "assets": task["assets"],
            "notes": task["notes"],
        },
        "options": task,
        "mutation_authorized": False,
        "name": capability,
        "operation": task["operation"],
        "action": task["operation"],
        "task": task,
        "payload": task,
        "data": task,
        "input": task,
        "arguments": task,
        "args": task,
        "params": task,
        "parameters": task,
        "metadata": {
            "source": "eira_inventor_holographic_lab",
            "job_id": task["job_id"],
            "invention_id": task["invention_id"],
        },
        "job_id": task["job_id"],
        "text": _prompt(task),
    }
    for p in sig.parameters.values():
        if p.name in ("self", "cls"):
            continue
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.name in mapping:
            kwargs[p.name] = mapping[p.name]
        elif p.default is inspect._empty:
            missing.append(p.name)
    if missing:
        raise Engineering3DContractError(
            f"CapabilityRequest required fields unresolved: {missing}; signature={sig}"
        )
    try:
        return request_cls(**kwargs), len(media)
    except Exception as exc:
        raise Engineering3DContractError(
            f"CapabilityRequest construction failed: {exc!r}; signature={sig}; supplied={sorted(kwargs)}"
        ) from exc

def invoke(job: dict[str, Any]) -> dict[str, Any]:
    contract = provider_contract()
    if not contract.get("ok"):
        raise Engineering3DContractError(
            "engineering3d provider contract unresolved: " + json.dumps(contract, default=str)
        )

    provider_mod = importlib.import_module(PROVIDER_MODULE)
    provider_cls = getattr(provider_mod, "Engineering3DProvider")
    instance = provider_cls()
    request_cls = _request_type(provider_mod)
    task = build_task(job)
    request, media_count = _make_request(request_cls, contract["capability"], task)

    started = time.time()
    result = instance.execute(request)
    receipt = {
        "job_id": job["job_id"],
        "provider": contract,
        "task": task,
        "media_count": media_count,
        "request_repr": repr(request),
        "result": result,
        "started": started,
        "finished": time.time(),
    }
    out = plugin.JOBS_ROOT / f"{job['job_id']}_engineering3d_receipt.json"
    out.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return {
        "ok": True,
        "receipt": str(out),
        "provider_result": result,
        "provider": contract,
        "task": task,
        "media_count": media_count,
    }

def _candidate_objects(value):
    seen = set()
    def walk(v):
        oid = id(v)
        if oid in seen:
            return
        seen.add(oid)
        if isinstance(v, dict):
            preferred = ("assembly", "blueprint", "model", "design", "data", "result", "output", "payload")
            for k in preferred:
                if k in v:
                    yield v[k]
            yield v
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from walk(x)
        else:
            yield v
    yield from walk(value)

def parse_provider_assembly(provider_result):
    pkg = importlib.import_module(ENGINEERING_PACKAGE)
    parse_assembly = getattr(pkg, "parse_assembly", None)
    if not callable(parse_assembly):
        schema_mod = importlib.import_module(f"{ENGINEERING_PACKAGE}.schema")
        parse_assembly = getattr(schema_mod, "parse_assembly", None)
    if not callable(parse_assembly):
        raise Engineering3DContractError("Engineering3D parse_assembly() is unavailable")

    errors = []
    for candidate in _candidate_objects(provider_result):
        try:
            assembly = parse_assembly(candidate)
            if assembly is not None:
                return assembly
        except Exception as exc:
            if len(errors) < 8:
                errors.append(f"{type(exc).__name__}:{str(exc)[:180]}")
    raise Engineering3DContractError(
        "Engineering3D provider returned no parseable Assembly; attempts=" + json.dumps(errors)
    )

def render_with_blender(job: dict[str, Any], provider_result) -> dict[str, Any]:
    blender = find_blender()
    if not blender:
        raise Engineering3DContractError(
            "Blender executable not found on the Pi. Install/configure Blender or set EIRA_BLENDER to its executable path."
        )
    assembly = parse_provider_assembly(provider_result)
    pkg = importlib.import_module(ENGINEERING_PACKAGE)
    writer = getattr(pkg, "write_blueprint_package", None)
    if not callable(writer):
        export_mod = importlib.import_module(f"{ENGINEERING_PACKAGE}.export")
        writer = getattr(export_mod, "write_blueprint_package", None)
    if not callable(writer):
        raise Engineering3DContractError("Engineering3D write_blueprint_package() is unavailable")

    out_dir = (plugin.MODELS_ROOT / job["job_id"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    package_result = writer(
        assembly,
        str(out_dir),
        render_blender=True,
        blender_executable=blender,
    )
    files = []
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(plugin.DATA_ROOT).as_posix()
            files.append({
                "name": p.name,
                "path": str(p),
                "url": "/archive/" + rel,
                "suffix": p.suffix.lower(),
                "sha256": _sha(p),
                "size": p.stat().st_size,
            })
    glb = next((f for f in files if f["suffix"] == ".glb"), None)
    gltf = next((f for f in files if f["suffix"] == ".gltf"), None)
    blend = next((f for f in files if f["suffix"] == ".blend"), None)
    model = glb or gltf
    if model is None:
        raise Engineering3DContractError(
            "Blender/Engineering3D package completed without producing a .glb or .gltf model"
        )
    return {
        "ok": True,
        "blender": blender,
        "output_dir": str(out_dir),
        "package_result": package_result,
        "files": files,
        "model_url": model["url"],
        "model_path": model["path"],
        "blend_url": None if blend is None else blend["url"],
        "blend_path": None if blend is None else blend["path"],
        "started": started,
        "finished": time.time(),
    }
