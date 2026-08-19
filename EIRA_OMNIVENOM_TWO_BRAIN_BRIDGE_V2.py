from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from threading import RLock

from .runtime import Omnivenom

_LOCK = RLock()
_MESH = None
_LAST_REFRESH = 0.0
_REFRESH_SECONDS = 60.0

_SYSTEM_WORDS = (
    "eira", " live", "file", "folder", "directory", "memory", "system",
    "extension", "artifact", "node", "omnivenom", "venom", "recent",
    "added", "changed", "project", "router", "brain",
)


def _live_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _mesh() -> Omnivenom:
    global _MESH
    with _LOCK:
        if _MESH is None:
            _MESH = Omnivenom(_live_root())
        return _MESH


def _needs_evidence(text: str) -> bool:
    low = " " + str(text or "").lower()
    return any(word in low for word in _SYSTEM_WORDS)


def _recent_files(limit: int = 18):
    root = _live_root()
    rows = []
    skip = {
        ".git", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".venv", "venv", "node_modules",
    }
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in skip]
        cur = Path(current)
        for name in files:
            p = cur / name
            try:
                st = p.stat()
                rel = p.relative_to(root).as_posix()
            except OSError:
                continue
            rows.append(
                (st.st_mtime_ns, {
                    "path": rel,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
            )
    rows.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in rows[:max(1, min(int(limit), 50))]]


def _evidence(text: str):
    global _LAST_REFRESH
    if not _needs_evidence(text):
        return None

    mesh = _mesh()
    now = time.monotonic()

    with _LOCK:
        status = mesh.status()
        if (
            int(status.get("nodes", 0) or 0) == 0
            or now - _LAST_REFRESH >= _REFRESH_SECONDS
        ):
            mesh.refresh()
            _LAST_REFRESH = now

    return {
        "omnivenom": mesh.context(str(text), depth=1, limit=80),
        "recent_files": _recent_files(),
        "live_root": str(_live_root()),
        "evidence_mode": "read_only",
    }


def chat(prompt, timeout=600, persist_history=True, **kwargs):
    """
    Two-brain Eira bridge.

    OmniVenom supplies evidence. Unified Brain owns the turn.
    The existing local brain remains the tandem/voice tissue used by
    Unified Brain, and is also the fail-safe if Unified Brain cannot answer.
    """
    text = str(prompt or "").strip()
    if not text:
        return {
            "status": "unresolved",
            "model": None,
            "response": "",
            "errors": ["empty_prompt"],
        }

    evidence = None
    evidence_error = None
    try:
        evidence = _evidence(text)
    except Exception as exc:
        evidence_error = f"{type(exc).__name__}:{str(exc)[:160]}"

    try:
        from extensions.unified_brain_ai import plugin as unified

        options = {
            "persist_history": bool(persist_history),
            "dominant_reasoning_owner": "unified_brain_ai",
            "legacy_brain_role": "tandem_provider",
            "one_output_plane": True,
        }
        if evidence is not None:
            options["venom_mesh_context"] = evidence
            options["omnivenom_context"] = evidence

        result = unified.ask({
            "turn_id": "main_" + uuid.uuid4().hex[:12],
            "message": text,
            "options": options,
        })

        response = (
            str(result.get("response") or "").strip()
            if isinstance(result, dict)
            else ""
        )
        if isinstance(result, dict) and result.get("ok") and response:
            errors = []
            if evidence_error:
                errors.append({
                    "node": "omnivenom",
                    "error": evidence_error,
                })
            return {
                "status": "answered",
                "model": "unified_brain_ai",
                "response": response,
                "errors": errors,
                "source": result.get("source"),
                "capability": result.get("capability"),
                "metadata": result.get("metadata") or {},
            }

        unified_error = (
            (result or {}).get("error")
            if isinstance(result, dict)
            else "unified_result_invalid"
        )
    except Exception as exc:
        unified_error = f"{type(exc).__name__}:{str(exc)[:160]}"

    # Continuity fail-safe: preserve the existing local/conversation brain.
    try:
        from extensions.local_brain.router import chat as local_chat

        legacy = local_chat(
            text,
            timeout=timeout,
            persist_history=persist_history,
        )
        if isinstance(legacy, dict):
            legacy.setdefault("errors", [])
            legacy["errors"].append({
                "node": "unified_brain_ai",
                "error": unified_error,
            })
            if evidence_error:
                legacy["errors"].append({
                    "node": "omnivenom",
                    "error": evidence_error,
                })
            return legacy
    except Exception as exc:
        local_error = f"{type(exc).__name__}:{str(exc)[:160]}"
        return {
            "status": "unresolved",
            "model": None,
            "response": "I could not complete that conversation turn.",
            "errors": [
                {"node": "unified_brain_ai", "error": unified_error},
                {"node": "local_brain", "error": local_error},
            ],
        }

    return {
        "status": "unresolved",
        "model": None,
        "response": "I could not complete that conversation turn.",
        "errors": [{
            "node": "unified_brain_ai",
            "error": unified_error,
        }],
    }


def status():
    return {
        "ok": True,
        "brain_count": 2,
        "dominant": "unified_brain_ai",
        "tandem": "local_brain",
        "omnivenom_role": "connective_evidence_fabric",
        "outward_response_planes": 1,
        "voice_owner": "main.py:_speak",
    }
