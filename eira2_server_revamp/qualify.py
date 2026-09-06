#!/usr/bin/env python3
"""Isolated end-to-end qualification for the EIRA 2 unified server.

Uses temporary fixtures only. Never reads or mutates Easystore LIVE.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE / "server.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def request(port: int, method: str, path: str, body: bytes | None = None, content_type: str = "application/json"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    headers = {"Content-Type": content_type} if body is not None else {}
    c.request(method, path, body=body, headers=headers)
    r = c.getresponse(); raw = r.read(); status = r.status; c.close()
    if "application/json" in (r.getheader("Content-Type") or ""):
        return status, json.loads(raw.decode("utf-8"))
    return status, raw


def jbody(obj: dict) -> bytes:
    return json.dumps(obj).encode("utf-8")


def wait_server(port: int, proc: subprocess.Popen, timeout: float = 8.0) -> None:
    until = time.time() + timeout
    while time.time() < until:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"server_exited:{proc.returncode}:{out[-1200:]}:{err[-1200:]}")
        try:
            status, _ = request(port, "GET", "/api/health")
            if status in {200, 503}:
                return
        except Exception:
            pass
        time.sleep(.08)
    raise RuntimeError("server_start_timeout")


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        raise AssertionError(f"{name}: {detail}")
    print(f"PASS {name}" + (f" :: {detail}" if detail else ""))


def write_fixture(path: Path) -> None:
    path.write_text(r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
p=json.load(sys.stdin)
if p.get("probe"):
    print(json.dumps({"ok":True,"ready":True})); raise SystemExit
if p.get("task")=="speech_to_text":
    a=Path(p["audio_path"])
    if not a.is_file() or a.stat().st_size < 4: raise SystemExit(7)
    print(json.dumps({"text":"blue comet voice fixture"})); raise SystemExit
if p.get("action")=="launch":
    print(json.dumps({"url":"http://127.0.0.1:8787/","status":"ready"})); raise SystemExit
text=str(p.get("text") or "")
if not text: raise SystemExit(8)
print(json.dumps({"text":"Eira canonical reply: "+text,"source":p.get("source")}))
''', encoding="utf-8")


def main() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="eira2-server-qual-") as td:
        root = Path(td)
        live = root / "LIVE"; live.mkdir()
        state = root / "state"
        ar = live / "artifacts"; ar.mkdir()
        (ar / "test.usdz").write_bytes(b"PK\x03\x04EIRA2-USDZ-FIXTURE")
        overview = live / "overview.json"; fibers = live / "fibers.json"; activity = live / "activity.json"
        overview.write_text(json.dumps({"nodes":[{"id":"core","role":"core"},{"id":"voice","role":"voice"},{"id":"conversation","role":"conversation"}]}))
        fibers.write_text(json.dumps({"fibers":[{"source":"core","target":"voice"},{"source":"voice","target":"conversation"}]}))
        activity.write_text(json.dumps({"activity":[{"id":"conversation","strength":1.0}]}))
        bridge = live / "bridge.py"; write_fixture(bridge)
        port = free_port()
        cmd = f"{sys.executable} {bridge}"
        env = dict(os.environ)
        env.update({
            "EIRA2_HOST":"127.0.0.1", "EIRA2_PORT":str(port), "EIRA2_LIVE_ROOT":str(live), "EIRA2_STATE_DIR":str(state),
            "EIRA2_CONVERSATION_CMD":cmd, "EIRA2_CONVERSATION_PROBE_CMD":cmd,
            "EIRA2_VOICE_CMD":cmd, "EIRA2_VOICE_PROBE_CMD":cmd,
            "EIRA2_INVENTION_CMD":cmd, "EIRA2_INVENTION_PROBE_CMD":cmd,
            "EIRA2_NEURAL_OVERVIEW":str(overview), "EIRA2_NEURAL_FIBERS":str(fibers), "EIRA2_NEURAL_ACTIVITY":str(activity),
            "EIRA2_AR_ROOTS":str(ar), "EIRA2_PACKAGE_MANIFEST":"",
        })
        proc = subprocess.Popen([sys.executable, str(SERVER)], cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            wait_server(port, proc)
            status, health = request(port,"GET","/api/health")
            check("health_all_bridges_green", status==200 and health.get("ok") and health.get("port")==port and health["bridges"]["voice_to_text"]["healthy"]); checks+=1

            status, doctor = request(port,"GET","/api/doctor")
            check("deep_forensic_doctor", status==200 and doctor.get("ok") and doctor["bridges"]["voice_to_text"]["healthy"]); checks+=1

            status, act = request(port,"POST","/api/activate",jbody({"active":True}))
            check("activate_route", status==200 and act["runtime"]["active"]); checks+=1
            status, mute = request(port,"POST","/api/mute",jbody({"muted":True}))
            check("mute_route", status==200 and mute["runtime"]["muted"]); checks+=1

            audio = b"RIFFfake-valid-audio-fixture"
            status, vt = request(port,"POST","/api/voice",audio,"audio/wav")
            check("voice_audio_transcription", status==200 and vt.get("text")=="blue comet voice fixture"); checks+=1
            status, vr = request(port,"POST","/api/conversation",jbody({"text":vt["text"],"source":"voice"}))
            check("voice_reuses_canonical_conversation", status==200 and vr["result"].get("source")=="voice" and "blue comet" in vr["result"].get("text", "")); checks+=1

            status, tr = request(port,"POST","/api/conversation",jbody({"text":"typed fixture","source":"text"}))
            check("typed_conversation_same_authority", status==200 and tr["result"].get("source")=="text"); checks+=1
            status, bad = request(port,"POST","/api/conversation",jbody({"text":""}))
            check("empty_conversation_rejected", status==400); checks+=1
            huge = b"x"*(10*1024*1024+1)
            status, _ = request(port,"POST","/api/voice",huge,"audio/wav")
            check("oversize_voice_rejected", status==400); checks+=1

            status, inv = request(port,"POST","/api/invention/launch",jbody({"action":"launch"}))
            check("invention_bridge", status==200 and inv["result"].get("url","").endswith("8787/")); checks+=1

            ok_neural=True
            for endpoint in ("overview","fibers","activity"):
                s,p=request(port,"GET",f"/api/neural/{endpoint}"); ok_neural &= s==200 and p.get("ok") is True
            check("neural_three_path_contract", ok_neural); checks+=1
            status, listing=request(port,"GET","/api/ar/list")
            check("apple_ar_list", status==200 and listing.get("items") and listing["items"][0]["name"]=="test.usdz"); checks+=1
            status, model=request(port,"GET","/api/ar/file/0/test.usdz")
            check("apple_ar_usdz_route", status==200 and isinstance(model,bytes) and model.startswith(b"PK")); checks+=1
            status,_=request(port,"GET","/api/ar/file/0/../overview.json")
            check("ar_path_escape_rejected", status in {400,404}); checks+=1

            status, html=request(port,"GET","/")
            text=html.decode("utf-8") if isinstance(html,bytes) else ""
            markers=["MediaRecorder","vadLoop","/api/voice","submitText(transcript,'voice')","/api/conversation","window.isSecureContext","APPLE AR","INVENTION LAB","ACTIVATE EIRA","FREE-HOVERING 360° NEURAL TOPOLOGY"]
            check("continuous_voice_visual_control_surface", status==200 and all(m in text for m in markers), "all voice/AR/neural/control markers present"); checks+=1
            check("voice_transcript_frontend_convergence", text.count("submitText(transcript,'voice')")==1 and "submitText(text,'text')" in text); checks+=1

            second=subprocess.run([sys.executable,str(SERVER)],cwd=str(HERE),env=env,capture_output=True,text=True,timeout=4)
            check("live_instance_lock_protected", second.returncode!=0 and "instance_already_running" in (second.stderr+second.stdout)); checks+=1
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        check("lock_cleanup", not (state/"server.pid").exists()); checks+=1

        # Direct manifest fail-closed checks remain part of server package qualification.
        sys.path.insert(0,str(HERE)); from hardening import verify_manifest
        protected=live/"protected.txt"; protected.write_text("canonical")
        digest=hashlib.sha256(protected.read_bytes()).hexdigest()
        manifest=live/"manifest.json"; manifest.write_text(json.dumps({"files":{"protected.txt":{"size":protected.stat().st_size,"sha256":digest}}}))
        check("manifest_integrity_green", verify_manifest(str(manifest),live)["healthy"]); checks+=1
        protected.write_text("corrupt")
        check("manifest_corruption_fail_closed", not verify_manifest(str(manifest),live)["healthy"]); checks+=1
        manifest.write_text(json.dumps({"files":{"../escape":{"size":0,"sha256":""}}}))
        check("manifest_path_escape_fail_closed", not verify_manifest(str(manifest),live)["healthy"]); checks+=1

    print(f"EIRA2_SERVER_QUALIFICATION=PASS checks={checks}")
    return 0

if __name__=="__main__": raise SystemExit(main())
