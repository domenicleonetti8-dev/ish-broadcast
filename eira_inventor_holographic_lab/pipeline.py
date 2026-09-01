from __future__ import annotations

import json
import shutil
import subprocess
import time
import traceback
from pathlib import Path

from .provider import ollama_vision
from .compiler import compile_assembly
from .blender_backend import generate_blender_script
from .quality import inspect_scene, require_quality
from .preview import generate_preview_script, preview_paths
from .review import review_render, repair_assembly

TERMINAL={"completed","failed","cancelled"}


def _write_json(path: Path, value):
    path.write_text(json.dumps(value,indent=2,default=str))


def _run_blender(blender,script,stdout_path,stderr_path,timeout_s):
    cp=subprocess.run([blender,"-b","--python",str(script)],capture_output=True,text=True,timeout=int(timeout_s))
    stdout_path.write_text(cp.stdout or "")
    stderr_path.write_text(cp.stderr or "")
    if cp.returncode!=0:
        raise RuntimeError(f"blender_failed:returncode={cp.returncode}")
    return cp


def _expand_geometry(compiled):
    from .geometry import mesh_from_geometry
    for p in compiled["parts"]:
        if p["geometry"]["kind"] in {"instance","boolean","primitive","mesh","curve"}:
            continue
        m=mesh_from_geometry(p["geometry"])
        p["geometry"]={"kind":"mesh","vertices":m.vertices.tolist(),"faces":m.faces.tolist()}


def run_job(job,image_path,user_text,out_dir,vision=ollama_vision,blender="blender"):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); trace=[]
    def stage(s,**kw):
        now=time.time(); trace.append({"status":s,"t":now}); job.update(status=s,updated=now,**kw)
        _write_json(out/"job.json",job); _write_json(out/"lifecycle_trace.json",trace)

    max_attempts=max(1,min(int(job.get("repair_attempts",3)),6))
    visual_review_enabled=bool(job.get("visual_review",True))
    review_model=str(job.get("review_model","gemma3:4b"))
    review_threshold=float(job.get("visual_review_threshold",0.82))
    review_timeout=int(job.get("visual_review_timeout_s",900))
    blender_timeout=int(job.get("blender_timeout_s",900))

    try:
        stage("starting")
        stage("vision_running")
        assembly=vision(image_path,user_text)
        _write_json(out/"vision_ir.json",assembly)

        last_quality=None
        last_review=None
        for attempt in range(1,max_attempts+1):
            attempt_dir=out/f"attempt_{attempt:02d}"
            attempt_dir.mkdir(parents=True,exist_ok=True)
            _write_json(attempt_dir/"candidate_ir.json",assembly)

            stage("engineering_compiling",attempt=attempt,max_attempts=max_attempts)
            compiled,scene=compile_assembly(assembly,duration_s=float(job.get("duration_s",10)),fps=int(job.get("fps",24)))
            _write_json(attempt_dir/"compiled_ir.json",compiled)
            _write_json(attempt_dir/"engineering_report.json",{
                "summary":compiled.get("engineering_summary"),
                "quantities":compiled.get("calculated_quantities"),
                "diagrams":compiled.get("diagram_layer"),
            })

            stage("geometry_quality_check",attempt=attempt)
            quality=inspect_scene(
                compiled,scene,
                support_gap_m=float(job.get("support_gap_m",0.035)),
                forbidden_overlap_m3=float(job.get("forbidden_overlap_m3",1e-6)),
            )
            compiled["geometry_quality"]=quality
            last_quality=quality
            _write_json(attempt_dir/"geometry_quality.json",quality)

            # Deterministic defects are repair evidence, not an excuse to ship a bad model.
            if not quality.get("ok"):
                if attempt>=max_attempts:
                    require_quality(quality)
                stage("geometry_repairing",attempt=attempt)
                assembly=repair_assembly(
                    image_path,[],assembly,
                    {"pass":False,"scores":{},"issues":quality.get("issues",[]),"summary":"Deterministic geometry QA failed before render."},
                    quality,
                    model=review_model,timeout=review_timeout,
                )
                _write_json(attempt_dir/"repaired_ir.json",assembly)
                continue

            stage("geometry_expanding",attempt=attempt)
            render_ir=json.loads(json.dumps(compiled))
            _expand_geometry(render_ir)
            glb=attempt_dir/"assembly.glb"
            script=attempt_dir/"assembly_blender.py"
            script.write_text(generate_blender_script(render_ir,str(glb)))

            stage("blender_running",attempt=attempt)
            _run_blender(
                blender,script,
                attempt_dir/"blender.stdout.txt",
                attempt_dir/"blender.stderr.txt",
                blender_timeout,
            )
            if not glb.exists() or glb.stat().st_size<=0:
                raise RuntimeError("blender_failed:no_glb")

            stage("preview_rendering",attempt=attempt)
            preview_dir=attempt_dir/"previews"
            preview_dir.mkdir(exist_ok=True)
            preview_script=attempt_dir/"preview_blender.py"
            preview_script.write_text(generate_preview_script(str(glb),str(preview_dir),resolution=int(job.get("preview_resolution",640))))
            _run_blender(
                blender,preview_script,
                attempt_dir/"preview.stdout.txt",
                attempt_dir/"preview.stderr.txt",
                blender_timeout,
            )
            previews=preview_paths(str(preview_dir))
            missing=[p for p in previews if not Path(p).exists()]
            if missing:
                raise RuntimeError(f"preview_failed:missing={missing}")

            if visual_review_enabled:
                stage("visual_reviewing",attempt=attempt)
                review=review_render(
                    image_path,previews,render_ir,
                    model=review_model,timeout=review_timeout,threshold=review_threshold,
                )
                last_review=review
                _write_json(attempt_dir/"visual_review.json",review)
                if not review.get("pass"):
                    if attempt>=max_attempts:
                        raise RuntimeError(f"visual_review_failed:min_score={review.get('minimum_score')}")
                    stage("visual_repairing",attempt=attempt,min_score=review.get("minimum_score"))
                    assembly=repair_assembly(
                        image_path,previews,assembly,review,quality,
                        model=review_model,timeout=review_timeout,
                    )
                    _write_json(attempt_dir/"repaired_ir.json",assembly)
                    continue

            # Promote only a geometry-clean, preview-rendered, visually accepted attempt.
            final_glb=out/"assembly.glb"
            shutil.copy2(glb,final_glb)
            final_preview_dir=out/"previews"
            if final_preview_dir.exists(): shutil.rmtree(final_preview_dir)
            shutil.copytree(preview_dir,final_preview_dir)
            _write_json(out/"compiled_ir.json",compiled)
            _write_json(out/"geometry_quality.json",quality)
            if last_review is not None: _write_json(out/"visual_review.json",last_review)
            _write_json(out/"engineering_report.json",{
                "summary":compiled.get("engineering_summary"),
                "quantities":compiled.get("calculated_quantities"),
                "diagrams":compiled.get("diagram_layer"),
            })
            stage(
                "completed",
                attempt=attempt,
                model_url=str(final_glb),
                engineering_report=str(out/"engineering_report.json"),
                geometry_quality=str(out/"geometry_quality.json"),
                visual_review=str(out/"visual_review.json") if last_review is not None else None,
                preview_dir=str(final_preview_dir),
            )
            return job

        raise RuntimeError("repair_loop_exhausted_without_terminal_result")
    except Exception as exc:
        stage("failed",error=f"{type(exc).__name__}:{exc}",traceback=traceback.format_exc(),last_quality=last_quality,last_review=last_review)
        return job
