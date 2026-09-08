#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request
BASE='http://127.0.0.1:8782'

def req(method,path,payload=None,timeout=120):
    data=None if payload is None else json.dumps(payload).encode()
    headers={} if data is None else {'Content-Type':'application/json'}
    r=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    with urllib.request.urlopen(r,timeout=timeout) as x:
        raw=x.read(); return getattr(x,'status',200),json.loads(raw.decode('utf-8','replace'))

def main():
    out={'schema':'eira2_text_path_qualification_v4','ok':False,'mutates_live':False}
    try:
        hs,h=req('GET','/health',timeout=15)
        ts,t=req('POST','/v1/text',{'text':'Say exactly one short sentence confirming EIRA2 text conversation is live.','source':'transport_qualification_v4'},timeout=120)
        answer=''
        if isinstance(t,dict):
            answer=str(t.get('text') or t.get('reply') or t.get('response') or '').strip()
            if not answer and isinstance(t.get('result'),dict):
                rr=t['result']; answer=str(rr.get('text') or rr.get('reply') or rr.get('response') or '').strip()
        out.update({'health_status':hs,'health':h,'text_status':ts,'text_response':t,'answer':answer,'ok':hs==200 and ts==200 and bool(answer)})
    except Exception as exc: out['error']=f'{type(exc).__name__}:{exc}'
    print(json.dumps(out,separators=(',',':'))); return 0 if out['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
