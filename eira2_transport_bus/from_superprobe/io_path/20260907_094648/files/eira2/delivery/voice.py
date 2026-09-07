from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..contracts import Event, Health, RuntimeContext, ServiceSpec, ServiceState
from .native_bluetooth_voice import NativeBluetoothVoiceRuntime


Speaker = Callable[[str], None]


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _device_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _sink_matches_device(sink: str, *, mac: str, name: str) -> bool:
    raw = str(sink or "").casefold()
    mac_raw = str(mac or "").casefold()
    mac_underscore = mac_raw.replace(":", "_")
    mac_compact = mac_raw.replace(":", "")
    name_token = _device_token(name)
    sink_token = _device_token(raw)
    return bool(
        (mac_raw and mac_raw in raw)
        or (mac_underscore and mac_underscore in raw)
        or (mac_compact and mac_compact in sink_token)
        or (name_token and name_token in sink_token)
    )


def _language_env_suffix(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", str(code or "").upper()).strip("_")


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    identity: str = "Eira"
    presentation: str = "adult_feminine"
    timbre_target: str = "warm_confident_slightly_smoky"
    personality_delivery: str = "playful_spunky_grounded"
    cadence: str = "natural_thought_sized"
    energy: str = "responsive_not_hyper"
    breath_behavior: str = "silent_thought_boundary_breath_groups"
    micro_pause_behavior: str = "adaptive_clause_sentence_and_reaction_pauses"
    nonverbal_behavior: str = "contextual_sparse_never_canned"
    synthetic_breath_samples: bool = False
    voiceprint_cloning: bool = False
    lexical_rewrite_allowed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "presentation": self.presentation,
            "timbre_target": self.timbre_target,
            "personality_delivery": self.personality_delivery,
            "cadence": self.cadence,
            "energy": self.energy,
            "breath_behavior": self.breath_behavior,
            "micro_pause_behavior": self.micro_pause_behavior,
            "nonverbal_behavior": self.nonverbal_behavior,
            "synthetic_breath_samples": self.synthetic_breath_samples,
            "voiceprint_cloning": self.voiceprint_cloning,
            "lexical_rewrite_allowed": self.lexical_rewrite_allowed,
        }


class VoiceOutputService:
    """Canonical EIRA2 spoken-output owner.

    Conversation owns accepted words and identity. This service owns acoustic
    delivery only. It never generates or rewrites lexical content, never boots an
    independent resident voice runtime, and never delegates execution into EIRA1.
    Flash Cube remains the canonical Bluetooth mouth unless the operator explicitly
    enables fallback. Spoken-language routing is correlation-aware and fails silent
    for unqualified languages while preserving accepted text delivery.
    """

    spec = ServiceSpec(
        "delivery.voice",
        required=True,
        dependencies=("kernel.events",),
        start_timeout_seconds=15.0,
    )

    def __init__(
        self,
        runtime_root: Path,
        *,
        enabled: bool,
        shadow_mode: bool,
        speaker: Speaker | None = None,
        voice_model: Path | None = None,
        preferred_device_name: str | None = None,
    ) -> None:
        self.runtime_root = runtime_root.expanduser().resolve()
        self.enabled = bool(enabled)
        self.shadow_mode = bool(shadow_mode)
        configured = str(os.environ.get("EIRA2_VOICE_MODEL", "")).strip()
        self.voice_model = (
            Path(configured).expanduser().resolve()
            if configured
            else (voice_model.expanduser().resolve() if voice_model else None)
        )
        configured_device = str(os.environ.get("EIRA2_BT_PREFERRED_DEVICE_NAME", "")).strip()
        requested_device = str(preferred_device_name or configured_device or "Flash Cube").strip()
        self.preferred_device_name = requested_device or "Flash Cube"
        self.allow_speaker_fallback = _truthy_env("EIRA2_BT_ALLOW_SPEAKER_FALLBACK", False)
        self.allow_language_voice_fallback = _truthy_env("EIRA2_VOICE_ALLOW_LANGUAGE_FALLBACK", False)
        multilingual = str(os.environ.get("EIRA2_MULTILINGUAL_VOICE_MODEL", "")).strip()
        self.multilingual_voice_model = Path(multilingual).expanduser().resolve() if multilingual else None
        configured_languages = str(os.environ.get("EIRA2_MULTILINGUAL_VOICE_LANGUAGES", "")).strip()
        self.multilingual_voice_languages = frozenset(
            token.strip().casefold()
            for token in configured_languages.split(",")
            if token.strip()
        )
        self._speaker = speaker
        self._speaker_injected = speaker is not None
        self._native_runtime: NativeBluetoothVoiceRuntime | Any | None = None
        self._native_default_voice_model: Path | None = None
        self._preferred_device_connected: bool | None = None
        self._preferred_sink: str | None = None
        self._connected_device_names: tuple[str, ...] = ()
        self._context: RuntimeContext | None = None
        self._state = ServiceState.DECLARED
        self._spoken_count = 0
        self._last_error = ""
        self._turn_languages: dict[str, str] = {}
        self._last_language_code: str | None = None
        self._last_language_model_source: str | None = None
        self._unqualified_language_voice_count = 0
        self.profile = VoiceProfile()

    async def start(self, context: RuntimeContext) -> None:
        if self.shadow_mode and self.enabled:
            raise RuntimeError("voice_output_forbidden_in_shadow_mode")
        self._context = context
        events = context.get_service("kernel.events")
        subscribe = getattr(events, "subscribe", None)
        if not callable(subscribe):
            raise RuntimeError("voice_language_event_subscription_missing")
        subscribe("conversation.language_and_figures.analyzed", self._observe_language_profile)
        self._state = ServiceState.READY

    async def stop(self) -> None:
        self._turn_languages.clear()
        self._context = None
        self._native_runtime = None
        self._native_default_voice_model = None
        if not self._speaker_injected:
            self._speaker = None
        self._state = ServiceState.STOPPED

    async def _observe_language_profile(self, event: Event) -> None:
        code = str(event.payload.get("requested_language_code") or "").strip().casefold()
        if code:
            self._turn_languages[event.correlation_id] = code
        else:
            self._turn_languages.pop(event.correlation_id, None)

    async def health(self) -> Health:
        if self._state == ServiceState.READY and self._last_error:
            return Health(ServiceState.DEGRADED, "voice_error:" + self._last_error[:180])
        if (
            self._state == ServiceState.READY
            and self.enabled
            and not self.shadow_mode
            and not self._speaker_injected
            and self._preferred_device_connected is False
            and not self.allow_speaker_fallback
        ):
            return Health(ServiceState.DEGRADED, "preferred_bluetooth_speaker_missing:" + self.preferred_device_name)
        mode = "shadow_silent" if self.shadow_mode else ("armed" if self.enabled else "disabled")
        return Health(self._state, mode)

    def status(self) -> dict[str, object]:
        explicit_codes = sorted(
            key.removeprefix("EIRA2_VOICE_MODEL_").casefold()
            for key in os.environ
            if key.startswith("EIRA2_VOICE_MODEL_")
            and str(os.environ.get(key, "")).strip()
            and key != "EIRA2_VOICE_MODEL_"
        )
        return {
            "schema": "eira2_voice_output_v4",
            "enabled": self.enabled,
            "shadow_mode": self.shadow_mode,
            "spoken_count": self._spoken_count,
            "last_error": self._last_error or None,
            "runtime_root": str(self.runtime_root),
            "native_backend": True,
            "eira1_runtime_delegation": False,
            "voice_model_override": str(self.voice_model) if self.voice_model else None,
            "native_default_voice_model": str(self._native_default_voice_model) if self._native_default_voice_model else None,
            "preferred_bluetooth_device_name": self.preferred_device_name,
            "preferred_bluetooth_device_connected": self._preferred_device_connected,
            "preferred_bluetooth_sink": self._preferred_sink,
            "connected_bluetooth_device_names": list(self._connected_device_names),
            "speaker_fallback_allowed": self.allow_speaker_fallback,
            "language_voice_fallback_allowed": self.allow_language_voice_fallback,
            "custom_speaker_injected": self._speaker_injected,
            "explicit_language_voice_codes": explicit_codes,
            "multilingual_voice_model_configured": self.multilingual_voice_model is not None,
            "multilingual_voice_languages": sorted(self.multilingual_voice_languages),
            "last_language_code": self._last_language_code,
            "last_language_model_source": self._last_language_model_source,
            "unqualified_language_voice_count": self._unqualified_language_voice_count,
            "profile": self.profile.as_dict(),
        }

    def _preferred_device_present(self, state: dict[str, Any]) -> bool:
        connected = state.get("connected_devices") or {}
        if isinstance(connected, dict):
            pairs = tuple(
                (str(mac).strip(), str(name).strip())
                for mac, name in connected.items()
                if str(name).strip()
            )
        else:
            pairs = ()
        self._connected_device_names = tuple(name for _, name in pairs)
        target = self.preferred_device_name.casefold()
        preferred_pairs = tuple((mac, name) for mac, name in pairs if name.casefold() == target)
        present = bool(preferred_pairs)
        self._preferred_device_connected = present
        self._preferred_sink = None
        if not present:
            return False

        active_sinks = tuple(
            str(row).strip() for row in (state.get("active_sinks") or ()) if str(row).strip()
        )
        matching = tuple(
            sink
            for sink in active_sinks
            if any(_sink_matches_device(sink, mac=mac, name=name) for mac, name in preferred_pairs)
        )
        if matching:
            self._preferred_sink = matching[0]
        elif len(pairs) == 1 and len(active_sinks) == 1:
            self._preferred_sink = active_sinks[0]
        return True

    def _pin_preferred_sink(self, runtime: Any, state: dict[str, Any]) -> None:
        if self.allow_speaker_fallback:
            return
        if not self._preferred_device_present(state):
            raise RuntimeError("preferred_bluetooth_speaker_not_connected:" + self.preferred_device_name)
        if self._preferred_sink is None:
            raise RuntimeError("preferred_bluetooth_speaker_sink_not_identified:" + self.preferred_device_name)
        if hasattr(runtime, "_default_sink"):
            runtime._default_sink = self._preferred_sink
        if hasattr(runtime, "_active_sinks"):
            runtime._active_sinks = [self._preferred_sink]

    def _native_speaker(self) -> Speaker:
        runtime = NativeBluetoothVoiceRuntime(self.runtime_root, voice_model=self.voice_model)
        self._native_runtime = runtime
        self._native_default_voice_model = Path(runtime.voice_model).expanduser().resolve()

        def speak_with_named_device_guard(text: str) -> None:
            state = dict(runtime.ensure() or {})
            preferred_present = self._preferred_device_present(state)
            if not preferred_present and not self.allow_speaker_fallback:
                raise RuntimeError(
                    "preferred_bluetooth_speaker_not_connected:" + self.preferred_device_name
                )
            if preferred_present:
                self._pin_preferred_sink(runtime, state)
            runtime.speak_now(text)
            try:
                self._preferred_device_present(dict(runtime.status() or {}))
            except Exception:
                pass

        return speak_with_named_device_guard

    def _resolve_speaker(self) -> Speaker:
        if self._speaker is None:
            self._speaker = self._native_speaker()
        return self._speaker

    def _qualified_model_for_language(self, code: str) -> tuple[Path | None, str | None]:
        normalized = str(code or "").strip().casefold()
        if not normalized or normalized == "en":
            if self.voice_model is not None:
                return self.voice_model, "default_english_model"
            return None, "backend_default_english"

        suffix = _language_env_suffix(normalized)
        configured = str(os.environ.get(f"EIRA2_VOICE_MODEL_{suffix}", "")).strip()
        if configured:
            path = Path(configured).expanduser().resolve()
            if path.is_file():
                return path, f"language_model:{normalized}"
            return None, f"configured_language_model_missing:{normalized}"

        if self.multilingual_voice_model is not None:
            covered = "*" in self.multilingual_voice_languages or normalized in self.multilingual_voice_languages
            if covered and self.multilingual_voice_model.is_file():
                return self.multilingual_voice_model, "qualified_multilingual_model"

        if self.allow_language_voice_fallback:
            return self.voice_model, "operator_enabled_language_fallback"
        return None, None

    def _select_native_model(self, selected_model: Path | None, model_source: str | None) -> None:
        runtime = self._native_runtime
        if runtime is None:
            return
        target = selected_model
        if target is None and model_source in {"backend_default_english", "operator_enabled_language_fallback"}:
            target = self._native_default_voice_model
        if target is None:
            return
        setter = getattr(runtime, "set_voice_model", None)
        if callable(setter):
            setter(target)
        else:
            runtime.voice_model = target

    async def _publish_language_unqualified(self, correlation_id: str, code: str) -> None:
        self._unqualified_language_voice_count += 1
        self._last_language_code = code
        self._last_language_model_source = None
        self._last_error = "spoken_language_voice_unqualified:" + code
        if self._context is not None:
            await self._context.publish(Event(
                "delivery.voice.language_unqualified",
                {
                    "language_code": code,
                    "preferred_device_name": self.preferred_device_name,
                    "text_delivery_preserved": True,
                    "spoken_fallback_used": False,
                },
                correlation_id,
            ))

    async def _speak_accepted(
        self,
        text: str,
        *,
        correlation_id: str | None = None,
        language_code: str | None = None,
        selected_model: Path | None = None,
        model_source: str | None = None,
    ) -> bool:
        if self._state != ServiceState.READY:
            raise RuntimeError("voice_output_not_ready")
        spoken = str(text or "").strip()
        if not spoken:
            return False
        if self.shadow_mode or not self.enabled:
            return False
        try:
            speaker = self._resolve_speaker()
            self._select_native_model(selected_model, model_source)
            await asyncio.to_thread(speaker, spoken)
            self._spoken_count += 1
            self._last_error = ""
            self._last_language_code = language_code or "en"
            self._last_language_model_source = model_source or "default"
        except Exception as error:
            self._last_error = f"{type(error).__name__}:{error}"
            if self._context is not None:
                await self._context.publish(Event(
                    "delivery.voice.failed",
                    {
                        "characters": len(spoken),
                        "error_type": type(error).__name__,
                        "preferred_device_name": self.preferred_device_name,
                        "language_code": language_code,
                    },
                    correlation_id or "",
                ))
            raise
        if self._context is not None:
            await self._context.publish(Event(
                "delivery.voice.spoken",
                {
                    "characters": len(spoken),
                    "spoken_count": self._spoken_count,
                    "presentation": self.profile.presentation,
                    "timbre_target": self.profile.timbre_target,
                    "breath_behavior": self.profile.breath_behavior,
                    "nonverbal_behavior": self.profile.nonverbal_behavior,
                    "preferred_device_name": self.preferred_device_name,
                    "preferred_device_connected": self._preferred_device_connected,
                    "preferred_sink": self._preferred_sink,
                    "language_code": language_code or "en",
                    "language_model_source": model_source or "default",
                    "native_backend": not self._speaker_injected,
                },
                correlation_id or "",
            ))
        return True

    async def sink(self, text: str) -> bool:
        """Speak accepted default-language text; retained for explicit direct use/tests."""
        model, source = self._qualified_model_for_language("en")
        return await self._speak_accepted(
            text,
            language_code="en",
            selected_model=model,
            model_source=source,
        )

    async def sink_for_turn(self, correlation_id: str, text: str, final: bool) -> bool:
        """Speak accepted text through the qualified voice route for this transaction."""
        code = self._turn_languages.get(correlation_id, "en")
        try:
            if not str(text or "").strip():
                return False
            if self._speaker_injected:
                return await self._speak_accepted(
                    text,
                    correlation_id=correlation_id,
                    language_code=code,
                    model_source="explicit_injected_speaker",
                )
            model, source = self._qualified_model_for_language(code)
            if code != "en" and model is None and source != "operator_enabled_language_fallback":
                await self._publish_language_unqualified(correlation_id, code)
                return False
            return await self._speak_accepted(
                text,
                correlation_id=correlation_id,
                language_code=code,
                selected_model=model,
                model_source=source,
            )
        finally:
            if final:
                self._turn_languages.pop(correlation_id, None)
