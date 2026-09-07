#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, shutil, subprocess, tempfile, urllib.request, wave
from pathlib import Path

ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
JS=ROOT/'eira2/neural/web/communication.js'
BASE='http://127.0.0.1:8782'
EXPECTED_JS='fb5def022e94f225a677e199cf86f985da5a388aa5c980c8a7deb554f53ba92b'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def post(path, body, ctype, timeout):
    req=urllib.request.Request(BASE+path,data=body,headers={'Content-Type':ctype},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.status,json.loads(r.read().decode('utf-8'))

def synth_pcm():
    exe=shutil.which('espeak-ng') or shutil.which('espeak')
    if not exe: raise RuntimeError('speech_synthesizer_unavailable')
    with tempfile.TemporaryDirectory() as td:
        wav=Path(td)/'voice.wav'
        p=subprocess.run([exe,'-w',str(wav),'Eira voice qualification marker seven'],capture_output=True,text=True,timeout=30)
        if p.returncode: raise RuntimeError('speech_synthesis_failed:'+p.stderr[-400:])
        with wave.open(str(wav),'rb') as w:
            if w.getnchannels()!=1 or w.getsampwidth()!=2: raise RuntimeError('unexpected_synth_pcm_format')
            return w.getframerate(),w.readframes(w.getnframes())

def main():
    checks={}
    text=JS.read_text(encoding='utf-8')
    checks['js_sha_match']=sha(JS)==EXPECTED_JS
    markers=['INTENT_KEY','rememberIntent(true)',"ensureArmed('automatic')",'track.onended','context.onstatechange','visibilitychange','pageshow','/v1/ambient?sample_rate=16000','/v1/listen?sample_rate=16000']
    checks['lifecycle_markers']=all(x in text for x in markers)
    checks['no_destructive_pagehide']="pagehide',()=>{shutdown()" not in text

    text_error=None; text_payload={}
    try:
        status,text_payload=post('/v1/text',json.dumps({'text':'Eira voice qualification marker seven'}).encode(),'application/json',300)
        checks['text_http_200']=status==200
        checks['text_ok']=text_payload.get('ok') is True
        checks['text_response_present']=bool(text_payload.get('response') or (text_payload.get('result') or {}).get('response') or (text_payload.get('result') or {}).get('text'))
    except Exception as exc:
        text_error=f'{type(exc).__name__}:{exc}'
        checks['text_http_200']=checks['text_ok']=checks['text_response_present']=False

    voice_error=None; voice={}
    try:
        rate,pcm=synth_pcm()
        status,voice=post(f'/v1/listen?sample_rate={rate}&channels=1&sample_width=2',pcm,'application/octet-stream',360)
        checks['listen_http_200']=status==200
        checks['listen_ok']=voice.get('ok') is True
        checks['transcript_present']=bool(voice.get('utterance') or voice.get('text'))
        result=voice.get('result') or voice
        checks['voice_response_present']=bool(result.get('response') or result.get('text') or voice.get('response'))
    except Exception as exc:
        voice_error=f'{type(exc).__name__}:{exc}'
        checks['listen_http_200']=checks['listen_ok']=checks['transcript_present']=checks['voice_response_present']=False

    speaker_detail=''
    pactl=shutil.which('pactl')
    if pactl:
        p=subprocess.run([pactl,'list','sinks'],capture_output=True,text=True,timeout=15)
        speaker_detail=((p.stdout or '')+(p.stderr or ''))[-12000:]
        checks['flashcube_observed']='flashcube' in speaker_detail.casefold()
    else:
        checks['flashcube_observed']=False
        speaker_detail='pactl_unavailable'

    frontend_ok=all(checks[k] for k in ('js_sha_match','lifecycle_markers','no_destructive_pagehide'))
    conversation_ok=all(checks[k] for k in ('text_http_200','text_ok','text_response_present'))
    microphone_ok=all(checks[k] for k in ('listen_http_200','listen_ok','transcript_present','voice_response_present'))
    speaker_ok=checks['flashcube_observed']
    full_end_to_end_ok=frontend_ok and conversation_ok and microphone_ok and speaker_ok

    out={
        'schema':'eira2_voice_path_diagnostic_v2',
        'ok':full_end_to_end_ok,
        'full_end_to_end_ok':full_end_to_end_ok,
        'frontend_lifecycle_ok':frontend_ok,
        'conversation_path_ok':conversation_ok,
        'microphone_transcription_path_ok':microphone_ok,
        'speaker_routing_ok':speaker_ok,
        'checks':checks,
        'js_sha256':sha(JS),
        'text_error':text_error,
        'voice_error':voice_error,
        'text_result':text_payload,
        'voice_result':voice,
        'speaker_detail_tail':speaker_detail[-3000:],
    }
    print(json.dumps(out,sort_keys=True))
    return 0 if full_end_to_end_ok else 2

if __name__=='__main__':
    raise SystemExit(main())
