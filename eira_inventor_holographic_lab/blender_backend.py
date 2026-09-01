from __future__ import annotations
import json

def generate_blender_script(assembly,out_glb):
    A=json.dumps(assembly,separators=(",",":"))
    return f'''import bpy,json,math
from mathutils import Vector
A=json.loads({A!r})
OUT={out_glb!r}
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
PARTS={{}}

def rgba(v,default=(.55,.62,.68,1)):
 try:
  if isinstance(v,str) and v.startswith('#') and len(v) in (7,9):
   s=v[1:]; a=int(s[6:8],16)/255 if len(s)==8 else 1; return (int(s[0:2],16)/255,int(s[2:4],16)/255,int(s[4:6],16)/255,a)
  if isinstance(v,(list,tuple)) and len(v)>=3: return (float(v[0]),float(v[1]),float(v[2]),float(v[3]) if len(v)>3 else 1)
 except Exception: pass
 return default

def material(name,color,alpha=1,metallic=.05,roughness=.42):
 m=bpy.data.materials.get(name) or bpy.data.materials.new(name); c=rgba(color); m.diffuse_color=(c[0],c[1],c[2],alpha*c[3]); m.use_nodes=True
 bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=m.diffuse_color; bs.inputs['Metallic'].default_value=float(metallic); bs.inputs['Roughness'].default_value=float(roughness); bs.inputs['Alpha'].default_value=m.diffuse_color[3]
 try:
  if m.diffuse_color[3]<.999: m.surface_render_method='DITHERED'
 except Exception: pass
 return m

def mesh_obj(pid,verts,faces):
 me=bpy.data.meshes.new(pid); me.from_pydata(verts,[],faces); me.validate(); me.update(); o=bpy.data.objects.new(pid,me); bpy.context.collection.objects.link(o); return o

def curve_obj(pid,pts,basis='POLY',radius=.01,material_obj=None):
 cu=bpy.data.curves.new(pid,'CURVE'); cu.dimensions='3D'; cu.bevel_depth=float(radius); cu.bevel_resolution=3; cu.resolution_u=12
 sp=cu.splines.new('BEZIER' if basis=='BEZIER' else 'NURBS' if basis=='NURBS' else 'POLY')
 if basis=='BEZIER':
  sp.bezier_points.add(len(pts)-1)
  for q,p in zip(sp.bezier_points,pts): q.co=p; q.handle_left_type='AUTO'; q.handle_right_type='AUTO'
 else:
  sp.points.add(len(pts)-1)
  for q,p in zip(sp.points,pts): q.co=(*p,1)
  if basis=='NURBS': sp.use_endpoint_u=True
 o=bpy.data.objects.new(pid,cu); bpy.context.collection.objects.link(o)
 if material_obj: o.data.materials.append(material_obj)
 return o

def text_obj(name,text,loc,size=.08):
 cu=bpy.data.curves.new(name,'FONT'); cu.body=str(text); cu.align_x='CENTER'; cu.size=float(size); cu.extrude=.001; o=bpy.data.objects.new(name,cu); bpy.context.collection.objects.link(o); o.location=loc; return o

def cylinder_between(name,a,b,r=.006,mat=None):
 a=Vector(a); b=Vector(b); d=b-a; L=d.length
 if L<1e-9: return None
 bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=r,depth=L,location=(a+b)/2); o=bpy.context.object; o.name=name; o.rotation_mode='QUATERNION'; o.rotation_quaternion=d.to_track_quat('Z','Y')
 if mat: o.data.materials.append(mat)
 return o

def cone_tip(name,at,direction,r=.018,L=.05,mat=None):
 d=Vector(direction)
 if d.length<1e-9:return None
 d.normalize(); bpy.ops.mesh.primitive_cone_add(vertices=20,radius1=r,radius2=0,depth=L,location=Vector(at)-d*(L/2)); o=bpy.context.object; o.name=name; o.rotation_mode='QUATERNION'; o.rotation_quaternion=d.to_track_quat('Z','Y')
 if mat:o.data.materials.append(mat)
 return o

def build(g,pid):
 k=g['kind']
 if k=='primitive':
  d=g.get('dimensions',{{}}); q=g['primitive']
  if q=='box': bpy.ops.mesh.primitive_cube_add(); o=bpy.context.object; o.scale=(d.get('x',1)/2,d.get('y',1)/2,d.get('z',1)/2)
  elif q=='cylinder': bpy.ops.mesh.primitive_cylinder_add(vertices=int(d.get('segments',64)),radius=d.get('radius',.5),depth=d.get('height',1)); o=bpy.context.object
  elif q=='sphere': bpy.ops.mesh.primitive_uv_sphere_add(segments=int(d.get('segments',64)),ring_count=int(d.get('rings',32)),radius=d.get('radius',.5)); o=bpy.context.object
  elif q=='cone': bpy.ops.mesh.primitive_cone_add(vertices=int(d.get('segments',64)),radius1=d.get('radius',.5),depth=d.get('height',1)); o=bpy.context.object
  elif q=='torus': bpy.ops.mesh.primitive_torus_add(major_segments=96,minor_segments=32,major_radius=d.get('major_radius',1),minor_radius=d.get('minor_radius',.2)); o=bpy.context.object
  elif q=='capsule': bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=d.get('radius',.25)); o=bpy.context.object
  else: raise RuntimeError('primitive unsupported:'+str(q))
  return o
 if k=='mesh': return mesh_obj(pid,g['vertices'],g['faces'])
 if k=='curve': return curve_obj(pid,g['points'],g.get('basis','POLY'),g.get('radius',.01))
 raise RuntimeError('geometry must be precompiled before Blender:'+k)

for p in A['parts']:
 g=p['geometry']
 if g['kind'] in ('instance','boolean'): continue
 o=build(g,p['part_id']); o.name=p['part_id']+'__'+p['name']; PARTS[p['part_id']]=o
 t=p.get('transform',{{}}); o.location=t.get('location',[0,0,0]); o.rotation_euler=[math.radians(x) for x in t.get('rotation_deg',[0,0,0])]; o.scale=[o.scale[i]*t.get('scale',[1,1,1])[i] for i in range(3)]
 vis=p.get('visual',{{}}); color=vis.get('color',p.get('color','#8191a0')); alpha=float(vis.get('alpha',1.0)); mat=material('MAT__'+p['part_id'],color,alpha,float(vis.get('metallic',.05)),float(vis.get('roughness',.42))); o.data.materials.append(mat)
 o['engineering_source']=json.dumps(p.get('source',{{}})); o['system']=str(p.get('system','')); o['subsystem']=str(p.get('subsystem','')); o['engineering']=json.dumps(p.get('engineering',{{}}))

dim_mat=material('DIAGRAM_DIM','#f5d76e',1,0,.25); force_mat=material('DIAGRAM_FORCE','#e85d5d',1,0,.25); flow_mat=material('DIAGRAM_FLOW','#48a9e6',1,0,.2); port_mat=material('DIAGRAM_PORT','#8bd17c',1,0,.25); text_mat=material('DIAGRAM_TEXT','#f4f4f4',1,0,.5)
for it in A.get('diagram_layer',{{}}).get('items',[]):
 k=it.get('kind'); iid='DIAGRAM__'+str(it.get('id','item'))
 if k=='dimension':
  a=it['a']; b=it['b']; cylinder_between(iid+'__line',a,b,.004,dim_mat); d=Vector(b)-Vector(a); cone_tip(iid+'__a',a,-d,.014,.035,dim_mat); cone_tip(iid+'__b',b,d,.014,.035,dim_mat); tx=text_obj(iid+'__text',it.get('label',''),(Vector(a)+Vector(b))/2+Vector((0,0,.03)),.065); tx.data.materials.append(text_mat)
 elif k=='vector':
  a=Vector(it['origin']); v=Vector(it['vector']); scale=.12/max(1e-9,v.length); b=a+v*scale; cylinder_between(iid+'__shaft',a,b,.007,force_mat); cone_tip(iid+'__tip',b,v,.025,.06,force_mat); tx=text_obj(iid+'__text',it.get('label',''),b+Vector((0,0,.04)),.06); tx.data.materials.append(text_mat)
 elif k=='flow':
  pts=it.get('path',[]); curve_obj(iid+'__path',pts,'BEZIER',.008,flow_mat)
  if len(pts)>=2:
   cone_tip(iid+'__tip',pts[-1],Vector(pts[-1])-Vector(pts[-2]),.022,.055,flow_mat); tx=text_obj(iid+'__text',it.get('label',''),Vector(pts[len(pts)//2])+Vector((0,0,.04)),.06); tx.data.materials.append(text_mat)
 elif k=='port':
  p=Vector(it['position']); d=Vector(it.get('direction',[0,0,1])); bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=.018,location=p); q=bpy.context.object; q.name=iid; q.data.materials.append(port_mat); cone_tip(iid+'__dir',p+d*.07,d,.014,.035,port_mat)

fps=int(A.get('motion_fps',24)); bpy.context.scene.render.fps=fps
for j in A.get('joints',[]):
 child=PARTS.get(j.get('child')); jid=j.get('joint_id'); track=A.get('motion_tracks',{{}}).get(jid,[]) if jid else []
 if not child or not track: continue
 axis=Vector(j.get('axis',[0,0,1])); idx=max(range(3),key=lambda i:abs(axis[i])); kind=j.get('kind'); base_rot=list(child.rotation_euler); base_loc=Vector(child.location)
 for s in track:
  fr=1+round(float(s['t_s'])*fps); val=float(s['value'])
  if kind in ('continuous','revolute','oscillating'):
   child.rotation_euler[idx]=base_rot[idx]+math.radians(val); child.keyframe_insert(data_path='rotation_euler',index=idx,frame=fr)
  elif kind=='prismatic':
   child.location=base_loc+axis.normalized()*val; child.keyframe_insert(data_path='location',frame=fr)

for frame in A.get('living_simulation',{{}}).get('frames',[]):
 fr=1+round(float(frame.get('t_s',0))*fps)
 for st in frame.get('states',{{}}).values():
  o=PARTS.get(st.get('target')); var=st.get('variable'); val=float(st.get('value',0))
  if not o: continue
  if var=='visibility': o.hide_render=val<=0; o.keyframe_insert(data_path='hide_render',frame=fr)
  elif var=='scale': o.scale=(val,val,val); o.keyframe_insert(data_path='scale',frame=fr)
  elif var=='rotation_z_deg': o.rotation_euler.z=math.radians(val); o.keyframe_insert(data_path='rotation_euler',index=2,frame=fr)
  elif var=='translation_z_m': o.location.z=val; o.keyframe_insert(data_path='location',index=2,frame=fr)

bpy.context.scene.frame_start=1; bpy.context.scene.frame_end=max(2,round(float(A.get('living_simulation',{{}}).get('duration_s',10))*fps)+1)
for o in bpy.context.scene.objects:
 if hasattr(o,'select_set'): o.select_set(False)
bpy.ops.export_scene.gltf(filepath=OUT,export_format='GLB',export_animations=True,export_extras=True,export_materials='EXPORT')
'''
