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
CALLABLE_PRIORITY = ("ask", "execute", "run", "handle")

class Engineering3DContractError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provider_contract() -> dict[str, Any]:
    provider = importlib.import_module(PROVIDER_MODULE)
    pkg = importlib.import_module(ENGINEERING_PACKAGE)
    submodules = {}
    for name in REQUIRED_SUBMODULES:
        mod = importlib.import_module(f"{ENGINEERING_PACKAGE}.{name}")
        p = Path(mod.__file__).resolve()
        submodules[name] = {"path": str(p), "sha256": _sha(p)}
    path = Path(provider.__file__).resolve()
    callables = []
    for name, value in vars(provider).items():
        if name.startswith("_") or not callable(value):
            continue
        try:
            sig = str(inspect.signature(value))
        except Exception:
            sig = "<?>"
        callables.append({"name": name, "signature": sig})
    entry = next((n for n in CALLABLE_PRIORITY if callable(getattr(provider, n, None))), None)
    return {
        "ok": bool(entry),
        "provider_module": PROVIDER_MODULE,
        "provider_path": str(path),
        "provider_sha256": _sha(path),
        "engineering_package": ENGINEERING_PACKAGE,
        "package_path": str(Path(pkg.__file__).resolve()),
        "required_submodules": submodules,
        "entrypoint": entry,
        "public_callables": sorted(callables, key=lambda x: x["name"]),
    }


def _invoke(fn, task: dict[str, Any]):
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    required = [p for p in params if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if any(p.kind == p.VAR_KEYWORD for p in params):
        return fn(task=task)
    if len(required) <= 1:
        return fn(task)
    raise Engineering3DContractError(f"unsupported engineering3d entrypoint signature: {sig}")


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


def invoke(job: dict[str, Any]) -> dict[str, Any]:
    contract = provider_contract()
    if not contract["ok"]:
        raise Engineering3DContractError("engineering3d provider exists but exposes no supported verified callable")
    provider = importlib.import_module(PROVIDER_MODULE)
    fn = getattr(provider, contract["entrypoint"])
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
    return {"ok": True, "receipt": str(out), "provider_result": result, "provider": contract}
