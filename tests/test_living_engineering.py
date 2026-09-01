from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eira_inventor_holographic_lab.compiler import compile_assembly

a={
 'assembly_id':'living_test','name':'Living engineering test','units':'m',
 'parts':[
  {'part_id':'beam','name':'Beam','geometry':{'kind':'primitive','primitive':'box','dimensions':{'x':2,'y':.1,'z':.1}},'transform':{'location':[0,0,0],'rotation_deg':[0,0,0],'scale':[1,1,1]},'source':{'provenance':'stated','confidence':1},'engineering':{'density_kg_m3':2700,'youngs_modulus_Pa':69e9,'beam_length_m':2,'second_moment_m4':8.33e-6,'point_load_N':500}},
  {'part_id':'fan','name':'Fan','geometry':{'kind':'primitive','primitive':'cylinder','dimensions':{'radius':.2,'height':.05}},'transform':{'location':[0,0,.5],'rotation_deg':[0,0,0],'scale':[1,1,1]},'source':{'provenance':'stated','confidence':1},'engineering':{'voltage_V':24,'current_A':2}}
 ],
 'joints':[{'joint_id':'fan_joint','parent':'beam','child':'fan','kind':'continuous','axis':[0,0,1],'speed_deg_s':360}],
 'dimensions':[{'dimension_id':'beam_len','a':[-1,0,0],'b':[1,0,0],'label':'2.0 m'}],
 'flows':[{'flow_id':'air','medium':'air','path':[[0,0,.5],[0,0,1.5]],'label':'airflow'}],
 'behaviors':[{'behavior_id':'pulse','target':'fan','variable':'scale','curve':'sine','offset':1,'amplitude':.01,'frequency_hz':1}]
}
c,scene=compile_assembly(a,duration_s=2,fps=12)
assert c['engineering_summary']['part_count']==2
assert c['diagram_layer']['count']==2
assert len(c['calculated_quantities'])>=4
assert len(c['motion_tracks']['fan_joint'])>2
assert len(c['living_simulation']['frames'])>2
assert len(scene.geometry)>=4
print('LIVING ENGINEERING PASS')
