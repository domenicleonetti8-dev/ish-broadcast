#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

MIC_SIGNATURES = ['/v1/listen','getUserMedia','packPCM16','state.active','transcribing','inactive']

class Assets(HTMLParser):
    def __init__(self):
        super().__init__(); self.assets=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='script' and a.get('src'): self.assets.append(a['src'])
        if tag=='link' and a.get('href') and str(a.get('rel','')).lower().find('stylesheet')>=0: self.assets.append(a['href'])

def req(url, *, data=None, headers=None, timeout=15):
    r=urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as h:
            body=h.read()
            return {'ok':True,'status':getattr(h,'status',200),'content_type':h.headers.get('Content-Type'),'bytes':len(body),'body':body}
    except Exception as e:
        return {'ok':False,'error':f'{type(e).__name__}:{e}','status':getattr(e,'code',None),'content_type':None,'bytes':0,'body':b''}

def source_context(text:str):
    lines=text.splitlines(); hits=[]
    for i,line in enumerate(lines):
        matched=[s for s in MIC_SIGNATURES if s in line]
        if matched: hits.append((i,matched))
    spans=[]; used=set()
    for i,_ in hits:
        start=max(0,i-70); end=min(len(lines),i+71); key=(start,end)
        if key in used: continue
        used.add(key)
        spans.append({'start_line':start+1,'end_line':end,'source':'\n'.join(f'{n+1:05d}: {lines[n]}' for n in range(start,end))})
    return {
        'matched_signatures':sorted({s for _,m in hits for s in m}),
        'match_line_numbers':[i+1 for i,_ in hits[:100]],
        'contexts':spans[:12],
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base',default='http://127.0.0.1:8782/'); ap.add_argument('--out',default='eira_probe/revamp2_frontend_acceptance.json'); a=ap.parse_args()
    base=a.base if a.base.endswith('/') else a.base+'/'
    out={'schema':'eira2_revamp2_frontend_acceptance_v2','mode':'read_only','mutates_live':False,'base':base,'checks':{},'mic_source_matches':[]}
    root=req(base); rev=req(base+'?revamp=2')
    out['checks']['root']={k:v for k,v in root.items() if k!='body'}
    out['checks']['revamp2']={k:v for k,v in rev.items() if k!='body'}
    assets=[]
    if rev['ok']:
        text=rev['body'].decode('utf-8','replace')
        out['checks']['revamp2']['html_has_body']=bool(re.search(r'<body\b',text,re.I))
        out['checks']['revamp2']['html_has_script']=bool(re.search(r'<script\b',text,re.I))
        out['checks']['revamp2']['sha256']=hashlib.sha256(rev['body']).hexdigest()
        p=Assets(); p.feed(text)
        for rel in p.assets:
            u=urljoin(base,rel); r=req(u)
            meta={'asset':rel,'url':u,**{k:v for k,v in r.items() if k!='body'}}
            if r.get('ok'):
                meta['sha256']=hashlib.sha256(r['body']).hexdigest()
                ctype=str(r.get('content_type') or '').lower()
                if rel.lower().endswith('.js') or 'javascript' in ctype:
                    js=r['body'].decode('utf-8','replace'); ctx=source_context(js)
                    if ctx['matched_signatures']:
                        out['mic_source_matches'].append({'asset':rel,'url':u,'sha256':meta['sha256'],'bytes':len(r['body']),**ctx})
            assets.append(meta)
    out['assets']=assets
    payload=json.dumps({'text':'How are you?','source':'frontend_acceptance_probe'}).encode()
    chat=req(urljoin(base,'v1/text'),data=payload,headers={'Content-Type':'application/json'})
    chat_body=chat.pop('body',b'')
    out['checks']['v1_text']={**chat,'json':None}
    try: out['checks']['v1_text']['json']=json.loads(chat_body.decode('utf-8','replace')) if chat_body else None
    except Exception: out['checks']['v1_text']['body_preview']=chat_body[:500].decode('utf-8','replace')
    failures=[]
    if not rev.get('ok') or rev.get('bytes',0)<64: failures.append('revamp2_document_invalid')
    for x in assets:
        if not x.get('ok') or x.get('bytes',0)==0: failures.append('asset_failed:'+x['asset'])
    if not out['checks']['v1_text'].get('ok'): failures.append('v1_text_failed')
    if not out['mic_source_matches']: failures.append('mic_source_not_found_in_served_js')
    out['failures']=failures; out['ok']=not failures
    path=Path(a.out); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'EIRA2_REVAMP2_ACCEPTANCE':'PASS' if out['ok'] else 'FAIL','failures':failures,'mic_source_matches':len(out['mic_source_matches']),'out':str(path)},indent=2))
    return 0 if out['ok'] else 2
if __name__=='__main__': raise SystemExit(main())
