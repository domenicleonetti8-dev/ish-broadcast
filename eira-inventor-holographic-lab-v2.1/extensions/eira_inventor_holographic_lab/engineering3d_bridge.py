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
REQUIRED_SUBMODULES = ("schema", "validate", "exploded", "export", "materials", "physics")
METHOD_PRIORITY = ("ask", "execute", "run", "handle", "invoke", "render", "generate")
OBJECT_HINTS = ("provider", "engine", "service", "adapter", "client")

class Engineering3DContractError(RuntimeError):
    pass

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _public_callables(obj):
    rows = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if not callable(value):
            continue
        try:
            sig = str(inspect.signature(value))
        except Exception:
            sig = "<?>"
        rows.append({"name": name, "signature": sig})
    return sorted(rows, key=lambda x: x["name"])

def _zero_arg_instance(cls):
    try:
        sig = inspect.signature(cls)
        required = [
            p for p in sig.parameters.values()
            if p.default is inspect._empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if required:
            return None
        return cls()
    except Exception:
        return None

def _discover_target():
    modules = [
        ("provider_module", importlib.import_module(PROVIDER_MODULE)),
        ("engineering_package", importlib.import_module(ENGINEERING_PACKAGE)),
    ]

    for scope, mod in modules:
        for method in METHOD_PRIORITY:
            fn = getattr(mod, method, None)
            if callable(fn) and not inspect.isclass(fn):
                return {
                    "scope": scope,
                    "target_kind": "module_function",
                    "target_name": mod.__name__,
                    "method": method,
                }, fn

    for scope, mod in modules:
        names = list(vars(mod))
        names.sort(key=lambda n: (0 if any(h in n.lower() for h in OBJECT_HINTS) else 1, n.lower()))
        for name in names:
            if name.startswith("_"):
                continue
            try:
                obj = getattr(mod, name)
            except Exception:
                continue
            if inspect.ismodule(obj) or inspect.isfunction(obj):
                continue
            if inspect.isclass(obj):
                obj = _zero_arg_instance(obj)
                if obj is None:
                    continue
                kind = "class_instance"
            else:
                kind = "object"
            for method in METHOD_PRIORITY:
                fn = getattr(obj, method, None)
                if callable(fn):
                    return {
                        "scope": scope,
                        "target_kind": kind,
                        "target_name": name,
                        "target_class": type(obj).__name__,
                        "method": method,
                    }, fn

    return None, None

def provider_contract() -> dict[str, Any]:
    provider = importlib.import_module(PROVIDER_MODULE)
    pkg = importlib.import_module(ENGINEERING_PACKAGE)
    submodules = {}
    for name in REQUIRED_SUBMODULES:
        mod = importlib.import_module(f"{ENGINEERING_PACKAGE}.{name}")
        p = Path(mod.__file__).resolve()
        submodules[name] = {"path": str(p), "sha256": _sha(p)}

    path = Path(provider.__file__).resolve()
    target, fn = _discover_target()
    signature = None
    if fn is not None:
        try:
            signature = str(inspect.signature(fn))
        except Exception:
            signature = "<?>"

    return {
        "ok": bool(target and fn),
        "provider_module": PROVIDER_MODULE,
        "provider_path": str(path),
        "provider_sha256": _sha(path),
        "engineering_package": ENGINEERING_PACKAGE,
        "package_path": str(Path(pkg.__file__).resolve()),
        "required_submodules": submodules,
        "entrypoint": None if not target else f"{target['scope']}:{target['target_name']}.{target['method']}",
        "target": target,
        "entrypoint_signature": signature,
        "provider_public_callables": _public_callables(provider),
        "package_public_callables": _public_callables(pkg),
    }

def _invoke(fn, task: dict[str, Any]):
    try:
        sig = inspect.signature(fn)
    except Exception:
        return fn(task)

    params = list(sig.parameters.values())
    normal = [
        p for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]
    required = [p for p in normal if p.default is inspect._empty]
    names = {p.name for p in normal}

    if any(p.kind == p.VAR_KEYWORD for p in params):
        return fn(task=task)
    if "task" in names:
        return fn(task=task)
    if "request" in names:
        return fn(request=task)
    if "payload" in names:
        return fn(payload=task)
    if "data" in names and len(required) <= 1:
        return fn(data=task)
    if len(required) <= 1:
        return fn(task)
    raise Engineering3DContractError(
        f"unsupported engineering3d entrypoint signature: {sig}"
    )

def build_task(job: dict[str, Any]) -> dict[str, Any]:
    inv = plugin.get_invention(job["invention_id"])
    return {
        "operation": "render_invention",
        "capability": "engineering3d",
        "job_id": job["job_id"],
        "invention_id": job["invention_id"],
        "mode": job["mode"],
        "title": inv["title"],
        "description": inv["description"],
        "assets": inv.get("assets", []),
        "notes": inv.get("notes", []),
        "output_root": str(plugin.MODELS_ROOT.resolve()),
        "requested_outputs": [
            "blend", "glb", "gltf", "exploded_view", "animation", "turntable"
        ],
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

def invoke(job: dict[str, Any]) -> dict[str, Any]:
    contract = provider_contract()
    if not contract["ok"]:
        raise Engineering3DContractError(
            "engineering3d provider exists but exposes no supported verified callable"
        )

    _, fn = _discover_target()
    if fn is None:
        raise Engineering3DContractError("engineering3d target disappeared after discovery")

    task = build_task(job)
    started = time.time()
    result = _invoke(fn, task)
    receipt = {
        "job_id": job["job_id"],
        "provider": contract,
        "task": task,
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
