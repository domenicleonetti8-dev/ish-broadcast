#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request, urllib.error, time

BASE='http://127.0.0.1:8782'
CASES=[
 ('greeting','How are you my friend?'),
 ('causal','Why does a metal spoon feel colder than a wooden spoon in the same room? Explain the mechanism, not just the answer.'),
 ('analogy','Explain the relationship between voltage, current, and resistance using a water-system analogy, then tell me exactly where that analogy breaks down.'),
 ('transfer','If a city traffic network is like a neural network, what corresponds to synapses, inhibition, and plasticity? Give the analogy and two important limits.'),
 ('ambiguity','I saw a bat near the bank. What are the plausible meanings, and what question would you ask before assuming one?'),
 ('provenance','What components actually participated in producing this answer? Only claim what you can verify from the current runtime path.'),
 ('weird_science','Suppose gravity suddenly became 1% stronger for exactly 30 seconds worldwide. What immediate effects would be measurable, and what dramatic effects would probably NOT happen?'),
]

def request(path,data=None,timeout=180):
    body=None; headers={}
    if data is not None:
        body=json.dumps(data).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+path,data=body,headers=headers,method='POST' if body is not None else 'GET')
    t=time.monotonic()
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read(); status=getattr(r,'status',200)
    elapsed=round(time.monotonic()-t,3)
    try: parsed=json.loads(raw.decode())
    except Exception: parsed={'raw':raw.decode(errors='replace')}
    return status,elapsed,parsed

out={'schema':'eira2_real_conversation_regression_v1','ok':False,'mutates_live':False,'cases':[]}
try:
    hs,he,h=request('/health',timeout=20); out['health']={'status':hs,'elapsed':he,'body':h}
    for name,prompt in CASES:
        try:
            status,elapsed,body=request('/v1/text',{'text':prompt,'source':'transport_regression'},timeout=240)
            answer=''
            if isinstance(body,dict):
                for k in ('text','reply','response'):
                    if isinstance(body.get(k),str) and body.get(k).strip(): answer=body[k].strip(); break
                if not answer and isinstance(body.get('result'),dict):
                    for k in ('text','reply','response'):
                        if isinstance(body['result'].get(k),str) and body['result'].get(k).strip(): answer=body['result'][k].strip(); break
            out['cases'].append({'name':name,'prompt':prompt,'status':status,'elapsed_seconds':elapsed,'answer':answer,'body':body,'nonempty':bool(answer)})
        except Exception as e:
            out['cases'].append({'name':name,'prompt':prompt,'error':f'{type(e).__name__}:{e}','nonempty':False})
    out['ok']=hs==200 and all(c.get('status')==200 and c.get('nonempty') for c in out['cases'])
except Exception as e:
    out['error']=f'{type(e).__name__}:{e}'
print(json.dumps(out,separators=(',',':')))
raise SystemExit(0 if out.get('ok') else 1)
