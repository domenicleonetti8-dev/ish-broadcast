#!/usr/bin/env python3
"""Isolated, fail-closed EIRA 2.0 super server.

The fast health surface validates resolvable runtime contracts. /api/doctor performs
deeper side-effect-free bridge probes, manifest integrity checks, neural semantic
validation, lock ownership checks, TLS consistency, and AR artifact verification.
Nothing here mutates Easystore LIVE during qualification.
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from doctor import semantic_neural_check
from hardening import verify_ar_roots, verify_command_bridge, verify_json_source, verify_manifest

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
HOST = os.environ.get("EIRA2_HOST", "0.0.0.0")
PORT = int(os.environ.get("EIRA2_PORT", "8787"))
LIVE_ROOT = Path(os.environ.get("EIRA2_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
STATE_DIR = Path(os.environ.get("EIRA2_STATE_DIR", str(HERE / ".state"))).resolve()
STATE_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = STATE_DIR / "server.pid"
RUNTIME_STATE = STATE_DIR / "runtime.json"

CONVERSATION_CMD = os.environ.get("EIRA2_CONVERSATION_CMD", "").strip()
CONVERSATION_PROBE_CMD = os.environ.get("EIRA2_CONVERSATION_PROBE_CMD", "").strip()
INVENTION_CMD = os.environ.get("EIRA2_INVENTION_CMD", "").strip()
INVENTION_PROBE_CMD = os.environ.get("EIRA2_INVENTION_PROBE_CMD", "").strip()
NEURAL_OVERVIEW = os.environ.get("EIRA2_NEURAL_OVERVIEW", "").strip()
NEURAL_FIBERS = os.environ.get("EIRA2_NEURAL_FIBERS", "").strip()
NEURAL_ACTIVITY = os.environ.get("EIRA2_NEURAL_ACTIVITY", "").strip()
PACKAGE_MANIFEST = os.environ.get("EIRA2_PACKAGE_MANIFEST", "").strip()
AR_ROOTS = [Path(p).resolve() for p in os.environ.get("EIRA2_AR_ROOTS", "").split(os.pathsep) if p.strip()]
TLS_CERT = os.environ.get("EIRA2_TLS_CERT", "").strip()
TLS_KEY = os.environ.get("EIRA2_TLS_KEY", "").strip()


def now() -> float:
    return time.time()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_runtime() -> dict[str, Any]:
    if RUNTIME_STATE.exists():
        try:
            data = json.loads(RUNTIME_STATE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"active": False, "muted": False, "started_at": now(), "last_error": None}


_RUNTIME = load_runtime()
_RUNTIME_LOCK = threading.RLock()


def set_runtime(**changes: Any) -> dict[str, Any]:
    with _RUNTIME_LOCK:
        _RUNTIME.update(changes)
        _RUNTIME["updated_at"] = now()
        atomic_json(RUNTIME_STATE, _RUNTIME)
        return dict(_RUNTIME)


def process_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_pid_lock() -> None:
    if PID_FILE.exists():
        try:
            old = int(PID_FILE.read_text().strip())
        except Exception:
            old = -1
        if process_alive(old):
            raise RuntimeError(f"eira2_server_instance_already_running:{old}")
        PID_FILE.unlink(missing_ok=True)
    tmp = PID_FILE.with_suffix(".tmp")
    tmp.write_text(str(os.getpid()), encoding="utf-8")
    os.replace(tmp, PID_FILE)


def release_pid_lock() -> None:
    try:
        if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except Exception:
        pass


@dataclass
class Bridge:
    name: str
    configured: bool
    healthy: bool
    detail: str


def _cmd_bridge(name: str, raw: str) -> Bridge:
    if not raw:
        return Bridge(name, False, False, "command_not_configured")
    try:
        argv = shlex.split(raw)
    except Exception as exc:
        return Bridge(name, True, False, f"invalid_command:{type(exc).__name__}:{exc}")
    if not argv:
        return Bridge(name, False, False, "empty_command")
    exe = argv[0]
    if os.path.sep in exe:
        ok = Path(exe).is_file()
    else:
        from shutil import which
        ok = which(exe) is not None
    return Bridge(name, True, ok, "resolved" if ok else f"executable_not_found:{exe}")


def _json_bridge(name: str, raw: str) -> Bridge:
    verified = verify_json_source(name, raw, LIVE_ROOT)
    return Bridge(name, verified.configured, verified.healthy, verified.detail)


def bridge_matrix() -> dict[str, dict[str, Any]]:
    bridges = [
        _cmd_bridge("conversation", CONVERSATION_CMD),
        _cmd_bridge("invention_lab", INVENTION_CMD),
        _json_bridge("neural_overview", NEURAL_OVERVIEW),
        _json_bridge("neural_fibers", NEURAL_FIBERS),
        _json_bridge("neural_activity", NEURAL_ACTIVITY),
    ]
    ar = verify_ar_roots(AR_ROOTS)
    bridges.append(Bridge("apple_ar", ar.configured, ar.healthy, ar.detail))
    return {b.name: asdict(b) for b in bridges}


def read_json_source(raw: str) -> Any:
    if not raw:
        raise RuntimeError("source_not_configured")
    path = Path(raw)
    if not path.is_absolute():
        path = LIVE_ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))


def safe_env() -> dict[str, str]:
    env = dict(os.environ)
    root = str(LIVE_ROOT)
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not current else root + os.pathsep + current
    env["EIRA2_LIVE_ROOT"] = root
    return env


def run_command(raw: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    if not raw:
        raise RuntimeError("bridge_command_not_configured")
    argv = shlex.split(raw)
    cp = subprocess.run(
        argv,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(LIVE_ROOT),
        env=safe_env(),
        timeout=timeout,
        check=False,
    )
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "bridge_failed").strip()[-4000:]
        raise RuntimeError(f"bridge_exit_{cp.returncode}:{err}")
    text = (cp.stdout or "").strip()
    if not text:
        raise RuntimeError("bridge_returned_empty_output")
    try:
        out = json.loads(text)
    except Exception:
        out = {"text": text}
    return out if isinstance(out, dict) else {"result": out}


def list_usdz() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, root in enumerate(AR_ROOTS):
        if not root.is_dir():
            continue
        for path in root.rglob("*.usdz"):
            try:
                rel = path.relative_to(root).as_posix()
                st = path.stat()
                items.append({"root": idx, "path": rel, "name": path.name, "size": st.st_size, "mtime": st.st_mtime})
            except Exception:
                continue
    items.sort(key=lambda item: item["mtime"], reverse=True)
    return items[:200]


def resolve_ar(root_index: int, rel: str) -> Path:
    if root_index < 0 or root_index >= len(AR_ROOTS):
        raise FileNotFoundError("invalid_ar_root")
    root = AR_ROOTS[root_index]
    path = (root / rel).resolve()
    if root != path and root not in path.parents:
        raise PermissionError("ar_path_escape")
    if path.suffix.lower() != ".usdz" or not path.is_file():
        raise FileNotFoundError("usdz_not_found")
    return path


def deep_doctor() -> dict[str, Any]:
    env = safe_env()
    verified = [
        verify_command_bridge("conversation", CONVERSATION_CMD, CONVERSATION_PROBE_CMD, cwd=LIVE_ROOT, env=env),
        verify_command_bridge("invention_lab", INVENTION_CMD, INVENTION_PROBE_CMD, cwd=LIVE_ROOT, env=env),
        verify_json_source("neural_overview", NEURAL_OVERVIEW, LIVE_ROOT),
        verify_json_source("neural_fibers", NEURAL_FIBERS, LIVE_ROOT),
        verify_json_source("neural_activity", NEURAL_ACTIVITY, LIVE_ROOT),
        verify_ar_roots(AR_ROOTS),
    ]
    bridges = {item.name: item.payload() for item in verified}

    semantic_checks: list[dict[str, Any]] = []
    try:
        semantic_checks = semantic_neural_check(
            read_json_source(NEURAL_OVERVIEW),
            read_json_source(NEURAL_FIBERS),
            read_json_source(NEURAL_ACTIVITY),
        )
    except Exception as exc:
        semantic_checks = [{"name": "semantic_neural_load", "ok": False, "detail": f"{type(exc).__name__}:{exc}", "severity": "error"}]

    manifest = verify_manifest(PACKAGE_MANIFEST, LIVE_ROOT)
    manifest_gate = bool(manifest.get("healthy")) if PACKAGE_MANIFEST else True
    lock_ok = False
    lock_detail = "pid_file_missing"
    try:
        owner = int(PID_FILE.read_text(encoding="utf-8").strip())
        lock_ok = owner == os.getpid() and process_alive(owner)
        lock_detail = f"owner={owner} current={os.getpid()} alive={process_alive(owner)}"
    except Exception as exc:
        lock_detail = f"{type(exc).__name__}:{exc}"

    tls_pair = bool(TLS_CERT) == bool(TLS_KEY)
    tls_files = True
    if TLS_CERT and TLS_KEY:
        tls_files = Path(TLS_CERT).is_file() and Path(TLS_KEY).is_file()
    tls_ok = tls_pair and tls_files
    tls_detail = "disabled_external_https_expected" if not TLS_CERT and not TLS_KEY else ("certificate_pair_resolved" if tls_ok else "certificate_pair_invalid")

    semantic_ok = all(item.get("ok") or item.get("severity") == "warning" for item in semantic_checks)
    bridge_ok = all(item.healthy for item in verified)
    ok = bridge_ok and semantic_ok and manifest_gate and lock_ok and tls_ok
    return {
        "ok": ok,
        "bridges": bridges,
        "semantic": semantic_checks,
        "manifest": manifest,
        "lock": {"healthy": lock_ok, "detail": lock_detail},
        "tls": {"healthy": tls_ok, "detail": tls_detail, "configured": bool(TLS_CERT and TLS_KEY)},
        "paths": {"live_root": str(LIVE_ROOT), "state_dir": str(STATE_DIR), "static": str(STATIC)},
        "runtime": dict(_RUNTIME),
        "pid": os.getpid(),
    }


class Handler(SimpleHTTPRequestHandler):
    server_version = "EIRA2SuperServer/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[eira2-http] " + fmt % args + "\n")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if length < 0 or length > 2_000_000:
            raise ValueError("request_too_large")
        raw = self.rfile.read(length) if length else b"{}"
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("body_must_be_object")
        return obj

    def _fail(self, exc: Exception, status: int = 500) -> None:
        set_runtime(last_error=f"{type(exc).__name__}:{exc}")
        self._json(status, {"ok": False, "error": str(exc), "type": type(exc).__name__})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                matrix = bridge_matrix()
                healthy = all(item["healthy"] for item in matrix.values())
                self._json(200 if healthy else 503, {"ok": healthy, "runtime": dict(_RUNTIME), "bridges": matrix, "live_root": str(LIVE_ROOT), "doctor": "/api/doctor"})
                return
            if path == "/api/doctor":
                report = deep_doctor()
                self._json(200 if report["ok"] else 503, report)
                return
            if path == "/api/runtime":
                self._json(200, {"ok": True, "runtime": dict(_RUNTIME), "bridges": bridge_matrix()})
                return
            if path == "/api/neural/overview":
                self._json(200, {"ok": True, "data": read_json_source(NEURAL_OVERVIEW)})
                return
            if path == "/api/neural/fibers":
                self._json(200, {"ok": True, "data": read_json_source(NEURAL_FIBERS)})
                return
            if path == "/api/neural/activity":
                self._json(200, {"ok": True, "data": read_json_source(NEURAL_ACTIVITY)})
                return
            if path == "/api/ar/list":
                self._json(200, {"ok": True, "items": list_usdz()})
                return
            if path.startswith("/api/ar/file/"):
                parts = path.split("/", 5)
                if len(parts) != 6:
                    raise FileNotFoundError("invalid_ar_path")
                root_index = int(parts[4])
                rel = unquote(parts[5])
                asset = resolve_ar(root_index, rel)
                data = asset.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "model/vnd.usdz+zip")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'inline; filename="{asset.name}"')
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/":
                self.path = "/index.html"
            return super().do_GET()
        except FileNotFoundError as exc:
            self._fail(exc, 404)
        except (ValueError, PermissionError) as exc:
            self._fail(exc, 400)
        except Exception as exc:
            self._fail(exc, 503)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/activate":
                active = bool(body.get("active", True))
                state = set_runtime(active=active, muted=False if not active else bool(_RUNTIME.get("muted", False)), last_error=None)
                self._json(200, {"ok": True, "runtime": state})
                return
            if path == "/api/mute":
                state = set_runtime(muted=bool(body.get("muted", True)), last_error=None)
                self._json(200, {"ok": True, "runtime": state})
                return
            if path == "/api/conversation":
                text = str(body.get("text", "")).strip()
                if not text:
                    raise ValueError("text_required")
                if len(text) > 32000:
                    raise ValueError("text_too_large")
                result = run_command(CONVERSATION_CMD, {"text": text, "source": "eira2_super_server"})
                set_runtime(last_error=None)
                self._json(200, {"ok": True, "result": result})
                return
            if path == "/api/invention/launch":
                result = run_command(INVENTION_CMD, body or {"action": "launch"}, timeout=180)
                set_runtime(last_error=None)
                self._json(200, {"ok": True, "result": result})
                return
            self._json(404, {"ok": False, "error": "route_not_found", "path": path})
        except ValueError as exc:
            self._fail(exc, 400)
        except subprocess.TimeoutExpired as exc:
            self._fail(RuntimeError(f"bridge_timeout:{exc.timeout}"), 504)
        except Exception as exc:
            self._fail(exc, 503)


def serve() -> None:
    acquire_pid_lock()
    os.chdir(STATIC)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    scheme = "http"
    if TLS_CERT or TLS_KEY:
        if not (TLS_CERT and TLS_KEY):
            release_pid_lock()
            raise RuntimeError("eira2_tls_certificate_pair_incomplete")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile=TLS_CERT, keyfile=TLS_KEY)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    set_runtime(started_at=now(), last_error=None)
    print(f"EIRA2_SUPER_SERVER_READY {scheme}://{HOST}:{PORT}", flush=True)

    def stop(*_: Any) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        httpd.server_close()
        release_pid_lock()


if __name__ == "__main__":
    serve()
