from __future__ import annotations

from pathlib import Path


def generate_preview_script(glb_path: str, out_dir: str, *, resolution: int = 640) -> str:
    """Return a self-contained Blender script that renders diagnostic views of a GLB.

    These previews are not presentation art. They are deterministic evidence for the
    visual review loop: front 3/4, rear 3/4, side, roof and underside/service views.
    """
    return f'''import bpy, math
from pathlib import Path
from mathutils import Vector

GLB={glb_path!r}
OUT=Path({out_dir!r})
RES={int(resolution)}
OUT.mkdir(parents=True,exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=GLB)

objects=[o for o in bpy.context.scene.objects if o.type=="MESH"]
if not objects:
    raise RuntimeError("preview:no_mesh_objects")

mins=Vector((1e30,1e30,1e30)); maxs=Vector((-1e30,-1e30,-1e30))
for o in objects:
    for c in o.bound_box:
        w=o.matrix_world @ Vector(c)
        mins.x=min(mins.x,w.x); mins.y=min(mins.y,w.y); mins.z=min(mins.z,w.z)
        maxs.x=max(maxs.x,w.x); maxs.y=max(maxs.y,w.y); maxs.z=max(maxs.z,w.z)
center=(mins+maxs)*0.5
ext=maxs-mins
radius=max(ext.x,ext.y,ext.z)*0.75
if radius<=1e-6: radius=1.0

scene=bpy.context.scene
scene.render.engine='BLENDER_EEVEE_NEXT'
scene.render.resolution_x=RES
scene.render.resolution_y=RES
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.film_transparent=False
scene.world.color=(0.025,0.028,0.035)

# neutral ground catches floating parts and exposes the service-base relationship
bpy.ops.mesh.primitive_plane_add(size=max(ext.x,ext.y)*2.8,location=(center.x,center.y,mins.z-0.01))
ground=bpy.context.object
ground.name='QA_GROUND'
mat=bpy.data.materials.new('QA_GROUND_MAT'); mat.diffuse_color=(0.10,0.11,0.13,1); mat.use_nodes=True
ground.data.materials.append(mat)

# camera
bpy.ops.object.camera_add()
cam=bpy.context.object
scene.camera=cam
cam.data.lens=48

def track(obj, point):
    obj.rotation_euler=(Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

def add_area(name,loc,energy,size):
    bpy.ops.object.light_add(type='AREA',location=loc)
    l=bpy.context.object; l.name=name; l.data.energy=energy; l.data.shape='DISK'; l.data.size=size; track(l,center)

add_area('QA_KEY',(center.x-radius*1.2,center.y-radius*1.3,center.z+radius*1.5),1400,radius*1.1)
add_area('QA_FILL',(center.x+radius*1.4,center.y-radius*0.4,center.z+radius*0.8),850,radius*1.0)
add_area('QA_RIM',(center.x,center.y+radius*1.5,center.z+radius*1.2),1000,radius*0.8)

views={{
 'front_three_quarter': (center.x-radius*1.35, center.y-radius*1.45, center.z+radius*0.80),
 'rear_three_quarter':  (center.x+radius*1.35, center.y+radius*1.45, center.z+radius*0.80),
 'side_cutaway':        (center.x, center.y-radius*2.0, center.z+radius*0.30),
 'roof_systems':        (center.x-radius*0.20, center.y-radius*0.45, center.z+radius*2.10),
 'underside_service':   (center.x-radius*0.70, center.y-radius*1.55, mins.z-radius*0.22),
}}

for name,loc in views.items():
    cam.location=loc
    track(cam,center)
    scene.render.filepath=str(OUT/(name+'.png'))
    bpy.ops.render.render(write_still=True)

print('PREVIEW_RENDER_PASS',len(views))
'''


def preview_paths(out_dir: str) -> list[str]:
    root = Path(out_dir)
    names = ["front_three_quarter", "rear_three_quarter", "side_cutaway", "roof_systems", "underside_service"]
    return [str(root / f"{name}.png") for name in names]
