from __future__ import annotations
import threading, uuid
from pathlib import Path
from typing import Any
from extensions.unified_brain_ai.bootstrap import build_unified_executive
from extensions.unified_brain_ai.schema import TurnInput
from .common import VERSION, ROLE, _CONTROL, _config, _config_path, _live_root, _invoke, _text
from .history import ConversationSource, SymbioteJournal
from .fabric import FullSymbioticFabric
from .legacy import LegacyLiveProvider
from .bridge import SymbioteHostBridge

_LOCK=threading.RLock()
_EXECUTIVE=None
_BRIDGE=None
_HOST_ID=None
_FABRIC=None
_FABRIC_KEY=None
_JOURNAL=None
_JOURNAL_KEY=None
_LEGACY=None
_LEGACY_KEY=None

def _fabric_for(live_root: Path) -> FullSymbioticFabric:
    global _FABRIC, _FABRIC_KEY
    cfg = _config()
    sym = cfg.get("symbiote") or {}
    state = Path(str(sym.get("state_path") or (live_root / "data" / "eira_neural_web.sqlite3"))).expanduser().resolve()
    key = (str(live_root), str(state))
    with _LOCK:
        if _FABRIC is None or _FABRIC_KEY != key:
            _FABRIC = FullSymbioticFabric(live_root, state, int(sym.get("refresh_ttl_seconds", 300)))
            _FABRIC_KEY = key
        return _FABRIC


def _journal_for(live_root: Path) -> SymbioteJournal:
    global _JOURNAL, _JOURNAL_KEY
    key = str(live_root)
    with _LOCK:
        if _JOURNAL is None or _JOURNAL_KEY != key:
            _JOURNAL = SymbioteJournal(live_root)
            _JOURNAL_KEY = key
        return _JOURNAL


def _legacy_for(live_root: Path) -> ConversationSource:
    global _LEGACY, _LEGACY_KEY
    key = str(live_root)
    with _LOCK:
        if _LEGACY is None or _LEGACY_KEY != key:
            _LEGACY = ConversationSource(live_root / "data" / "local_brain" / "conversation.json", "legacy_live_history", 200)
            _LEGACY_KEY = key
        return _LEGACY


def _executive_for(host_chat, router_globals=None):
    global _EXECUTIVE, _BRIDGE, _HOST_ID
    live_root = _live_root()
    hid = id(host_chat)
    with _LOCK:
        if _EXECUTIVE is None or _HOST_ID != hid:
            fabric = _fabric_for(live_root)
            _BRIDGE = SymbioteHostBridge(host_chat, router_globals, fabric, live_root)
            executive = build_unified_executive(str(_config_path()), host=_BRIDGE)
            existing = {getattr(p, "name", "") for p in executive.gateway.registry.all()}
            for provider in LegacyLiveProvider.discover(live_root):
                if provider.name not in existing:
                    executive.gateway.registry.register(provider)
                    existing.add(provider.name)
            _EXECUTIVE = executive
            _HOST_ID = hid
        else:
            if _BRIDGE is not None and router_globals is not None:
                _BRIDGE.router_globals = router_globals
        return _EXECUTIVE


def claim_turn(current_turn: Any, *, host_should_route=None) -> bool:
    text = str(current_turn or "").strip()
    if not text or _CONTROL.match(text):
        return False
    return True


def route_turn(current_turn: Any, *, host_chat, router_globals=None) -> str:
    text = str(current_turn or "").strip()
    if not text:
        return _text(_invoke(host_chat, str(current_turn or ""))).strip()
    live_root = _live_root()
    journal = _journal_for(live_root)
    try:
        messages = journal.relevant_for(text, 12)
        legacy = _legacy_for(live_root).relevant_for(text, 12)
        seen = {(m.get("role"), m.get("content")) for m in messages}
        messages.extend(m for m in legacy if (m.get("role"), m.get("content")) not in seen)
        response = _executive_for(host_chat, router_globals).handle(TurnInput(
            turn_id=f"symbiote_{uuid.uuid4().hex[:16]}", text=text, messages=messages[-18:],
            options={"symbiote_full_merge": True, "legacy_context_fused": bool(legacy)},
        ))
        if response.error or not str(response.text or "").strip():
            raise RuntimeError(response.error or "symbiote_empty_brain_response")
        out = str(response.text).strip()
        journal.append_exchange(text, out, fallback=False)
        return out
    except Exception as exc:
        try:
            bridge = _BRIDGE if (_BRIDGE is not None and _HOST_ID == id(host_chat)) else SymbioteHostBridge(host_chat, router_globals, _fabric_for(live_root), live_root)
            out = bridge._render(
                text,
                "unified_brain_safe_fallback",
                messages if "messages" in locals() else [],
                [],
                "The full symbiote remains authoritative for this ordinary turn. The specialist path failed; answer the current user directly without reviving unrelated legacy context. "
                + f"Internal failure class: {type(exc).__name__}.",
            ).strip()
        except Exception:
            out = _text(_invoke(host_chat, text)).strip()
        if out:
            journal.append_exchange(text, out, fallback=True)
        return out


def self_test(host_chat=None, router_globals=None, *, refresh_fabric: bool = False) -> Dict[str, Any]:
    live_root = _live_root()
    fabric = _fabric_for(live_root)
    claims = {
        "conversation": claim_turn("hello there"),
        "knowledge": claim_turn("explain photosynthesis"),
        "engineering": claim_turn("build a steel bracket"),
        "continuity": claim_turn("what did we decide about memory?"),
        "control_exit": claim_turn("exit"),
    }
    providers = LegacyLiveProvider.discover(live_root)
    result = {
        "ok": all(claims[k] for k in ("conversation", "knowledge", "engineering", "continuity")) and not claims["control_exit"],
        "version": VERSION,
        "mode": "complete_symbiotic_venom",
        "claims": claims,
        "legacy_providers_discovered": len(providers),
        "legacy_capabilities_discovered": sum(len(p.capabilities) for p in providers),
        "main_rewrite": False,
        "outward_identity_owner": "host_eira",
        "history_authority": "current_turn_filtered_unified_context",
        "neural_store": str(fabric.store.path),
    }
    if refresh_fabric:
        result["fabric"] = fabric.refresh(True)
    else:
        result["fabric"] = fabric.status()
    return result


def status() -> Dict[str, Any]:
    return self_test(refresh_fabric=False)


def register() -> Dict[str, Any]:
    return {
        "name": ROLE,
        "version": VERSION,
        "entrypoint": "extensions.eira_full_symbiote_ai.plugin",
        "capabilities": ["symbiote_status", "symbiote_refresh", "symbiote_connected_context"],
        "mode": "complete_symbiotic_venom",
        "identity_owner": "host_eira",
    }
