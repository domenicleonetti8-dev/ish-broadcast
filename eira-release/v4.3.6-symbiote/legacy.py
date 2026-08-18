from __future__ import annotations
import importlib
from pathlib import Path
from typing import Iterable, List
from extensions.unified_brain_ai.provider_base import Provider
from extensions.unified_brain_ai.schema import CapabilityRequest, CapabilityResult
from .common import ROLE, _STANDARD_CALLS, _text
from .contracts import _extension_contract, _safe_entrypoint

class LegacyLiveProvider(Provider):
    local = True
    cost_tier = 0
    priority = 180
    heavy = False
    quality_score = 0.72
    privacy_score = 1.0
    latency_tier = 0

    def __init__(self, extension_name: str, entrypoint: str, capabilities: Iterable[str], live_root: Path, discovery: str):
        super().__init__({})
        self.extension_name = extension_name
        self.entrypoint = entrypoint
        self.live_root = live_root
        self.discovery = discovery
        self.name = f"live:{extension_name}"
        self.capabilities = {str(c).strip() for c in capabilities if str(c).strip()}

    @classmethod
    def discover(cls, live_root: Path) -> List["LegacyLiveProvider"]:
        ext_root = live_root / "extensions"
        if not ext_root.is_dir() or ext_root.is_symlink():
            return []
        out = []
        for ext in sorted(ext_root.iterdir(), key=lambda p: p.name):
            if not ext.is_dir() or ext.is_symlink() or ext.name in {"unified_brain_ai", ROLE}:
                continue
            data = _extension_contract(ext)
            caps = [str(x).strip() for x in (data.get("capabilities") or []) if str(x).strip()] if isinstance(data, dict) else []
            ep = str(data.get("entrypoint") or "").strip() if isinstance(data, dict) else ""
            prefix = f"extensions.{ext.name}"
            if caps and _safe_entrypoint(ep) and (ep == prefix or ep.startswith(prefix + ".")):
                out.append(cls(ext.name, ep, caps, live_root, str(data.get("discovery") or "")))
        return out

    def configured(self) -> bool:
        return self.live_root.is_dir() and bool(self.capabilities) and _safe_entrypoint(self.entrypoint)

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        if request.capability not in self.capabilities:
            return CapabilityResult(self.name, request.capability, False, error="legacy_capability_not_advertised")
        if request.options.get("legacy_mutation") and not request.mutation_authorized:
            return CapabilityResult(self.name, request.capability, False, error="legacy_mutation_requires_current_turn_authorization")
        try:
            module = importlib.import_module(self.entrypoint)
        except Exception as exc:
            return CapabilityResult(self.name, request.capability, False, error=f"legacy_import_failed:{type(exc).__name__}:{str(exc)[:160]}")
        fn = next((getattr(module, name, None) for name in _STANDARD_CALLS if callable(getattr(module, name, None))), None)
        if fn is None:
            return CapabilityResult(self.name, request.capability, False, error="legacy_standard_callable_not_found")
        payload = {"capability": request.capability, "prompt": request.prompt, "messages": list(request.messages), "context": dict(request.context), "options": dict(request.options), "mutation_authorized": bool(request.mutation_authorized), "venom_symbiotic": True}
        try:
            value = fn(payload)
        except TypeError:
            try:
                value = fn(request.prompt)
            except Exception as exc:
                return CapabilityResult(self.name, request.capability, False, error=f"legacy_execute_failed:{type(exc).__name__}:{str(exc)[:180]}")
        except Exception as exc:
            return CapabilityResult(self.name, request.capability, False, error=f"legacy_execute_failed:{type(exc).__name__}:{str(exc)[:180]}")
        if isinstance(value, CapabilityResult):
            return value
        ok = bool(value.get("ok", True)) if isinstance(value, dict) else True
        text = _text(value).strip() if value is not None else ""
        return CapabilityResult(self.name, request.capability, ok, text=text, data=value, evidence=[{"type": "legacy_live_extension", "extension": self.extension_name, "entrypoint": self.entrypoint, "discovery": self.discovery, "current_turn_routed": True}], metadata={"symbiotic_legacy_merge": True}, error=None if ok else str(value.get("error") or "legacy_provider_failed") if isinstance(value, dict) else None)
