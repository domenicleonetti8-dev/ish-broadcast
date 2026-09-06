from __future__ import annotations
import json,re
from pathlib import Path
from .contracts import PROVENANCE, ContractError

DETAIL_KEYS=(
    'component_ledger','fastener_schedule','wire_schedule','electronics','pcb','bom','software_artifacts',
)

def _src(item):
    if not isinstance(item,dict): raise ContractError('forensic_detail_item_must_be_object')
    src=item.get('source') or {'provenance':'unresolved','confidence':0.0,'reason':'not supplied'}
    if src.get('provenance','unresolved') not in PROVENANCE: raise ContractError('forensic_detail_bad_provenance')
    try: c=float(src.get('confidence',0.0))
    except Exception as exc: raise ContractError('forensic_detail_bad_confidence') from exc
    if not 0<=c<=1: raise ContractError('forensic_detail_bad_confidence')
    return src

def validate_forensic_detail(assembly):
    part_ids={str(p.get('part_id')) for p in assembly.get('parts',[]) if p.get('part_id')}
    findings=[]
    for key in DETAIL_KEYS:
        rows=assembly.get(key,[]) or []
        if not isinstance(rows,list): raise ContractError(f'{key}_must_be_array')
        for i,row in enumerate(rows):
            _src(row)
            pid=row.get('part_id') or row.get('component_id') or row.get('target_part_id')
            if pid and str(pid) not in part_ids:
                findings.append({'severity':'warning','kind':'unmapped_detail','schedule':key,'index':i,'part_id':str(pid)})
    for row in assembly.get('wire_schedule',[]) or []:
        if row.get('awg') is None and row.get('cross_section_mm2') is None:
            findings.append({'severity':'warning','kind':'wire_gauge_unresolved','wire':row.get('wire_id') or row.get('id')})
        if row.get('length_m') is None:
            findings.append({'severity':'warning','kind':'wire_length_unresolved','wire':row.get('wire_id') or row.get('id')})
    for row in assembly.get('fastener_schedule',[]) or []:
        if row.get('nominal_diameter_mm') is None and not row.get('standard_size'):
            findings.append({'severity':'warning','kind':'fastener_size_unresolved','fastener':row.get('fastener_id') or row.get('id')})
    return findings

def _safe_filename(name,default):
    s=re.sub(r'[^A-Za-z0-9._-]+','_',str(name or '')).strip('._')
    return (s[:120] or default)

def write_blueprint_package(assembly,out_dir):
    out=Path(out_dir); bp=out/'blueprints'; bp.mkdir(parents=True,exist_ok=True)
    findings=validate_forensic_detail(assembly)
    master={
        'assembly_id':assembly.get('assembly_id'),'name':assembly.get('name'),'units':assembly.get('units','m'),
        'truth_model':'observed/stated/calculated/inferred/assumed/hypothesized/unresolved',
        'component_ledger':assembly.get('component_ledger',[]),'fastener_schedule':assembly.get('fastener_schedule',[]),
        'wire_schedule':assembly.get('wire_schedule',[]),'electronics':assembly.get('electronics',[]),'pcb':assembly.get('pcb',[]),
        'bom':assembly.get('bom',[]),'dimensions':assembly.get('dimensions',[]),'flows':assembly.get('flows',[]),
        'equations':assembly.get('equations',[]),'validation_requirements':assembly.get('validation_requirements',[]),
        'unresolved_regions':assembly.get('unresolved_regions',[]),'forensic_findings':findings,
    }
    (bp/'engineering_master.json').write_text(json.dumps(master,indent=2,default=str),encoding='utf-8')
    (bp/'bom.json').write_text(json.dumps(assembly.get('bom',[]),indent=2,default=str),encoding='utf-8')
    (bp/'fastener_schedule.json').write_text(json.dumps(assembly.get('fastener_schedule',[]),indent=2,default=str),encoding='utf-8')
    (bp/'wire_schedule.json').write_text(json.dumps(assembly.get('wire_schedule',[]),indent=2,default=str),encoding='utf-8')
    (bp/'electronics.json').write_text(json.dumps(assembly.get('electronics',[]),indent=2,default=str),encoding='utf-8')
    (bp/'pcb.json').write_text(json.dumps(assembly.get('pcb',[]),indent=2,default=str),encoding='utf-8')
    code_dir=bp/'software'; code_dir.mkdir(exist_ok=True)
    software_index=[]
    for i,art in enumerate(assembly.get('software_artifacts',[]) or []):
        if not isinstance(art,dict): continue
        src=_src(art); name=_safe_filename(art.get('filename'),f'artifact_{i}.txt')
        text=str(art.get('source_text') or art.get('code') or '')
        (code_dir/name).write_text(text,encoding='utf-8')
        software_index.append({'filename':name,'language':art.get('language'),'target':art.get('target'),'entrypoint':art.get('entrypoint'),'source':src})
    (bp/'software_index.json').write_text(json.dumps(software_index,indent=2),encoding='utf-8')
    return {'root':str(bp),'master':str(bp/'engineering_master.json'),'software_count':len(software_index),'findings':findings}
