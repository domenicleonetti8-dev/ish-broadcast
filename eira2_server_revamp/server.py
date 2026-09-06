#!/usr/bin/env python3
"""Isolated EIRA 2.0 revamp server.

This server is deliberately fail-closed: a bridge is never reported healthy unless its
contract can actually be resolved. It can be qualified in isolation before migration
into Easystore LIVE.
"""
from __future__ import annotations

import json
import mimetypes
import os
import shlex
import signal
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

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
INVENTION_CMD = os.environ.get("EIRA2_INVENTION_CMD", "").strip()
NEURAL_OVERVIEW = os.environ.get("EIRA2_NEURAL_OVERVIEW", "").strip()
NEURAL_FIBERS = os.environ.get("EIRA2_NEURAL_FIBERS", "").strip()
NEURAL_ACTIVITY = os.environ.get("EIRA2_NEURAL_ACTIVITY", "").strip()
AR_ROOTS = [Path(p).resolve() for p in os.environ.get("EIRA2_AR_ROOTS", "").split(os.pathsep) if p.strip()]


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
    tmp.write_text(str(os.getpid()))
    os.replace(tmp, PID_FILE)


def release_pid_lock() -> None:
    try:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
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
        return Bridge(name, True, False, f"invalid_command:{type(exc).__name__}")
    if not argv:
        return Bridge(name, False, False, "empty_command")
    exe = argv[0]
    if os.path.sep in exe:
        ok = Path(exe).exists()
    else:
        from shutil import which
        ok = which(exe) is not None
    return Bridge(name, True, ok, "resolved" if ok else f"executable_not_found:{exe}")


def _json_bridge(name: str, raw: str) -> Bridge:
    if not raw:
        return Bridge(name, False, False, "json_source_not_configured")
    p = Path(raw)
    if not p.is_absolute():
        p = LIVE_ROOT / p
    if not p.exists():
        return Bridge(name, True, False, f"missing:{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, (dict, list)):
            raise ValueError("top_level_not_object_or_array")
    except Exception as exc:
        return Bridge(name, True, False, f"invalid_json:{type(exc).__name__}:{exc}")
    return Bridge(name, True, True, str(p))


def bridge_matrix() -> dict[str, dict[str, Any]]:
    bridges = [
        _cmd_bridge("conversation", CONVERSATION_CMD),
        _cmd_bridge("invention_lab", INVENTION_CMD),
        _json_bridge("neural_overview", NEURAL_OVERVIEW),
        _json_bridge("neural_fibers", NEURAL_FIBERS),
        _json_bridge("neural_activity", NEURAL_ACTIVITY),
    ]
    ar_ok = any(p.exists() and p.is_dir() for p in AR_ROOTS)
    bridges.append(Bridge("apple_ar", bool(AR_ROOTS), ar_ok, "roots_resolved" if ar_ok else "ar_roots_unavailable"))
    return {b.name: asdict(b) for b in bridges}


def read_json_source(raw: str) -> Any:
    if not raw:
        raise RuntimeError("source_not_configured")
    p = Path(raw)
    if not p.is_absolute():
        p = LIVE_ROOT / p
    return json.loads(p.read_text(encoding="utf-8"))


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
    text = cp.stdout.strip()
    if not text:
        raise RuntimeError("bridge_returned_empty_output")
    try:
        out = json.loads(text)
    except Exception:
        out = {"text": text}
    if isinstance(out, dict):
        return out
    return {"result": out}


def list_usdz() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, root in enumerate(AR_ROOTS):
        if not root.is_dir():
            continue
        for p in root.rglob("*.usdz"):
            try:
                rel = p.relative_to(root).as_posix()
                st = p.stat()
                items.append({"root": idx, "path": rel, "name": p.name, "size": st.st_size, "mtime": st.st_mtime})
            except Exception:
                continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:200]


def resolve_ar(root_index: int, rel: str) -> Path:
    if root_index < 0 or root_index >= len(AR_ROOTS):
        raise FileNotFoundError("invalid_ar_root")
    root = AR_ROOTS[root_index]
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise PermissionError("ar_path_escape")
    if p.suffix.lower() != ".usdz" or not p.is_file():
        raise FileNotFoundError("usdz_not_found")
    return p


class Handler(SimpleHTTPRequestHandler):
    server_version = "EIRA2Revamp/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[eira2-http] " + fmt % args + "\n")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n > 2_000_000:
            raise ValueError("request_too_large")
        raw = self.rfile.read(n) if n else b"{}"
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("body_must_be_object")
        return obj

    def _fail(self, exc: Exception, status: int = 500) -> None:
        set_runtime(last_error=f"{type(exc).__name__}:{exc}")
        self._json(status, {"ok": False, "error": str(exc), "type": type(exc).__name__})

    def do_GET(self) -> None:
        u = urlparse(self.path)
        path = u.path
        try:
            if path == "/api/health":
                matrix = bridge_matrix()
                healthy = all(v["healthy"] for v in matrix.values())
                self._json(200 if healthy else 503, {"ok": healthy, "runtime": dict(_RUNTIME), "bridges": matrix, "live_root": str(LIVE_ROOT)})
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
                p = resolve_ar(root_index, rel)
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "model/vnd.usdz+zip")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'inline; filename="{p.name}"')
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
                state = set_runtime(active=bool(body.get("active", True)), last_error=None)
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
                result = run_command(CONVERSATION_CMD, {"text": text, "source": "eira2_revamp_server"})
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
    cert = os.environ.get("EIRA2_TLS_CERT", "").strip()
    key = os.environ.get("EIRA2_TLS_KEY", "").strip()
    scheme = "http"
    if cert and key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert, keyfile=key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    set_runtime(started_at=now(), last_error=None)
    print(f"EIRA2_REVAMP_READY {scheme}://{HOST}:{PORT}", flush=True)

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
