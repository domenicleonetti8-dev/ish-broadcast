from __future__ import annotations
import json, subprocess, time, traceback
from pathlib import Path
from .provider import ollama_vision
from .compiler import compile_assembly
from .blender_backend import generate_blender_script

TERMINAL={"completed","failed","cancelled"}

def run_job(job,image_path,user_text,out_dir,vision=ollama_vision,blender="blender"):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); trace=[]
    def stage(s,**kw):
        now=time.time(); trace.append({"status":s,"t":now}); job.update(status=s,updated=now,**kw)
        (out/"job.json").write_text(json.dumps(job,indent=2,default=str)); (out/"lifecycle_trace.json").write_text(json.dumps(trace,indent=2))
    try:
        stage("starting"); stage("vision_running")
        assembly=vision(image_path,user_text); (out/"vision_ir.json").write_text(json.dumps(assembly,indent=2))
        stage("engineering_compiling")
        compiled,scene=compile_assembly(assembly,duration_s=float(job.get("duration_s",10)),fps=int(job.get("fps",24)))
        (out/"compiled_ir.json").write_text(json.dumps(compiled,indent=2))
        (out/"engineering_report.json").write_text(json.dumps({"summary":compiled.get("engineering_summary"),"quantities":compiled.get("calculated_quantities"),"diagrams":compiled.get("diagram_layer")},indent=2))
        stage("geometry_expanding")
        for p in compiled["parts"]:
            if p["geometry"]["kind"] in {"instance","boolean","primitive","mesh","curve"}: continue
            from .geometry import mesh_from_geometry
            m=mesh_from_geometry(p["geometry"]); p["geometry"]={"kind":"mesh","vertices":m.vertices.tolist(),"faces":m.faces.tolist()}
        glb=out/"assembly.glb"; script=out/"assembly_blender.py"; script.write_text(generate_blender_script(compiled,str(glb)))
        stage("blender_running")
        cp=subprocess.run([blender,"-b","--python",str(script)],capture_output=True,text=True,timeout=int(job.get("blender_timeout_s",900)))
        (out/"blender.stdout.txt").write_text(cp.stdout); (out/"blender.stderr.txt").write_text(cp.stderr)
        if cp.returncode!=0 or not glb.exists(): raise RuntimeError(f"blender_failed:returncode={cp.returncode}")
        stage("completed",model_url=str(glb),engineering_report=str(out/"engineering_report.json")); return job
    except Exception as exc:
        stage("failed",error=f"{type(exc).__name__}:{exc}",traceback=traceback.format_exc()); return job
