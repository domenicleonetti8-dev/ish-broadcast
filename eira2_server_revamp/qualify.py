#!/usr/bin/env python3
"""Self-contained end-to-end qualification for the isolated EIRA 2 super server."""
from __future__ import annotations

import hashlib
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

from hardening import verify_manifest

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "server.py"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def request(base: str, path: str, method: str = "GET", body=None, expect=(200,)):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=7) as response:
            status = response.status
            payload = response.read()
            ctype = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read()
        ctype = exc.headers.get("Content-Type", "")
    if status not in expect:
        raise AssertionError(f"{method} {path}: expected {expect}, got {status}: {payload[:500]!r}")
    if "application/json" in ctype:
        return status, json.loads(payload.decode())
    return status, payload


def main() -> int:
    checks: list[str] = []

    def ok(name: str) -> None:
        checks.append(name)
        print(f"PASS {name}")

    with tempfile.TemporaryDirectory(prefix="eira2_super_qual_") as td:
        temp = Path(td)
        live = temp / "LIVE"
        state = temp / "state"
        ar = temp / "ar"
        live.mkdir(); state.mkdir(); ar.mkdir()

        overview = temp / "overview.json"
        fibers = temp / "fibers.json"
        activity = temp / "activity.json"
        overview.write_text(json.dumps({"nodes": [
            {"id": "left.reasoning", "hemisphere": "left"},
            {"id": "right.voice", "hemisphere": "right"},
            {"id": "core.supervisor", "region": "core"},
        ]}), encoding="utf-8")
        fibers.write_text(json.dumps({"fibers": [
            {"source": "core.supervisor", "target": "left.reasoning"},
            {"source": "core.supervisor", "target": "right.voice"},
        ]}), encoding="utf-8")
        activity.write_text(json.dumps({"nodes": [
            {"id": "left.reasoning", "activity": 0.8},
            {"id": "right.voice", "activity": 0.45},
        ]}), encoding="utf-8")
        (ar / "proof.usdz").write_bytes(b"USDC-ROUTE-PROOF")

        marker = live / "qualified.marker"
        marker.write_text("EIRA2-SUPER-SERVER", encoding="utf-8")
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        manifest = live / "manifest.json"
        manifest.write_text(json.dumps({"files": {
            "qualified.marker": {"size": marker.stat().st_size, "sha256": digest}
        }}), encoding="utf-8")

        bridge = temp / "bridge.py"
        bridge.write_text(
            "import json,sys\n"
            "d=json.load(sys.stdin)\n"
            "if d.get('probe'):\n"
            " print(json.dumps({'ok':True,'status':'ready'}))\n"
            "else:\n"
            " print(json.dumps({'text':'bridge-ok:'+str(d.get('text','')), 'status':'launched', 'url':None}))\n",
            encoding="utf-8",
        )
        bridge_cmd = f"{sys.executable} {bridge}"

        port = free_port()
        env = dict(os.environ)
        env.update({
            "EIRA2_HOST": "127.0.0.1",
            "EIRA2_PORT": str(port),
            "EIRA2_LIVE_ROOT": str(live),
            "EIRA2_STATE_DIR": str(state),
            "EIRA2_CONVERSATION_CMD": bridge_cmd,
            "EIRA2_CONVERSATION_PROBE_CMD": bridge_cmd,
            "EIRA2_INVENTION_CMD": bridge_cmd,
            "EIRA2_INVENTION_PROBE_CMD": bridge_cmd,
            "EIRA2_NEURAL_OVERVIEW": str(overview),
            "EIRA2_NEURAL_FIBERS": str(fibers),
            "EIRA2_NEURAL_ACTIVITY": str(activity),
            "EIRA2_AR_ROOTS": str(ar),
            "EIRA2_PACKAGE_MANIFEST": str(manifest),
        })

        proc = subprocess.Popen(
            [sys.executable, str(SERVER)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 10
            last = None
            while time.time() < deadline:
                try:
                    _, health = request(base, "/api/health")
                    last = health
                    if health.get("ok"):
                        break
                except Exception as exc:
                    last = exc
                time.sleep(.1)
            if not isinstance(last, dict) or not last.get("ok"):
                raise AssertionError(f"health did not qualify: {last!r}")
            ok("health_all_bridges_green")

            _, doctor = request(base, "/api/doctor")
            assert doctor["ok"] is True
            assert all(v["healthy"] for v in doctor["bridges"].values())
            assert doctor["manifest"]["healthy"] is True
            assert doctor["lock"]["healthy"] is True
            assert doctor["tls"]["healthy"] is True
            assert all(item["ok"] for item in doctor["semantic"] if item.get("severity") == "error")
            ok("deep_forensic_doctor")

            _, response = request(base, "/api/activate", "POST", {"active": True})
            assert response["runtime"]["active"] is True
            ok("activate_route")

            _, response = request(base, "/api/mute", "POST", {"muted": True})
            assert response["runtime"]["muted"] is True
            ok("mute_route")

            _, response = request(base, "/api/conversation", "POST", {"text": "hello"})
            assert response["result"]["text"] == "bridge-ok:hello"
            ok("conversation_bridge")

            _, response = request(base, "/api/invention/launch", "POST", {"action": "launch"})
            assert response["result"]["status"] == "launched"
            ok("invention_bridge")

            _, response = request(base, "/api/neural/overview")
            assert len(response["data"]["nodes"]) == 3
            _, response = request(base, "/api/neural/fibers")
            assert len(response["data"]["fibers"]) == 2
            _, response = request(base, "/api/neural/activity")
            assert len(response["data"]["nodes"]) == 2
            ok("neural_three_path_contract")

            _, response = request(base, "/api/ar/list")
            assert response["items"] and response["items"][0]["name"] == "proof.usdz"
            _, raw = request(base, "/api/ar/file/0/proof.usdz")
            assert raw == b"USDC-ROUTE-PROOF"
            ok("apple_ar_usdz_route")

            request(base, "/api/ar/file/0/../secret.usdz", expect=(400, 404))
            ok("ar_path_escape_rejected")

            request(base, "/api/conversation", "POST", {}, expect=(400,))
            ok("empty_conversation_rejected")

            _, html = request(base, "/")
            current_markers = (
                b"ACTIVATE EIRA", b"MUTE", b"SEND", b"INVENTION LAB", b"APPLE AR",
                b"FREE-HOVERING 360", b"/api/neural/activity", b"pathTo(",
                b"let cores=[]", b"paths:paths.slice(0,24)", b"pathEdges", b"pathNodes",
                b"nodeLabel", b'href="/reference.css"',
            )
            missing = [m.decode("utf-8", "replace") for m in current_markers if m not in html]
            assert not missing, f"current visual/topology markers missing: {missing}"
            _, skin = request(base, "/reference.css")
            for marker_text in (b"brainCard", b"compose", b"position:fixed", b"orbGlow"):
                assert marker_text in skin
            ok("live_visual_control_surface_served")
            ok("reference_hovering_brain_skin_served")

            pid_file = state / "server.pid"
            assert pid_file.exists() and int(pid_file.read_text()) == proc.pid
            duplicate = subprocess.run([sys.executable, str(SERVER)], env=env, capture_output=True, text=True, timeout=4)
            assert duplicate.returncode != 0 and "already_running" in (duplicate.stderr + duplicate.stdout)
            ok("live_instance_lock_protected")

            bad_manifest = live / "bad_manifest.json"
            bad_manifest.write_text(json.dumps({"files": {
                "qualified.marker": {"size": marker.stat().st_size + 1, "sha256": digest}
            }}), encoding="utf-8")
            bad = verify_manifest(str(bad_manifest), live)
            assert bad["healthy"] is False and "size_mismatch" in bad["detail"]
            ok("manifest_corruption_fail_closed")

            escape_manifest = live / "escape_manifest.json"
            escape_manifest.write_text(json.dumps({"files": {
                "../escape": {"size": 1}
            }}), encoding="utf-8")
            escaped = verify_manifest(str(escape_manifest), live)
            assert escaped["healthy"] is False and "manifest_path_escape" in escaped["detail"]
            ok("manifest_path_escape_fail_closed")

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()

        if (state / "server.pid").exists():
            raise AssertionError("server pid lock survived graceful shutdown")
        ok("lock_cleanup")

    print(f"EIRA2_SERVER_QUALIFICATION=PASS checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
