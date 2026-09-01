from __future__ import annotations
import base64, json, urllib.request
from .vision_contract import SYSTEM_PROMPT, response_schema
class VisionProviderError(RuntimeError): pass

def ollama_vision(image_path,user_text="",model="gemma3:4b",timeout=900):
    with open(image_path,"rb") as f: image=base64.b64encode(f.read()).decode()
    payload={"model":model,"stream":False,"messages":[{"role":"user","content":SYSTEM_PROMPT+"\n"+user_text,"images":[image]}],"format":response_schema(),"options":{"temperature":0,"num_ctx":4096,"num_predict":4096}}
    req=urllib.request.Request("http://127.0.0.1:11434/api/chat",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: data=json.load(r)
    except Exception as e: raise VisionProviderError(f"vision_transport:{type(e).__name__}:{e}")
    raw=data.get("message",{}).get("content","")
    try: return json.loads(raw)
    except Exception as e: raise VisionProviderError(f"vision_json:{e}")
