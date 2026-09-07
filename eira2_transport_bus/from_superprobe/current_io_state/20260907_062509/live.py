from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .adapters.ollama import OllamaCandidateAdapter
from .evidence.deterministic import verify_response
from .interfaces.ingress import InputKind
from .neural.server import NeuralHandler
from .operations.model_takeover import verify_private_model_containment
from .operations.package_identity import verify_package_manifest
from .runtime import Eira2Runtime, default_config


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _verified_live_identity(root: Path, manifest: Path) -> tuple[str, str]:
    payload = verify_package_manifest(root, manifest)
    target = str(payload.get("source_commit_sha") or "").strip().casefold()
    tree = str(payload.get("package_tree_sha256") or "").strip().casefold()
    if not target or not tree:
        raise RuntimeError("live_eira2_package_identity_invalid")
    return target, tree


def live_config(root: Path, manifest: Path, *, host: str = "0.0.0.0", port: int = 8782) -> Any:
    root = root.expanduser().resolve()
    manifest = manifest.expanduser().resolve()
    target, _tree = _verified_live_identity(root, manifest)
    return replace(
        default_config(root),
        shadow_mode=False,
        terminal_enabled=True,
        voice_enabled=True,
        repair_enabled=True,
        self_evolution_enabled=True,
        neural_ui_enabled=True,
        neural_ui_host=host,
        neural_ui_port=port,
        package_manifest_path=manifest,
        expected_eira2_sha=target,
    )


def _install_conversation_post_bridge(runtime: Eira2Runtime, loop: asyncio.AbstractEventLoop, turn_lock: asyncio.Lock) -> None:
    async def process_input(text: str, kind: InputKind):
        async with turn_lock:
            return await runtime.process(text, kind=kind)

    def send_json(handler: NeuralHandler, status: int, payload: Mapping[str, object]) -> None:
        raw = (json.dumps(dict(payload), sort_keys=True) + "\n").encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        handler.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS, POST")
        handler.end_headers()
        handler.wfile.write(raw)

    def read_body(handler: NeuralHandler) -> tuple[str, bool]:
        try:
            length = int(handler.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 1_000_000:
            return "", False
        raw = handler.rfile.read(length)
        content_type = str(handler.headers.get("Content-Type") or "").casefold()
        if "application/json" in content_type:
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                return "", False
            text = str(payload.get("text") or payload.get("message") or payload.get("transcript") or payload.get("utterance") or "").strip()
            source = str(payload.get("source") or payload.get("kind") or "").casefold()
            voice = bool(payload.get("voice") is True or "voice" in source or payload.get("transcript") or payload.get("utterance"))
            return text, voice
        return raw.decode("utf-8", errors="replace").strip(), False

    def do_POST(handler: NeuralHandler) -> None:
        path = handler.path.split("?", 1)[0]
        if path in {"/api/input", "/api/chat", "/api/conversation", "/api/message", "/api/voice"}:
            try:
                text, voice_hint = read_body(handler)
                if not text:
                    send_json(handler, 400, {"ok": False, "error": "empty_input"})
                    return
                kind = InputKind.IPHONE_VOICE if (path == "/api/voice" or voice_hint) else InputKind.IPHONE_TEXT
                future = asyncio.run_coroutine_threadsafe(process_input(text, kind), loop)
                result = future.result(timeout=300)
                send_json(handler, 200, {
                    "ok": True,
                    "verified": bool(result.verified),
                    "response": result.response,
                    "text": result.response,
                    "correlation_id": result.correlation_id,
                    "input_kind": kind.value,
                })
            except Exception as exc:
                send_json(handler, 500, {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:1200]})
            return

        if path in {"/api/mute", "/api/listening/mute", "/api/ambient/mute"}:
            try:
                text, _ = read_body(handler)
                clean = text.casefold()
                muted = not ("unmute" in clean or "false" in clean or "resume" in clean)
                future = asyncio.run_coroutine_threadsafe(runtime.senses.set_ambient_muted(muted), loop)
                result = future.result(timeout=30)
                send_json(handler, 200, result)
            except Exception as exc:
                send_json(handler, 500, {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:1200]})
            return

        send_json(handler, 404, {"ok": False, "error": "post_route_not_found"})

    NeuralHandler.do_POST = do_POST


async def run_live(root: Path, manifest: Path, *, model: str = "", host: str = "0.0.0.0", port: int = 8782) -> dict[str, object]:
    root = root.expanduser().resolve()
    manifest = manifest.expanduser().resolve()
    target, package_tree = _verified_live_identity(root, manifest)
    config = live_config(root, manifest, host=host, port=port)
    if config.expected_eira2_sha != target:
        raise RuntimeError("live_config_identity_mismatch")

    model_containment = verify_private_model_containment(runtime_root=root)
    socket_path = str(model_containment.get("unix_socket") or "").strip()
    if not socket_path:
        raise RuntimeError("live_private_model_unix_socket_missing")
    selected_model = model or os.getenv("EIRA_MODEL") or "qwen2.5:3b"
    allowed_models = {str(value) for value in model_containment.get("required_models") or ()}
    if selected_model not in allowed_models:
        raise RuntimeError("live_model_not_in_attested_private_set:" + selected_model)

    adapter = OllamaCandidateAdapter(model=selected_model, unix_socket=socket_path)
    runtime = Eira2Runtime(config, generate=adapter.generate, verify=verify_response)
    loop = asyncio.get_running_loop()
    turn_lock = asyncio.Lock()
    _install_conversation_post_bridge(runtime, loop, turn_lock)

    await runtime.start()
    health = await runtime.health.snapshot()
    if health.get("required_failures"):
        await runtime.stop()
        raise RuntimeError("live_required_services_not_healthy")

    stop_event = asyncio.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    async def terminal_turn(text: str) -> None:
        clean = text.strip()
        if not clean:
            return
        async with turn_lock:
            try:
                result = await runtime.process(clean, kind=InputKind.TERMINAL)
                print("Eira: " + result.response, flush=True)
            except Exception as exc:
                print(f"EIRA2_INPUT_ERROR={type(exc).__name__}:{exc}", flush=True)

    terminal_reader_installed = False
    if config.terminal_enabled and sys.stdin is not None and sys.stdin.isatty():
        try:
            fd = sys.stdin.fileno()
            def on_terminal_input() -> None:
                line = sys.stdin.readline()
                if line == "":
                    try:
                        loop.remove_reader(fd)
                    except Exception:
                        pass
                    return
                loop.create_task(terminal_turn(line))
            loop.add_reader(fd, on_terminal_input)
            terminal_reader_installed = True
        except (AttributeError, OSError, RuntimeError, ValueError):
            terminal_reader_installed = False

    receipt_path = root / "var" / "eira2-live-runtime.json"
    receipt: dict[str, object] = {
        "schema": "eira2_live_runtime_v6",
        "ok": True,
        "active": True,
        "pid": os.getpid(),
        "started_unix_ns": time.time_ns(),
        "runtime_authority": "eira2",
        "shadow_mode": False,
        "git_metadata_required_at_runtime": False,
        "target_eira2_sha": config.expected_eira2_sha,
        "package_tree_sha256": package_tree,
        "package_identity_verified_at_boot": True,
        "required_services_healthy": True,
        "model_role": "private_candidate_only",
        "model_name": selected_model,
        "model_transport": "unix_domain_socket",
        "model_unix_socket": socket_path,
        "model_store_under_eira2": model_containment.get("model_store_under_eira2") is True,
        "model_outbound_network_allowed": False,
        "model_private_network_verified_at_boot": True,
        "model_direct_delivery_authority": False,
        "model_direct_tool_authority": False,
        "model_direct_identity_authority": False,
        "model_direct_memory_acceptance": False,
        "neural_ui_host": host,
        "neural_ui_port": int(runtime.neural_ui.port if runtime.neural_ui is not None else port),
        "voice_enabled": True,
        "repair_enabled": True,
        "self_evolution_enabled": True,
        "conversation_http_post_enabled": True,
        "conversation_http_routes": ["/api/input", "/api/chat", "/api/conversation", "/api/message", "/api/voice"],
        "terminal_input_enabled": terminal_reader_installed,
        "clean_shutdown": False,
    }
    _atomic_json(receipt_path, receipt)
    print(json.dumps(receipt, sort_keys=True), flush=True)

    try:
        await stop_event.wait()
    finally:
        if terminal_reader_installed:
            try:
                loop.remove_reader(sys.stdin.fileno())
            except Exception:
                pass
        await runtime.stop()
        stopped = dict(receipt)
        stopped.update({"active": False, "stopped_unix_ns": time.time_ns(), "clean_shutdown": True})
        _atomic_json(receipt_path, stopped)
    return receipt
