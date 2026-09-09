#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,time
from pathlib import Path
from typing import Any
VERSION='6.0.0'
SCHEMA='eira2_transport_request_v1'
PLAN_SCHEMA='eira2_builder_plan_v3'
ROOT=Path(os.environ.get('EIRA_ROOT','/media/domenicleonetti/easystore/EIRA/LIVE')).resolve()

def _sha(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()

def _atomic(p:Path,v:Any)->None:
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+f'.tmp.{os.getpid()}'); t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(t,p)

def _safe_rel(v:str)->str:
 p=Path(str(v or ''))
 if p.is_absolute() or not p.parts or '..' in p.parts: raise RuntimeError('unsafe_relative_path:'+str(v))
 if p.parts[0]=='.git': raise RuntimeError('git_metadata_write_blocked')
 return p.as_posix()

def _inbox()->str:
 p=ROOT/'eira_probe'/'watcher_inbox_v6'; p.mkdir(parents=True,exist_ok=True); return str(p)

def authorize_transport_request(request:dict[str,Any])->dict[str,Any]:
 if not isinstance(request,dict) or request.get('schema')!=SCHEMA: return {'authorized':False,'reason':'schema_mismatch'}
 op=str(request.get('operation') or '').casefold()
 if op not in {'inspect','deploy'}: return {'authorized':False,'reason':'unsupported_operation'}
 if op=='deploy':
  dep=request.get('deployment') or {}; target=dep.get('target') or {}; source=dep.get('source') or {}
  try: target_path=_safe_rel(str(target.get('path') or ''))
  except Exception as e: return {'authorized':False,'reason':str(e)}
  if not source: return {'authorized':False,'reason':'source_missing'}
  if not (source.get('path') or source.get('manifest')): return {'authorized':False,'reason':'source_path_missing'}
  return {'authorized':True,'authorized_by':'repair_watcher_ai','watcher_version':VERSION,'operation':'deploy','target_path':target_path,'policy':'broad_eira_live_write_with_root_containment_hash_and_rollback'}
 return {'authorized':True,'authorized_by':'repair_watcher_ai','watcher_version':VERSION,'operation':'inspect','policy':'read_only'}

def inspect_once()->dict[str,Any]:
 inbox=Path(_inbox()); idx=inbox/'file_index.json'; pkg=inbox/'surgery_package.json'
 if not idx.is_file() or not pkg.is_file(): return {'ok':True,'status':'idle','watcher_version':VERSION,'builder_plan':None}
 try:
  index=json.loads(idx.read_text()); package=json.loads(pkg.read_text()); rows=index.get('files') or []
  if not rows: raise RuntimeError('file_index_empty')
  stage=(inbox/'stage').resolve(); files=[]
  for row in rows:
   target=_safe_rel(str(row.get('target_path') or '')); staged=_safe_rel(str(row.get('staged_path') or '')); expected=str(row.get('sha256') or '').lower(); p=(stage/staged).resolve(); p.relative_to(stage)
   if not p.is_file(): raise RuntimeError('staged_missing:'+staged)
   actual=_sha(p)
   if expected and actual!=expected: raise RuntimeError('staged_hash_mismatch:'+staged)
   files.append({'target_path':target,'staged_path':staged,'sha256':actual})
  plan={'schema':PLAN_SCHEMA,'authorized_by':'repair_watcher_ai','watcher_version':VERSION,'created_unix':time.time(),'offsystem_stage_root':str(stage),'files':files,'package_fingerprint_sha256':package.get('package_fingerprint_sha256')}
  out=ROOT/'eira_probe'/'eira2_builder_plan.json'; _atomic(out,plan)
  return {'ok':True,'status':'authorized','watcher_version':VERSION,'builder_plan':str(out),'file_count':len(files)}
 except Exception as e:
  return {'ok':False,'status':'rejected','watcher_version':VERSION,'error':f'{type(e).__name__}:{e}'}
