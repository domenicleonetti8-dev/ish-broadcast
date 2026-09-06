#!/usr/bin/env python3
"""Self-contained qualification for the isolated EIRA 2 server.

Runs only against temporary fixtures. It does not touch Easystore LIVE.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "server.py"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def request(base: str, path: str, method: str = "GET", body=None, expect=(200,)):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            status = r.status
            payload = r.read()
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        status = e.code
        payload = e.read()
        ctype = e.headers.get("Content-Type", "")
    if status not in expect:
        raise AssertionError(f"{method} {path}: expected {expect}, got {status}: {payload[:500]!r}")
    if "application/json" in ctype:
        return status, json.loads(payload.decode())
    return status, payload


def main() -> int:
    checks = []
    def ok(name):
        checks.append(name)
        print(f"PASS {name}")

    with tempfile.TemporaryDirectory(prefix="eira2_revamp_qual_") as td:
        t = Path(td)
        live = t / "LIVE"
        state = t / "state"
        ar = t / "ar"
        live.mkdir(); state.mkdir(); ar.mkdir()

        overview = t / "overview.json"
        fibers = t / "fibers.json"
        activity = t / "activity.json"
        overview.write_text(json.dumps({"nodes":[
            {"id":"left.reasoning","hemisphere":"left"},
            {"id":"right.voice","hemisphere":"right"},
            {"id":"core.supervisor","region":"core"}
        ]}))
        fibers.write_text(json.dumps({"fibers":[
            {"source":"left.reasoning","target":"core.supervisor"},
            {"source":"core.supervisor","target":"right.voice"}
        ]}))
        activity.write_text(json.dumps({"nodes":[{"id":"left.reasoning","activity":0.8}]}))
        (ar / "proof.usdz").write_bytes(b"USDC-ROUTE-PROOF")

        bridge = t / "bridge.py"
        bridge.write_text(
            "import json,sys\n"
            "d=json.load(sys.stdin)\n"
            "print(json.dumps({'text':'bridge-ok:'+str(d.get('text','')), 'status':'launched', 'url':None}))\n"
        )

        port = free_port()
        env = dict(os.environ)
        env.update({
            "EIRA2_HOST":"127.0.0.1",
            "EIRA2_PORT":str(port),
            "EIRA2_LIVE_ROOT":str(live),
            "EIRA2_STATE_DIR":str(state),
            "EIRA2_CONVERSATION_CMD":f"{sys.executable} {bridge}",
            "EIRA2_INVENTION_CMD":f"{sys.executable} {bridge}",
            "EIRA2_NEURAL_OVERVIEW":str(overview),
            "EIRA2_NEURAL_FIBERS":str(fibers),
            "EIRA2_NEURAL_ACTIVITY":str(activity),
            "EIRA2_AR_ROOTS":str(ar),
        })
        p = subprocess.Popen([sys.executable, str(SERVER)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        base = f"http://127.0.0.1:{port}"
        try:
            deadline=time.time()+8
            last=None
            while time.time()<deadline:
                try:
                    _, h=request(base,"/api/health")
                    last=h
                    break
                except Exception as e:
                    last=e; time.sleep(.1)
            if not isinstance(last,dict) or not last.get("ok"):
                raise AssertionError(f"health did not qualify: {last!r}")
            ok("health_all_bridges_green")

            _, r=request(base,"/api/activate","POST",{"active":True})
            assert r["runtime"]["active"] is True
            ok("activate_route")

            _, r=request(base,"/api/mute","POST",{"muted":True})
            assert r["runtime"]["muted"] is True
            ok("mute_route")

            _, r=request(base,"/api/conversation","POST",{"text":"hello"})
            assert r["result"]["text"]=="bridge-ok:hello"
            ok("conversation_bridge")

            _, r=request(base,"/api/invention/launch","POST",{"action":"launch"})
            assert r["result"]["status"]=="launched"
            ok("invention_bridge")

            _, r=request(base,"/api/neural/overview")
            assert len(r["data"]["nodes"])==3
            _, r=request(base,"/api/neural/fibers")
            assert len(r["data"]["fibers"])==2
            _, r=request(base,"/api/neural/activity")
            assert r["data"]["nodes"][0]["activity"]==0.8
            ok("neural_three_path_contract")

            _, r=request(base,"/api/ar/list")
            assert r["items"] and r["items"][0]["name"]=="proof.usdz"
            _, raw=request(base,"/api/ar/file/0/proof.usdz")
            assert raw==b"USDC-ROUTE-PROOF"
            ok("apple_ar_usdz_route")

            request(base,"/api/ar/file/0/../secret.usdz",expect=(400,404))
            ok("ar_path_escape_rejected")

            request(base,"/api/conversation","POST",{},expect=(400,))
            ok("empty_conversation_rejected")

            _, html=request(base,"/")
            assert b"ACTIVATE EIRA" in html and b"INVENTION LAB" in html and b"APPLE AR" in html
            ok("control_surface_served")

            # PID lock must represent the running server and not be silently overwritten.
            pid_file=state/"server.pid"
            assert pid_file.exists() and int(pid_file.read_text())==p.pid
            q=subprocess.run([sys.executable,str(SERVER)],env=env,capture_output=True,text=True,timeout=4)
            assert q.returncode!=0 and "already_running" in (q.stderr+q.stdout)
            ok("live_instance_lock_protected")

        finally:
            p.terminate()
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:p.kill()

        # lock should be cleaned after graceful shutdown
        if (state/"server.pid").exists():
            raise AssertionError("server pid lock survived graceful shutdown")
        ok("lock_cleanup")

    print(f"EIRA2_SERVER_QUALIFICATION=PASS checks={len(checks)}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
