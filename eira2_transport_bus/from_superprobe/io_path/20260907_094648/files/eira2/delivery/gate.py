from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..contracts import Health, RuntimeContext, ServiceSpec, ServiceState


Sink = Callable[[str], Awaitable[Any]]
TurnSink = Callable[[str, str, bool], Awaitable[Any]]


class DeliveryGate:
    spec = ServiceSpec(
        "delivery.gate",
        required=True,
        dependencies=("conversation.spine", "delivery.voice"),
    )

    def __init__(
        self,
        sinks: list[Sink],
        *,
        shadow_mode: bool = True,
        turn_sinks: list[TurnSink] | None = None,
    ) -> None:
        self._sinks = tuple(sinks)
        self._turn_sinks = tuple(turn_sinks or ())
        self._shadow = shadow_mode
        self._state = ServiceState.DECLARED
        self._delivered_ids: set[str] = set()
        self._streaming_ids: set[str] = set()
        self._streamed_text: dict[str, str] = {}
        self._stream_consolidation_pending: set[str] = set()
        self._conversation = None

    async def start(self, context: RuntimeContext) -> None:
        conversation = context.get_service("conversation.spine")
        setter = getattr(conversation, "set_stream_emitter", None)
        if not callable(setter):
            raise RuntimeError("conversation_stream_emitter_contract_missing")

        async def emitter(correlation_id: str, text: str, final: bool) -> None:
            await self.deliver_chunk(correlation_id, text, final=final)

        setter(emitter)
        self._conversation = conversation
        self._state = ServiceState.READY

    async def stop(self) -> None:
        setter = getattr(self._conversation, "set_stream_emitter", None)
        if callable(setter):
            setter(None)
        self._conversation = None
        self._state = ServiceState.STOPPED
        self._delivered_ids.clear()
        self._streaming_ids.clear()
        self._streamed_text.clear()
        self._stream_consolidation_pending.clear()

    async def health(self) -> Health:
        mode = "shadow" if self._shadow else "active"
        return Health(self._state, f"{mode};streams={len(self._streaming_ids)}")

    async def _emit(self, correlation_id: str, text: str, *, final: bool) -> None:
        # Generic sinks remain deliberately text-only. Correlation-aware sinks are
        # reserved for canonical delivery machinery such as voice-language routing;
        # neither path is allowed to rewrite accepted words.
        for sink in self._sinks:
            await sink(text)
        for sink in self._turn_sinks:
            await sink(correlation_id, text, final)

    async def deliver(self, correlation_id: str, text: str) -> bool:
        if self._state != ServiceState.READY:
            raise RuntimeError("delivery_gate_not_ready")
        rendered = str(text or "")
        if correlation_id in self._stream_consolidation_pending:
            # The streaming path has already spoken this one logical response. The
            # normal runtime final delivery is consumed exactly once as a consistency
            # receipt, never spoken again.
            if rendered != self._streamed_text.get(correlation_id, ""):
                raise RuntimeError("streamed_final_response_mismatch")
            self._stream_consolidation_pending.discard(correlation_id)
            return False
        if correlation_id in self._delivered_ids or correlation_id in self._streaming_ids:
            raise RuntimeError("duplicate_outward_delivery")
        self._delivered_ids.add(correlation_id)
        if self._shadow:
            return False
        await self._emit(correlation_id, rendered, final=True)
        return True

    async def deliver_chunk(self, correlation_id: str, text: str, *, final: bool = False) -> bool:
        """Deliver a verified delta within exactly one logical outward response."""
        if self._state != ServiceState.READY:
            raise RuntimeError("delivery_gate_not_ready")
        if correlation_id in self._delivered_ids and correlation_id not in self._streaming_ids:
            raise RuntimeError("duplicate_outward_delivery")
        chunk = str(text or "")
        if not chunk and not final:
            return False
        self._streaming_ids.add(correlation_id)
        if chunk:
            self._streamed_text[correlation_id] = self._streamed_text.get(correlation_id, "") + chunk
            if not self._shadow:
                await self._emit(correlation_id, chunk, final=final)
        elif final and not self._shadow:
            # A final empty delta is still meaningful to a correlation-aware sink:
            # it lets the voice owner release per-turn language/model state.
            for sink in self._turn_sinks:
                await sink(correlation_id, "", True)
        if final:
            self._streaming_ids.discard(correlation_id)
            self._delivered_ids.add(correlation_id)
            self._stream_consolidation_pending.add(correlation_id)
        return not self._shadow

    def streamed_text(self, correlation_id: str) -> str:
        return self._streamed_text.get(correlation_id, "")
