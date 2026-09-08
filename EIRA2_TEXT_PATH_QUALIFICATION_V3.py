#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request, urllib.error

BASE='http://127.0.0.1:8782'

def get_json(path:str,timeout:float=20.0):
    req=urllib.request.Request(BASE+path,method='GET')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read(); return getattr(r,'status',200), json.loads(raw.decode('utf-8','replace'))

def post_json(path:str,payload:dict,timeout:float=120.0):
    raw=json.dumps(payload).encode('utf-8')
    req=urllib.request.Request(BASE+path,data=raw,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read(); return getattr(r,'status',200), json.loads(body.decode('utf-8','replace'))

def main()->int:
    out={'schema':'eira2_text_path_qualification_v3','mutates_live':False,'ok':False}
    try:
        hs,h=get_json('/health')
        ts,t=post_json('/v1/text',{'text':'Reply with one short sentence confirming the live EIRA2 text path is functioning.','source':'transport_qualification_v3'})
        answer=''
        if isinstance(t,dict):
            answer=str(t.get('text') or t.get('reply') or t.get('response') or '').strip()
            if not answer and isinstance(t.get('result'),dict):
                r=t['result']; answer=str(r.get('text') or r.get('reply') or r.get('response') or '').strip()
        out.update({'health_status':hs,'health':h,'text_status':ts,'text_response':t,'answer':answer,'ok':hs==200 and ts==200 and bool(answer)})
    except Exception as exc:
        out['error']=f'{type(exc).__name__}:{exc}'
    print(json.dumps(out,separators=(',',':')))
    return 0 if out['ok'] else 1

if __name__=='__main__':
    raise SystemExit(main())
