from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import time
from uuid import uuid4

from ..contracts import Health, RuntimeContext, ServiceSpec, ServiceState


class InputKind(str, Enum):
    TERMINAL = "terminal"
    IPHONE_TEXT = "iphone_text"
    IPHONE_VOICE = "iphone_voice"
    LOCAL_VOICE = "local_voice"


@dataclass(frozen=True, slots=True)
class InputEnvelope:
    text: str
    kind: InputKind
    correlation_id: str
    received_at: float

    @classmethod
    def create(cls, text: str, kind: InputKind) -> "InputEnvelope":
        clean = str(text or "").strip()
        if not clean:
            raise ValueError("empty_input")
        if not isinstance(kind, InputKind):
            kind = InputKind(str(kind))
        return cls(clean, kind, str(uuid4()), time())


class IngressService:
    """Canonical normalization boundary for all normal EIRA inputs.

    Ingress owns input normalization and correlation identity only. It never routes,
    reasons, speaks, writes state, or depends on outward delivery.
    """

    spec = ServiceSpec("interfaces.ingress", required=True, dependencies=())

    def __init__(self) -> None:
        self._state = ServiceState.DECLARED

    async def start(self, context: RuntimeContext) -> None:
        self._state = ServiceState.READY

    async def stop(self) -> None:
        self._state = ServiceState.STOPPED

    async def health(self) -> Health:
        return Health(self._state, "canonical_input_normalization")

    def accept(self, text: str, kind: InputKind) -> InputEnvelope:
        if self._state != ServiceState.READY:
            raise RuntimeError("ingress_not_ready")
        return InputEnvelope.create(text, kind)
