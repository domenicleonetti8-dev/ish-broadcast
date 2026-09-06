from __future__ import annotations
import base64, json, urllib.request
from pathlib import Path
from .vision_contract import SYSTEM_PROMPT, response_schema
class VisionProviderError(RuntimeError): pass

def _paths(image_paths):
    if isinstance(image_paths,(str,Path)): image_paths=[image_paths]
    out=[]
    for p in image_paths or []:
        q=Path(p)
        if q.is_file(): out.append(q)
    if not out: raise VisionProviderError('vision_no_images')
    return out

def ollama_vision(image_paths,user_text="",model="gemma3:4b",timeout=900):
    paths=_paths(image_paths)
    images=[]
    for path in paths:
        with path.open("rb") as f: images.append(base64.b64encode(f.read()).decode())
    evidence='\n'.join(f'VIEW[{i}]={p.name}' for i,p in enumerate(paths))
    payload={"model":model,"stream":False,"messages":[{"role":"user","content":SYSTEM_PROMPT+"\nUSER DESCRIPTION:\n"+str(user_text or '')+"\nSUBMITTED VIEWS:\n"+evidence,"images":images}],"format":response_schema(),"options":{"temperature":0,"num_ctx":8192,"num_predict":8192}}
    req=urllib.request.Request("http://127.0.0.1:11434/api/chat",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: data=json.load(r)
    except Exception as e: raise VisionProviderError(f"vision_transport:{type(e).__name__}:{e}")
    raw=data.get("message",{}).get("content","")
    try:
        out=json.loads(raw)
    except Exception as e: raise VisionProviderError(f"vision_json:{e}")
    out.setdefault('evidence_views',[{'index':i,'name':p.name,'path':str(p)} for i,p in enumerate(paths)])
    return out
