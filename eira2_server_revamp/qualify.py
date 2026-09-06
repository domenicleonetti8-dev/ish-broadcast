#!/usr/bin/env python3
"""Isolated end-to-end qualification for the EIRA 2 unified server. Never touches LIVE."""
from __future__ import annotations
import hashlib,http.client,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent; SERVER=HERE/"server.py"
def free_port():
    with socket.socket() as s: s.bind(("127.0.0.1",0)); return int(s.getsockname()[1])
def request(port,method,path,body=None,content_type="application/json"):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=8); headers={"Content-Type":content_type} if body is not None else {}; c.request(method,path,body=body,headers=headers); r=c.getresponse(); raw=r.read(); status=r.status; ctype=r.getheader("Content-Type") or ""; c.close()
    return (status,json.loads(raw.decode())) if "application/json" in ctype else (status,raw)
def jbody(x): return json.dumps(x).encode()
def oversize_header_status(port:int)->int:
    with socket.create_connection(("127.0.0.1",port),timeout=4) as s:
        s.sendall(b"POST /api/voice HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: audio/wav\r\nContent-Length: 10485761\r\nConnection: close\r\n\r\n")
        first=s.recv(128).split(b"\r\n",1)[0].decode("ascii","replace")
    return int(first.split()[1])
def wait_server(port,proc,timeout=8):
    until=time.time()+timeout
    while time.time()<until:
        if proc.poll() is not None:
            out,err=proc.communicate(); raise RuntimeError(f"server_exited:{proc.returncode}:{out[-800:]}:{err[-800:]}")
        try:
            if request(port,"GET","/api/health")[0] in {200,503}: return
        except Exception: pass
        time.sleep(.08)
    raise RuntimeError("server_start_timeout")
def check(name,ok,detail=""):
    if not ok: raise AssertionError(f"{name}:{detail}")
    print("PASS",name,(":: "+detail) if detail else "")
def fixture(path:Path):
    path.write_text(r'''#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=json.load(sys.stdin)
if p.get("probe"): print(json.dumps({"ok":True,"ready":True})); raise SystemExit
if p.get("task")=="speech_to_text":
 a=Path(p["audio_path"])
 if not a.is_file() or a.stat().st_size<4: raise SystemExit(7)
 print(json.dumps({"text":"blue comet voice fixture"})); raise SystemExit
if p.get("action")=="launch": print(json.dumps({"url":"http://127.0.0.1:8787/","status":"ready"})); raise SystemExit
text=str(p.get("text") or "")
if not text: raise SystemExit(8)
print(json.dumps({"text":"Eira canonical reply: "+text,"source":p.get("source")}))
''')
def main():
    checks=0
    with tempfile.TemporaryDirectory(prefix="eira2-server-qual-") as td:
        root=Path(td); live=root/"LIVE"; live.mkdir(); state=root/"state"; ar=live/"artifacts"; ar.mkdir(); (ar/"test.usdz").write_bytes(b"PK\x03\x04EIRA2-USDZ-FIXTURE")
        overview=live/"overview.json"; fibers=live/"fibers.json"; activity=live/"activity.json"
        overview.write_text(json.dumps({"nodes":[{"id":"core","role":"core"},{"id":"voice","role":"voice"},{"id":"conversation","role":"conversation"}]})); fibers.write_text(json.dumps({"fibers":[{"source":"core","target":"voice"},{"source":"voice","target":"conversation"}]})); activity.write_text(json.dumps({"activity":[{"id":"conversation","strength":1.0}]}))
        bridge=live/"bridge.py"; fixture(bridge); port=free_port(); cmd=f"{sys.executable} {bridge}"; env=dict(os.environ); env.update({"EIRA2_HOST":"127.0.0.1","EIRA2_PORT":str(port),"EIRA2_LIVE_ROOT":str(live),"EIRA2_STATE_DIR":str(state),"EIRA2_CONVERSATION_CMD":cmd,"EIRA2_CONVERSATION_PROBE_CMD":cmd,"EIRA2_VOICE_CMD":cmd,"EIRA2_VOICE_PROBE_CMD":cmd,"EIRA2_INVENTION_CMD":cmd,"EIRA2_INVENTION_PROBE_CMD":cmd,"EIRA2_NEURAL_OVERVIEW":str(overview),"EIRA2_NEURAL_FIBERS":str(fibers),"EIRA2_NEURAL_ACTIVITY":str(activity),"EIRA2_AR_ROOTS":str(ar),"EIRA2_PACKAGE_MANIFEST":""})
        proc=subprocess.Popen([sys.executable,str(SERVER)],cwd=str(HERE),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            wait_server(port,proc)
            status,h=request(port,"GET","/api/health"); check("health_all_bridges_green",status==200 and h.get("ok") and h.get("port")==port and h["bridges"]["voice_to_text"]["healthy"]); checks+=1
            status,d=request(port,"GET","/api/doctor"); check("deep_forensic_doctor",status==200 and d.get("ok") and d["bridges"]["voice_to_text"]["healthy"]); checks+=1
            status,a=request(port,"POST","/api/activate",jbody({"active":True})); check("activate_route",status==200 and a["runtime"]["active"]); checks+=1
            status,m=request(port,"POST","/api/mute",jbody({"muted":True})); check("mute_route",status==200 and m["runtime"]["muted"]); checks+=1
            status,vt=request(port,"POST","/api/voice",b"RIFFfake-valid-audio-fixture","audio/wav"); check("voice_audio_transcription",status==200 and vt.get("text")=="blue comet voice fixture"); checks+=1
            status,vr=request(port,"POST","/api/conversation",jbody({"text":vt["text"],"source":"voice"})); check("voice_reuses_canonical_conversation",status==200 and vr["result"].get("source")=="voice" and "blue comet" in vr["result"].get("text","")); checks+=1
            status,tr=request(port,"POST","/api/conversation",jbody({"text":"typed fixture","source":"text"})); check("typed_conversation_same_authority",status==200 and tr["result"].get("source")=="text"); checks+=1
            check("empty_conversation_rejected",request(port,"POST","/api/conversation",jbody({"text":""}))[0]==400); checks+=1
            check("oversize_voice_rejected",oversize_header_status(port)==400,"rejected from Content-Length without consuming payload"); checks+=1
            status,inv=request(port,"POST","/api/invention/launch",jbody({"action":"launch"})); check("invention_bridge",status==200 and inv["result"].get("url","").endswith("8787/")); checks+=1
            ok=True
            for ep in ("overview","fibers","activity"):
                s,p=request(port,"GET",f"/api/neural/{ep}"); ok &= s==200 and p.get("ok") is True
            check("neural_three_path_contract",ok); checks+=1
            status,lst=request(port,"GET","/api/ar/list"); check("apple_ar_list",status==200 and lst.get("items") and lst["items"][0]["name"]=="test.usdz"); checks+=1
            status,model=request(port,"GET","/api/ar/file/0/test.usdz"); check("apple_ar_usdz_route",status==200 and isinstance(model,bytes) and model.startswith(b"PK")); checks+=1
            check("ar_path_escape_rejected",request(port,"GET","/api/ar/file/0/../overview.json")[0] in {400,404}); checks+=1
            status,html=request(port,"GET","/"); text=html.decode() if isinstance(html,bytes) else ""; markers=["MediaRecorder","vadLoop","/api/voice","submitText(transcript,'voice')","/api/conversation","window.isSecureContext","APPLE AR","INVENTION LAB","ACTIVATE EIRA","FREE-HOVERING 360° NEURAL TOPOLOGY"]
            check("continuous_voice_visual_control_surface",status==200 and all(x in text for x in markers)); checks+=1
            check("voice_transcript_frontend_convergence",text.count("submitText(transcript,'voice')")==1 and "submitText(text,'text')" in text); checks+=1
            second=subprocess.run([sys.executable,str(SERVER)],cwd=str(HERE),env=env,capture_output=True,text=True,timeout=4); check("live_instance_lock_protected",second.returncode!=0 and "instance_already_running" in second.stderr+second.stdout); checks+=1
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        check("lock_cleanup",not (state/"server.pid").exists()); checks+=1
        sys.path.insert(0,str(HERE)); from hardening import verify_manifest
        protected=live/"protected.txt"; protected.write_text("canonical"); digest=hashlib.sha256(protected.read_bytes()).hexdigest(); manifest=live/"manifest.json"; manifest.write_text(json.dumps({"files":{"protected.txt":{"size":protected.stat().st_size,"sha256":digest}}}))
        check("manifest_integrity_green",verify_manifest(str(manifest),live)["healthy"]); checks+=1
        protected.write_text("corrupt"); check("manifest_corruption_fail_closed",not verify_manifest(str(manifest),live)["healthy"]); checks+=1
        manifest.write_text(json.dumps({"files":{"../escape":{"size":0,"sha256":""}}})); check("manifest_path_escape_fail_closed",not verify_manifest(str(manifest),live)["healthy"]); checks+=1
    print(f"EIRA2_SERVER_QUALIFICATION=PASS checks={checks}"); return 0
if __name__=="__main__": raise SystemExit(main())
