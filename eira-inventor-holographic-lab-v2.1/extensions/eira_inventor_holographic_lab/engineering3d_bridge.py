from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import time
from pathlib import Path
from typing import Any

from . import plugin

PROVIDER_MODULE = "extensions.unified_brain_ai.providers.engineering3d"
ENGINEERING_PACKAGE = "extensions.unified_brain_ai.engineering3d"
PROVIDER_BASE = "extensions.unified_brain_ai.provider_base"
REQUIRED_SUBMODULES = ("schema", "validate", "exploded", "export", "materials", "physics")
CAPABILITY_CANDIDATES = ("engineering3d", "engineering_3d", "3d_engineering", "3d")

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
    try:
        base = importlib.import_module(PROVIDER_BASE)
    except Exception:
        return None
    cls = getattr(base, "CapabilityRequest", None)
    return cls if inspect.isclass(cls) else None

def _choose_capability(instance) -> tuple[str | None, dict]:
    description = {}
    try:
        raw = instance.describe()
        if isinstance(raw, dict):
            description = raw
    except Exception as exc:
        description = {"describe_error": repr(exc)}
    for name in CAPABILITY_CANDIDATES:
        try:
            if bool(instance.supports(name)):
                return name, description
        except Exception:
            continue
    return None, description

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
    capability, description = _choose_capability(instance)

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
        "capability": capability,
        "provider_description": description,
        "configured": bool(instance.configured()) if callable(getattr(instance, "configured", None)) else None,
    }

def build_task(job: dict[str, Any]) -> dict[str, Any]:
    inv = plugin.get_invention(job["invention_id"])
    return {
        "operation": "render_invention",
        "job_id": job["job_id"],
        "invention_id": job["invention_id"],
        "mode": job["mode"],
        "title": inv["title"],
        "description": inv["description"],
        "assets": inv.get("assets", []),
        "notes": inv.get("notes", []),
        "output_root": str(plugin.MODELS_ROOT.resolve()),
        "requested_outputs": ["blend", "glb", "gltf", "exploded_view", "animation", "turntable"],
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
        },
    }

def _make_request(request_cls, capability: str, task: dict[str, Any]):
    sig = inspect.signature(request_cls)
    kwargs = {}
    missing = []
    mapping = {
        "capability": capability,
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
        "options": task,
        "context": {"source": "eira_inventor_holographic_lab", "job_id": task["job_id"]},
        "metadata": {"source": "eira_inventor_holographic_lab", "job_id": task["job_id"], "invention_id": task["invention_id"]},
        "request_id": task["job_id"],
        "job_id": task["job_id"],
        "prompt": task["description"],
        "text": task["description"],
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
        return request_cls(**kwargs)
    except Exception as exc:
        raise Engineering3DContractError(
            f"CapabilityRequest construction failed: {exc!r}; signature={sig}; supplied={sorted(kwargs)}"
        ) from exc

def invoke(job: dict[str, Any]) -> dict[str, Any]:
    contract = provider_contract()
    if not contract.get("ok"):
        raise Engineering3DContractError("engineering3d provider contract unresolved: " + json.dumps(contract, default=str))

    provider_mod = importlib.import_module(PROVIDER_MODULE)
    provider_cls = getattr(provider_mod, "Engineering3DProvider")
    instance = provider_cls()
    request_cls = _request_type(provider_mod)
    task = build_task(job)
    request = _make_request(request_cls, contract["capability"], task)

    started = time.time()
    result = instance.execute(request)
    receipt = {
        "job_id": job["job_id"],
        "provider": contract,
        "task": task,
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
    }
