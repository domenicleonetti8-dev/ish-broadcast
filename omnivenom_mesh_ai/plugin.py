from __future__ import annotations
from pathlib import Path
from .runtime import Omnivenom

VERSION='1.0.0'
_CACHE={}

def _mesh(live_root,state_path=None):
    key=(str(Path(live_root).resolve()),str(state_path or ''))
    if key not in _CACHE:_CACHE[key]=Omnivenom(live_root,state_path)
    return _CACHE[key]

def ask(task):
    if not isinstance(task,dict):return {'ok':False,'error':'task_must_be_mapping'}
    live=task.get('live_root') or '.'; op=str(task.get('operation') or 'status')
    m=_mesh(live,task.get('state_path'))
    if op=='refresh':return {'ok':True,'result':m.refresh()}
    if op=='find':return {'ok':True,'result':m.find(str(task.get('query') or ''),int(task.get('limit') or 20))}
    if op=='context':return {'ok':True,'result':m.context(str(task.get('query') or ''),int(task.get('depth') or 1),int(task.get('limit') or 250))}
    if op=='status':return {'ok':True,'result':m.status()}
    return {'ok':False,'error':'unsupported_operation'}
