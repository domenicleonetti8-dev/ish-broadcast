from __future__ import annotations
import json, urllib.request, urllib.error, time

def get(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body=r.read().decode('utf-8','replace')
            return {'ok': True, 'status': r.status, 'body': body[:4000]}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}:{e}'}

def post_json(url, payload, timeout=90):
    data=json.dumps(payload).encode('utf-8')
    req=urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body=r.read().decode('utf-8','replace')
            parsed=None
            try: parsed=json.loads(body)
            except Exception: pass
            return {'ok': True, 'status': r.status, 'body': body[:8000], 'json': parsed}
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8','replace')
        return {'ok': False, 'status': e.code, 'body': body[:8000], 'error': f'HTTPError:{e.code}'}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}:{e}'}

health=get('http://127.0.0.1:8782/health')
text=post_json('http://127.0.0.1:8782/v1/text', {'text':'Hello Eira. Reply with a short live-path confirmation sentence.','source':'superprobe_qualification_v2'})
response_present=False
if text.get('ok') and isinstance(text.get('json'), dict):
    j=text['json']
    response_present=bool(str(j.get('text') or j.get('reply') or j.get('response') or '').strip())
result={
    'schema':'eira2_text_path_qualification_v2',
    'generated_unix':time.time(),
    'mutates_live':False,
    'health':health,
    'text':text,
    'health_ok': bool(health.get('ok') and health.get('status')==200),
    'text_http_200': bool(text.get('ok') and text.get('status')==200),
    'response_present': response_present,
}
result['ok']=result['health_ok'] and result['text_http_200'] and result['response_present']
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result['ok'] else 2)
