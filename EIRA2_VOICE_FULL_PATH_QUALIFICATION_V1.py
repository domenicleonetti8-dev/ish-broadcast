#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, shutil, subprocess, tempfile, urllib.request, wave
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
JS=ROOT/'eira2/neural/web/communication.js'
BASE='http://127.0.0.1:8782'
EXPECTED_JS='fb5def022e94f225a677e199cf86f985da5a388aa5c980c8a7deb554f53ba92b'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def post(path, body, ctype, timeout=300):
    req=urllib.request.Request(BASE+path,data=body,headers={'Content-Type':ctype},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read(); return r.status,json.loads(raw.decode('utf-8'))
def synth_pcm():
    exe=shutil.which('espeak-ng') or shutil.which('espeak')
    if not exe: raise RuntimeError('speech_synthesizer_unavailable')
    with tempfile.TemporaryDirectory() as td:
        wav=Path(td)/'voice.wav'
        p=subprocess.run([exe,'-w',str(wav),'Eira voice path qualification'],capture_output=True,text=True,timeout=30)
        if p.returncode: raise RuntimeError('speech_synthesis_failed:'+p.stderr[-400:])
        with wave.open(str(wav),'rb') as w:
            if w.getnchannels()!=1 or w.getsampwidth()!=2: raise RuntimeError('unexpected_synth_pcm_format')
            rate=w.getframerate(); pcm=w.readframes(w.getnframes())
        return rate,pcm

def main():
    checks={}
    text=JS.read_text(encoding='utf-8')
    checks['js_sha_match']=sha(JS)==EXPECTED_JS
    required=['INTENT_KEY','rememberIntent(true)','ensureArmed(\'automatic\')','track.onended','context.onstatechange','visibilitychange','pageshow','/v1/ambient?sample_rate=16000','/v1/listen?sample_rate=16000']
    checks['lifecycle_markers']=all(x in text for x in required)
    checks['no_destructive_pagehide']="pagehide',()=>{shutdown()" not in text
    status,payload=post('/v1/text',json.dumps({'text':'Eira voice path qualification ping'}).encode(),'application/json',300)
    checks['text_http_200']=status==200
    checks['text_ok']=payload.get('ok') is True
    checks['text_response_present']=bool(payload.get('response') or (payload.get('result') or {}).get('response') or (payload.get('result') or {}).get('text'))
    rate,pcm=synth_pcm()
    status,voice=post(f'/v1/listen?sample_rate={rate}&channels=1&sample_width=2',pcm,'application/octet-stream',360)
    checks['listen_http_200']=status==200
    checks['listen_ok']=voice.get('ok') is True
    checks['transcript_present']=bool(voice.get('utterance') or voice.get('text'))
    result=voice.get('result') or voice
    checks['voice_response_present']=bool(result.get('response') or result.get('text') or voice.get('response'))
    pactl=shutil.which('pactl')
    if pactl:
        p=subprocess.run([pactl,'list','sinks'],capture_output=True,text=True,timeout=15)
        sinks=(p.stdout or '')+(p.stderr or '')
        checks['flashcube_observed']='flashcube' in sinks.casefold()
    else:
        checks['flashcube_observed']=False
    ok=all(checks.values())
    out={'schema':'eira2_voice_full_path_qualification_v1','ok':ok,'checks':checks,'js_sha256':sha(JS),'text_result':payload,'voice_result':voice}
    print(json.dumps(out,sort_keys=True))
    return 0 if ok else 2
if __name__=='__main__': raise SystemExit(main())
