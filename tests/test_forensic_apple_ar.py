from pathlib import Path
import json,tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eira_inventor_holographic_lab.forensic_detail import validate_forensic_detail,write_blueprint_package
from eira_inventor_holographic_lab.apple_ar import package_usdc,validate_usdz

assembly={
 'assembly_id':'forensic_test','name':'Forensic Test','units':'m',
 'parts':[{'part_id':'controller','name':'Controller','geometry':{'kind':'primitive','primitive':'box','dimensions':{'x':.1,'y':.08,'z':.03}},'transform':{'location':[0,0,0],'rotation_deg':[0,0,0],'scale':[1,1,1]},'source':{'provenance':'stated','confidence':1},'engineering':{}}],
 'component_ledger':[{'component_id':'controller','part_id':'controller','manufacturer_part_number':'CTRL-001','source':{'provenance':'stated','confidence':1}}],
 'fastener_schedule':[{'fastener_id':'f1','part_id':'controller','standard_size':'M3x0.5','length_mm':8,'source':{'provenance':'stated','confidence':1}}],
 'wire_schedule':[{'wire_id':'w1','part_id':'controller','awg':22,'length_m':0.42,'from':'J1.1','to':'SW1.1','source':{'provenance':'calculated','confidence':.95}}],
 'electronics':[{'component_id':'controller','part_id':'controller','kind':'microcontroller','mpn':'TEST-MCU','source':{'provenance':'stated','confidence':1}}],
 'pcb':[{'component_id':'controller','part_id':'controller','board_id':'PCB1','layers':4,'source':{'provenance':'stated','confidence':1}}],
 'bom':[{'component_id':'controller','part_id':'controller','quantity':1,'source':{'provenance':'stated','confidence':1}}],
 'software_artifacts':[{'component_id':'controller','part_id':'controller','filename':'firmware.py','language':'python','target':'controller','entrypoint':'main','source_text':'def main():\n    return 1\n','source':{'provenance':'stated','confidence':1}}],
}
assert validate_forensic_detail(assembly)==[]
with tempfile.TemporaryDirectory(prefix='eira_forensic_') as td:
 root=Path(td)
 bp=write_blueprint_package(assembly,root)
 master=Path(bp['master'])
 assert master.is_file()
 obj=json.loads(master.read_text())
 assert obj['wire_schedule'][0]['awg']==22
 assert obj['fastener_schedule'][0]['standard_size']=='M3x0.5'
 assert (root/'blueprints'/'software'/'firmware.py').read_text().startswith('def main')
 usdc=root/'assembly.usdc'; usdc.write_bytes(b'PXR-USDC-TEST-DATA'*8)
 usdz=package_usdc(usdc,root/'assembly.usdz')
 v=validate_usdz(usdz)
 assert v['ok'] and v['payload_alignment']%64==0
 print('FORENSIC BLUEPRINT + APPLE AR PACKAGE PASS',v['size'],v['payload_alignment'])
