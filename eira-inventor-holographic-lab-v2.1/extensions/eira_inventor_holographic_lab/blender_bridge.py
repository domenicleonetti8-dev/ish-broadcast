from __future__ import annotations

import json
import time

from . import plugin
from .engineering3d_bridge import invoke, provider_contract, render_with_blender

def next_jobs():
    plugin._init()
    for p in sorted(plugin.JOBS_ROOT.glob("render_*.json")):
        if p.name.endswith("_engineering3d_receipt.json"):
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if obj.get("status") == "queued":
                yield p, obj
        except Exception:
            continue

def mark(path, obj, status, **extra):
    obj.update(extra)
    obj["status"] = status
    obj["updated"] = time.time()
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")

def run_once():
    jobs = list(next_jobs())
    if not jobs:
        return {"ok": True, "processed": 0, "provider": provider_contract()}

    p, job = jobs[0]
    mark(p, job, "engineering3d_dispatched")
    try:
        engineering = invoke(job)
        mark(
            p,
            job,
            "engineering3d_completed",
            engineering3d={
                "receipt": engineering.get("receipt"),
                "media_count": engineering.get("media_count"),
                "provider": engineering.get("provider"),
            },
        )
        mark(p, job, "blender_rendering")
        blender = render_with_blender(job, engineering.get("provider_result"))
    except Exception as exc:
        error = f"{type(exc).__name__}:{str(exc)[:1600]}"
        mark(p, job, "failed", error=error)
        return {
            "ok": False,
            "processed": 1,
            "job": job["job_id"],
            "status": "failed",
            "error": error,
        }

    mark(
        p,
        job,
        "completed",
        engineering3d={
            "receipt": engineering.get("receipt"),
            "media_count": engineering.get("media_count"),
            "provider": engineering.get("provider"),
        },
        blender=blender,
        model_url=blender["model_url"],
        blend_url=blender.get("blend_url"),
    )
    return {
        "ok": True,
        "processed": 1,
        "job": job["job_id"],
        "status": "completed",
        "media_count": engineering.get("media_count"),
        "model_url": blender["model_url"],
        "blend_url": blender.get("blend_url"),
        "files": blender.get("files", []),
        "provider": engineering.get("provider"),
        "blender": {
            "executable": blender.get("blender"),
            "output_dir": blender.get("output_dir"),
        },
    }

if __name__ == "__main__":
    print(json.dumps(run_once(), indent=2, default=str))
