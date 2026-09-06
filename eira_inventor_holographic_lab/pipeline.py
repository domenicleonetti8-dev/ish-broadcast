from __future__ import annotations
import json, subprocess, time, traceback
from pathlib import Path
from .provider import ollama_vision
from .compiler import compile_assembly
from .blender_backend import generate_blender_script
from .forensic_detail import write_blueprint_package, validate_forensic_detail
from .apple_ar import package_usdc, validate_usdz

TERMINAL={"completed","failed","cancelled"}

def _image_list(image_paths):
    if isinstance(image_paths,(str,Path)): image_paths=[image_paths]
    out=[Path(p) for p in (image_paths or []) if Path(p).is_file()]
    if not out: raise ValueError('source_images_required')
    return out

def _usd_export_script(glb,usdc):
    return f'''import bpy\nGLB={str(glb)!r}\nUSDC={str(usdc)!r}\nbpy.ops.object.select_all(action="SELECT")\nbpy.ops.object.delete(use_global=False)\nbpy.ops.import_scene.gltf(filepath=GLB)\ntry:\n bpy.ops.wm.usd_export(filepath=USDC,export_animation=True,export_materials=True)\nexcept TypeError:\n bpy.ops.wm.usd_export(filepath=USDC)\n'''

def run_job(job,image_paths,user_text,out_dir,vision=ollama_vision,blender="blender"):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); trace=[]; images=_image_list(image_paths)
    def stage(s,**kw):
        now=time.time(); trace.append({"status":s,"t":now}); job.update(status=s,updated=now,**kw)
        (out/"job.json").write_text(json.dumps(job,indent=2,default=str)); (out/"lifecycle_trace.json").write_text(json.dumps(trace,indent=2))
    try:
        stage("starting",source_image_count=len(images),source_images=[str(p) for p in images]); stage("vision_running")
        assembly=vision([str(p) for p in images],user_text); assembly.setdefault('source_images',[str(p) for p in images]); (out/"vision_ir.json").write_text(json.dumps(assembly,indent=2))
        stage("engineering_compiling")
        compiled,scene=compile_assembly(assembly,duration_s=float(job.get("duration_s",10)),fps=int(job.get("fps",24)))
        forensic_findings=validate_forensic_detail(compiled); compiled['forensic_findings']=forensic_findings
        (out/"compiled_ir.json").write_text(json.dumps(compiled,indent=2,default=str))
        blueprint=write_blueprint_package(compiled,out)
        (out/"engineering_report.json").write_text(json.dumps({"summary":compiled.get("engineering_summary"),"quantities":compiled.get("calculated_quantities"),"diagrams":compiled.get("diagram_layer"),"forensic_findings":forensic_findings,"blueprint_package":blueprint},indent=2,default=str))
        stage("geometry_expanding",blueprint_master=blueprint['master'])
        for p in compiled["parts"]:
            if p["geometry"]["kind"] in {"instance","boolean","primitive","mesh","curve"}: continue
            from .geometry import mesh_from_geometry
            m=mesh_from_geometry(p["geometry"]); p["geometry"]={"kind":"mesh","vertices":m.vertices.tolist(),"faces":m.faces.tolist()}
        glb=out/"assembly.glb"; script=out/"assembly_blender.py"; script.write_text(generate_blender_script(compiled,str(glb)))
        stage("blender_running")
        cp=subprocess.run([blender,"-b","--python",str(script)],capture_output=True,text=True,timeout=int(job.get("blender_timeout_s",900)))
        (out/"blender.stdout.txt").write_text(cp.stdout); (out/"blender.stderr.txt").write_text(cp.stderr)
        if cp.returncode!=0 or not glb.exists(): raise RuntimeError(f"blender_failed:returncode={cp.returncode}")
        stage("apple_ar_export")
        usdc=out/'assembly.usdc'; usd_script=out/'apple_ar_export.py'; usd_script.write_text(_usd_export_script(glb,usdc),encoding='utf-8')
        cp2=subprocess.run([blender,"-b","--python",str(usd_script)],capture_output=True,text=True,timeout=int(job.get("blender_timeout_s",900)))
        (out/"apple_ar.stdout.txt").write_text(cp2.stdout); (out/"apple_ar.stderr.txt").write_text(cp2.stderr)
        if cp2.returncode!=0 or not usdc.exists(): raise RuntimeError(f"apple_usd_export_failed:returncode={cp2.returncode}")
        usdz=package_usdc(usdc,out/'assembly.usdz'); ar_validation=validate_usdz(usdz)
        stage("completed",model_url=str(glb),usdz_path=str(usdz),apple_ar=ar_validation,engineering_report=str(out/"engineering_report.json"),blueprint_master=blueprint['master']); return job
    except Exception as exc:
        stage("failed",error=f"{type(exc).__name__}:{exc}",traceback=traceback.format_exc()); return job
