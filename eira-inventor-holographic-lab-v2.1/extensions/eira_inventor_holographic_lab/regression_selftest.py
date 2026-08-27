from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import inspect
import json
import subprocess
import tempfile
import time
from pathlib import Path

from . import plugin
from . import engineering3d_bridge as bridge

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

VISIBLE_CONTROLS = {
    "create": "$('create').onclick",
    "files": "$('files').onchange",
    "interact": "$('interact').onclick",
    "reset": "$('reset').onclick",
    "play": "$('play').onclick",
    "explode": "$('explode').onclick",
    "assemble": "$('assemble').onclick",
    "isolate": "$('isolate').onclick",
    "show": "$('show').onclick",
    "transparent": "$('transparent').onclick",
    "section": "$('section').onclick",
    "render": "$('render').onclick",
    "send": "$('send').onclick",
    "mute": "$('mute').onclick",
}


def fail(name: str, detail: str = ""):
    raise RuntimeError(f"{name}: {detail}" if detail else name)


def check_python_compile(results: list[dict]):
    root = Path(__file__).resolve().parent
    for name in ("plugin.py", "server.py", "engineering3d_bridge.py", "blender_bridge.py", "regression_selftest.py"):
        p = root / name
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
    results.append({"test": "python_compile", "ok": True})


def check_ui_contract(results: list[dict]):
    html = (Path(__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")
    missing = []
    for cid, handler in VISIBLE_CONTROLS.items():
        if f'id="{cid}"' not in html or handler not in html:
            missing.append(cid)
    for required in (
        "function requireWorld",
        "function userAction",
        "function setModelControls",
        "function applyTransparency",
        "function toggleSection",
        "load3d",
        "pollJob",
        "Interact with 3D",
    ):
        if required not in html:
            missing.append(required)
    if missing:
        fail("ui_contract", ",".join(missing))
    results.append({"test": "ui_contract", "ok": True, "controls": sorted(VISIBLE_CONTROLS)})


def check_provider_contract(results: list[dict]):
    c = bridge.provider_contract()
    if not c.get("ok"):
        fail("engineering3d_contract", json.dumps(c, default=str))
    if not c.get("media_type"):
        fail("media_part_missing")
    if not c.get("blender_executable"):
        fail("blender_missing")
    results.append({
        "test": "engineering3d_contract",
        "ok": True,
        "capability": c.get("capability"),
        "media_type": c.get("media_type"),
        "blender": c.get("blender_executable"),
    })
    return c


def check_media_construction(results: list[dict]):
    media_cls = bridge._media_type()
    if media_cls is None:
        fail("media_type_unresolved")
    with tempfile.TemporaryDirectory(prefix="eira_lab_media_") as td:
        p = Path(td) / "drawing.png"
        p.write_bytes(PNG_1X1)
        asset = {
            "id": "asset_regression",
            "name": p.name,
            "mime": "image/png",
            "absolute_path": str(p),
            "url": "/archive/regression/drawing.png",
            "sha256": hashlib.sha256(PNG_1X1).hexdigest(),
        }
        media = bridge._construct_media(media_cls, asset)
        if getattr(media, "path", None) != str(p):
            fail("media_path_not_preserved", repr(media))
        if getattr(media, "mime_type", "image/png") != "image/png":
            fail("media_mime_not_preserved", repr(media))
    results.append({"test": "media_construction", "ok": True})


def _construct(cls, mapping: dict):
    sig = inspect.signature(cls)
    kwargs = {}
    missing = []
    for p in sig.parameters.values():
        if p.name in ("self", "cls") or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.name in mapping:
            kwargs[p.name] = mapping[p.name]
        elif p.default is inspect._empty:
            missing.append(p.name)
    if missing:
        fail("fixture_constructor", f"{cls.__name__} unresolved required fields {missing}; signature={sig}")
    return cls(**kwargs)


def _blender_export_glb(blender: str, blend: Path, glb: Path):
    expr = (
        "import bpy; "
        f"bpy.ops.export_scene.gltf(filepath={str(glb)!r}, export_format='GLB')"
    )
    cp = subprocess.run(
        [blender, "-b", str(blend), "--python-expr", expr],
        text=True,
        capture_output=True,
        timeout=300,
    )
    if cp.returncode != 0 or not glb.is_file() or glb.stat().st_size <= 0:
        fail(
            "blender_glb_export",
            f"returncode={cp.returncode}; stderr={cp.stderr[-1400:]!r}; stdout={cp.stdout[-800:]!r}",
        )


def check_blender_smoke(results: list[dict], contract: dict):
    blender = contract.get("blender_executable")
    pkg = importlib.import_module("extensions.unified_brain_ai.engineering3d")
    Assembly = getattr(pkg, "Assembly")
    Part = getattr(pkg, "Part")
    Vec3 = getattr(pkg, "Vec3")
    write_blueprint_package = getattr(pkg, "write_blueprint_package")
    with tempfile.TemporaryDirectory(prefix="eira_lab_blender_") as td:
        out = Path(td) / "model"
        out.mkdir()
        part = _construct(Part, {
            "part_id": "regression_box",
            "id": "regression_box",
            "name": "Regression Box",
            "shape": "box",
            "size": Vec3(1.0, 0.6, 0.4),
            "position": Vec3(0, 0, 0),
            "rotation_deg": Vec3(0, 0, 0),
            "material": "aluminum",
            "metadata": {"provenance": "regression_fixture"},
            "color": "#88aacc",
        })
        assembly = _construct(Assembly, {
            "assembly_id": "regression_assembly",
            "id": "regression_assembly",
            "name": "Regression Assembly",
            "parts": [part],
            "connectors": [],
            "fasteners": [],
            "wires": [],
            "metadata": {"provenance": "regression_fixture"},
        })
        produced = write_blueprint_package(
            assembly,
            str(out),
            render_blender=True,
            blender_executable=blender,
        )
        if not isinstance(produced, dict) or not produced.get("ok"):
            fail("engineering3d_blender_package", repr(produced))
        files = [p for p in out.rglob("*") if p.is_file()]
        blends = [p for p in files if p.suffix.lower() == ".blend" and p.stat().st_size > 0]
        if not blends:
            fail("blender_blend_smoke", "no nonempty .blend produced; return=" + repr(produced))
        glb = out / "assembly.glb"
        _blender_export_glb(blender, blends[0], glb)
        results.append({
            "test": "blender_glb_smoke",
            "ok": True,
            "glb_bytes": glb.stat().st_size,
            "glb_name": glb.name,
            "blend_present": True,
        })


def _latest_real_drawing():
    try:
        inventions = plugin.list_inventions()
    except Exception:
        return None
    for inv_row in inventions:
        try:
            inv = plugin.get_invention(inv_row["id"])
        except Exception:
            continue
        for asset in reversed(inv.get("assets", [])):
            mime = str(asset.get("mime") or "")
            suffix = Path(str(asset.get("name") or "")).suffix.lower()
            if mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".heic"}:
                p = (plugin.DATA_ROOT / asset["relpath"]).resolve()
                if p.is_file() and p.stat().st_size > 0:
                    return {
                        "bytes": p.read_bytes(),
                        "name": asset.get("name") or p.name,
                        "mime": mime or "image/jpeg",
                        "source_invention": inv.get("title"),
                    }
    return None


def _swap_archive(tmp: Path):
    original = {
        "DATA_ROOT": plugin.DATA_ROOT,
        "FILES_ROOT": plugin.FILES_ROOT,
        "MODELS_ROOT": plugin.MODELS_ROOT,
        "JOBS_ROOT": plugin.JOBS_ROOT,
        "DB_PATH": plugin.DB_PATH,
    }
    plugin.DATA_ROOT = tmp
    plugin.FILES_ROOT = tmp / "files"
    plugin.MODELS_ROOT = tmp / "models"
    plugin.JOBS_ROOT = tmp / "jobs"
    plugin.DB_PATH = tmp / "inventor_archive.sqlite3"
    plugin._init()
    return original


def _restore_archive(original: dict):
    for k, v in original.items():
        setattr(plugin, k, v)


def check_full_worker(results: list[dict], timeout: int):
    source = _latest_real_drawing()
    if source is None:
        source = {"bytes": PNG_1X1, "name": "regression.png", "mime": "image/png", "source_invention": "fixture"}
    with tempfile.TemporaryDirectory(prefix="eira_lab_full_") as td:
        original = _swap_archive(Path(td))
        try:
            inv = plugin.create_invention(
                "Regression Greenhouse",
                "A sealed three-dimensional off-world greenhouse module. Interpret the attached drawing as primary geometric evidence. Produce a coherent 3D engineering assembly; label every inferred dimension, material, load, tolerance, and hidden component as an assumption unless it is present in the drawing or description.",
            )
            plugin.add_asset(inv["id"], source["name"], source["mime"], source["bytes"])
            job = plugin.queue_render(inv["id"], "scientific_plausibility")
            started = time.time()
            result = plugin.process_next_render()
            elapsed = time.time() - started
            final = plugin.get_job(job["job_id"])
            if elapsed > timeout:
                fail("full_worker_timeout", f"{elapsed:.1f}s > {timeout}s")
            if final.get("status") != "completed":
                fail("full_worker", final.get("error") or json.dumps(result, default=str))
            if not final.get("model_url"):
                fail("full_worker_model_url_missing")
            media_count = ((final.get("engineering3d") or {}).get("media_count"))
            if not media_count or int(media_count) < 1:
                fail("full_worker_media_count", repr(media_count))
            model_rel = str(final["model_url"]).removeprefix("/archive/")
            model_path = plugin.DATA_ROOT / model_rel
            if not model_path.is_file() or model_path.stat().st_size <= 0:
                fail("full_worker_glb_missing", str(model_path))
            parts = []
            for candidate in (final.get("blender") or {}).get("files", []):
                parts.append(str(candidate))
            results.append({
                "test": "full_worker",
                "ok": True,
                "elapsed_seconds": round(elapsed, 2),
                "media_count": media_count,
                "model_bytes": model_path.stat().st_size,
                "model_url": final.get("model_url"),
                "blend_url": final.get("blend_url"),
                "source_drawing": source.get("source_invention"),
                "artifacts": parts,
            })
        finally:
            _restore_archive(original)


def run(full: bool = False, timeout: int = 300) -> dict:
    results: list[dict] = []
    started = time.time()
    check_python_compile(results)
    check_ui_contract(results)
    contract = check_provider_contract(results)
    check_media_construction(results)
    check_blender_smoke(results, contract)
    if full:
        check_full_worker(results, timeout)
    return {
        "ok": True,
        "mode": "full" if full else "fast",
        "tests": results,
        "elapsed_seconds": round(time.time() - started, 2),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()
    try:
        report = run(args.full, args.timeout)
        print(json.dumps(report, indent=2, default=str))
        print("INVENTOR_LAB_REGRESSION=PASS")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, indent=2))
        print("INVENTOR_LAB_REGRESSION=FAIL")
        raise SystemExit(1)
