from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .adapters.ollama import OllamaCandidateAdapter
from .evidence.deterministic import verify_response
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


def live_config(
    root: Path,
    manifest: Path,
    *,
    host: str = "0.0.0.0",
    port: int = 8782,
) -> Any:
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


async def run_live(
    root: Path,
    manifest: Path,
    *,
    model: str = "",
    host: str = "0.0.0.0",
    port: int = 8782,
) -> dict[str, object]:
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

    await runtime.start()
    health = await runtime.health.snapshot()
    if health.get("required_failures"):
        await runtime.stop()
        raise RuntimeError("live_required_services_not_healthy")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    receipt_path = root / "var" / "eira2-live-runtime.json"
    receipt: dict[str, object] = {
        "schema": "eira2_live_runtime_v5",
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
        "clean_shutdown": False,
    }
    _atomic_json(receipt_path, receipt)
    print(json.dumps(receipt, sort_keys=True), flush=True)

    try:
        await stop_event.wait()
    finally:
        await runtime.stop()
        stopped = dict(receipt)
        stopped.update({"active": False, "stopped_unix_ns": time.time_ns(), "clean_shutdown": True})
        _atomic_json(receipt_path, stopped)
    return receipt
