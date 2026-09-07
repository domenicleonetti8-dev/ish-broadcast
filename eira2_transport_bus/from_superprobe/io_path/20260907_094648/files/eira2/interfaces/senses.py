from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..capabilities.executor import CapabilityBinding
from ..contracts import Event, Health, RuntimeContext, ServiceSpec, ServiceState
from .native import NativeInputEvidenceService


@dataclass(frozen=True, slots=True)
class SensoryObservation:
    modality: str
    source: str
    summary: str
    confidence: float | None
    observed_at: float
    invoked: bool = False
    attention_candidate: bool = False
    evidence_sha256: str | None = None


class SensoryFusionService:
    """Canonical local audio/vision observation and fusion authority.

    Sensor backends may observe concurrently, but this service only records bounded
    evidence packets. It cannot generate an answer, mutate accepted conversation
    state, or speak. Raw microphone audio and camera frames are temporary inputs and
    are discarded by this service after local analysis; cognition receives summaries
    and provenance rather than raw media.
    """

    spec = ServiceSpec(
        "interfaces.senses",
        required=True,
        dependencies=("kernel.events", "interfaces.native"),
    )

    def __init__(self) -> None:
        self._context: RuntimeContext | None = None
        self._native: NativeInputEvidenceService | None = None
        self._state = ServiceState.DECLARED
        self._observations: deque[SensoryObservation] = deque(maxlen=256)
        self._ambient_task: asyncio.Task[None] | None = None
        self._ambient_muted = False
        self._last_error: str | None = None

    async def start(self, context: RuntimeContext) -> None:
        native = context.get_service("interfaces.native")
        if not isinstance(native, NativeInputEvidenceService):
            raise RuntimeError("native_input_authority_missing")
        self._context = context
        self._native = native
        self._state = ServiceState.READY
        if self._env_enabled("EIRA2_AMBIENT_AUDIO_ENABLED"):
            self._ambient_task = asyncio.create_task(self._ambient_loop(), name="eira2-ambient-audio")

    async def stop(self) -> None:
        task = self._ambient_task
        self._ambient_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._native = None
        self._context = None
        self._state = ServiceState.STOPPED

    async def health(self) -> Health:
        usb_audio, usb_camera = await asyncio.gather(
            asyncio.to_thread(self.usb_audio_devices),
            asyncio.to_thread(self.usb_camera_devices),
        )
        detail = {
            "observations": len(self._observations),
            "ambient_enabled": self._env_enabled("EIRA2_AMBIENT_AUDIO_ENABLED"),
            "ambient_muted": self._ambient_muted,
            "usb_audio_present": bool(usb_audio),
            "usb_camera_present": bool(usb_camera),
            "last_error": self._last_error,
        }
        return Health(self._state, json.dumps(detail, sort_keys=True))

    @staticmethod
    def _env_enabled(name: str) -> bool:
        return str(os.getenv(name, "0")).strip().casefold() in {"1", "true", "yes", "on"}

    @staticmethod
    def _json_command(name: str) -> tuple[str, ...]:
        raw = str(os.getenv(name) or "").strip()
        if not raw:
            return ()
        value = json.loads(raw)
        if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
            raise ValueError(name + "_must_be_json_string_array")
        return tuple(value)

    @staticmethod
    def usb_camera_devices() -> tuple[str, ...]:
        return tuple(str(path) for path in sorted(Path("/dev").glob("video*")) if path.exists())

    @staticmethod
    def usb_audio_devices() -> tuple[str, ...]:
        executable = shutil.which("arecord")
        if not executable:
            return ()
        try:
            result = subprocess.run(
                [executable, "-l"], check=False, capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ()
        devices: list[str] = []
        for line in result.stdout.splitlines():
            clean = line.strip()
            if clean.casefold().startswith("card "):
                devices.append(clean[:300])
        return tuple(devices)

    async def observe(
        self,
        *,
        modality: str,
        source: str,
        summary: str,
        confidence: float | None,
        invoked: bool = False,
        attention_candidate: bool = False,
        evidence_sha256: str | None = None,
    ) -> SensoryObservation:
        if self._state != ServiceState.READY or self._context is None:
            raise RuntimeError("sensory_fusion_not_ready")
        bounded_confidence = None if confidence is None else max(0.0, min(1.0, float(confidence)))
        packet = SensoryObservation(
            modality=str(modality or "unknown")[:40],
            source=str(source or "unknown")[:160],
            summary=" ".join(str(summary or "").split())[:1200],
            confidence=bounded_confidence,
            observed_at=time.time(),
            invoked=bool(invoked),
            attention_candidate=bool(attention_candidate),
            evidence_sha256=str(evidence_sha256) if evidence_sha256 else None,
        )
        if not packet.summary:
            raise ValueError("sensory_summary_required")
        self._observations.append(packet)
        await self._context.publish(Event("sensory.observation.recorded", {
            "modality": packet.modality,
            "source": packet.source,
            "confidence": packet.confidence,
            "invoked": packet.invoked,
            "attention_candidate": packet.attention_candidate,
            "evidence_sha256": packet.evidence_sha256,
            "raw_payload_retained": False,
            "outward_answer": False,
        }))
        return packet

    async def observe_ambient_label(self, label: str, confidence: float, *, source: str = "local_microphone") -> SensoryObservation:
        if self._native is None:
            raise RuntimeError("native_input_authority_missing")
        evidence = self._native.ambient_event(label, confidence, source=source)
        return await self.observe(
            modality="audio",
            source=source,
            summary=str(evidence["label"]),
            confidence=float(evidence["confidence"]),
            invoked=False,
            attention_candidate=bool(evidence["attention_candidate"]),
        )

    def recent(self, *, window_seconds: float = 20.0, limit: int = 16) -> tuple[SensoryObservation, ...]:
        cutoff = time.time() - max(0.0, float(window_seconds))
        rows = [row for row in self._observations if row.observed_at >= cutoff]
        return tuple(rows[-max(1, min(64, int(limit))):])

    def cognition_context(self, *, window_seconds: float = 20.0, limit: int = 12) -> str:
        rows = self.recent(window_seconds=window_seconds, limit=limit)
        if not rows:
            return ""
        lines = [
            "<eira_sensory_context>",
            "These are local, time-bounded sensory observations. Treat confidence and provenance as evidence, preserve conflicts, and do not claim raw media was retained.",
        ]
        for row in rows:
            confidence = "unknown" if row.confidence is None else f"{row.confidence:.3f}"
            lines.append(
                f"- modality={row.modality}; source={row.source}; confidence={confidence}; invoked={str(row.invoked).lower()}; attention={str(row.attention_candidate).lower()}; observation={row.summary}"
            )
        lines.append("</eira_sensory_context>")
        return "\n".join(lines)

    @staticmethod
    def _vision_result(stdout: str) -> tuple[str, float | None]:
        raw = str(stdout or "").strip()
        if not raw:
            raise RuntimeError("local_vision_empty")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw, None
        if not isinstance(payload, dict):
            return raw, None
        summary = str(payload.get("summary") or payload.get("description") or payload.get("text") or "").strip()
        if not summary:
            summary = raw
        confidence_raw = payload.get("confidence")
        if isinstance(confidence_raw, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        else:
            confidence = None
        return summary, confidence

    async def analyze_camera_once(self, device: str | None = None) -> SensoryObservation:
        devices = self.usb_camera_devices()
        selected = str(device or os.getenv("EIRA2_CAMERA_DEVICE") or (devices[0] if devices else "")).strip()
        if not selected or not Path(selected).exists():
            raise RuntimeError("usb_camera_not_present")
        vision_command = self._json_command("EIRA2_LOCAL_VISION_COMMAND")
        if not vision_command:
            raise RuntimeError("local_vision_backend_unconfigured")
        ffmpeg = shutil.which("ffmpeg")
        capture_command = self._json_command("EIRA2_CAMERA_CAPTURE_COMMAND")
        if not capture_command and not ffmpeg:
            raise RuntimeError("camera_capture_backend_missing")

        with tempfile.TemporaryDirectory(prefix="eira2-camera-") as temporary:
            frame = Path(temporary) / "frame.jpg"
            argv = (
                [part.replace("{device}", selected).replace("{output}", str(frame)) for part in capture_command]
                if capture_command
                else [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-i", selected, "-frames:v", "1", "-y", str(frame)]
            )
            capture = await asyncio.to_thread(subprocess.run, argv, check=False, capture_output=True, text=True)
            if capture.returncode != 0 or not frame.is_file():
                raise RuntimeError("camera_capture_failed:" + (capture.stderr or "")[-400:])
            raw = frame.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            vision_argv = [part.replace("{image}", str(frame)) for part in vision_command]
            if not any(str(frame) in part for part in vision_argv):
                vision_argv.append(str(frame))
            vision = await asyncio.to_thread(
                subprocess.run,
                vision_argv,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "EIRA2_VISION_LOCAL_ONLY": "1"},
            )
            if vision.returncode != 0:
                raise RuntimeError("local_vision_failed:" + (vision.stderr or "")[-400:])
            summary, confidence = self._vision_result(vision.stdout)
        return await self.observe(
            modality="vision",
            source=selected,
            summary=summary,
            confidence=confidence,
            invoked=True,
            attention_candidate=False,
            evidence_sha256=digest,
        )

    async def _ambient_loop(self) -> None:
        interval = max(0.25, float(os.getenv("EIRA2_AMBIENT_INTERVAL_SECONDS", "2.0")))
        analyzer = self._json_command("EIRA2_AMBIENT_AUDIO_COMMAND")
        while True:
            try:
                await asyncio.sleep(interval)
                if self._ambient_muted or not analyzer:
                    continue
                result = await asyncio.to_thread(
                    subprocess.run,
                    list(analyzer),
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "EIRA2_AMBIENT_LOCAL_ONLY": "1"},
                )
                if result.returncode != 0:
                    self._last_error = "ambient_analyzer_failed:" + (result.stderr or "")[-300:]
                    continue
                payload = json.loads(result.stdout or "{}")
                label = str(payload.get("label") or "").strip()
                if not label:
                    continue
                await self.observe_ambient_label(
                    label,
                    float(payload.get("confidence", 0.0)),
                    source=str(payload.get("source") or "local_microphone"),
                )
                self._last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._last_error = f"{type(error).__name__}:{error}"[:400]

    async def set_ambient_muted(self, muted: bool) -> dict[str, Any]:
        if self._state != ServiceState.READY or self._context is None:
            raise RuntimeError("sensory_fusion_not_ready")
        self._ambient_muted = bool(muted)
        await self._context.publish(Event("sensory.ambient.mute_changed", {
            "muted": self._ambient_muted,
            "ambient_enabled": self._env_enabled("EIRA2_AMBIENT_AUDIO_ENABLED"),
            "outward_answer": False,
        }))
        return {
            "ok": True,
            "ambient_muted": self._ambient_muted,
            "ambient_enabled": self._env_enabled("EIRA2_AMBIENT_AUDIO_ENABLED"),
        }

    def snapshot(self) -> dict[str, Any]:
        rows = self.recent(window_seconds=60.0, limit=32)
        return {
            "owner": self.spec.name,
            "usb_camera_devices": list(self.usb_camera_devices()),
            "usb_audio_devices": list(self.usb_audio_devices()),
            "camera_device_override": str(os.getenv("EIRA2_CAMERA_DEVICE") or "") or None,
            "local_vision_configured": bool(self._json_command("EIRA2_LOCAL_VISION_COMMAND")),
            "ambient_enabled": self._env_enabled("EIRA2_AMBIENT_AUDIO_ENABLED"),
            "ambient_analyzer_configured": bool(self._json_command("EIRA2_AMBIENT_AUDIO_COMMAND")),
            "ambient_muted": self._ambient_muted,
            "recent_observations": [asdict(row) for row in rows],
            "raw_audio_retained": False,
            "raw_camera_frames_retained": False,
            "can_generate_answer": False,
            "accepted_state_authority": "conversation.commit",
        }

    def capability_bindings(self) -> tuple[CapabilityBinding, ...]:
        async def status(_: str) -> dict[str, Any]:
            return await asyncio.to_thread(self.snapshot)

        async def camera(_: str) -> dict[str, Any]:
            row = await self.analyze_camera_once()
            return asdict(row)

        async def ambient_control(text: str) -> dict[str, Any]:
            clean = " ".join(str(text or "").casefold().split())
            unmute = "unmute" in clean or "resume ambient" in clean
            return await self.set_ambient_muted(not unmute)

        return (
            CapabilityBinding(
                id="senses.status",
                implementation_node=self.spec.name,
                aliases=("senses status", "camera status", "microphone status", "ambient status"),
                tags=("runtime_introspection", "senses", "vision", "audio_evidence"),
                handler=status,
                description="Inspect local USB microphone/camera and sensory-fusion readiness without retaining raw media.",
                read_only=True,
                auto_safe=False,
                shadow_safe=True,
            ),
            CapabilityBinding(
                id="vision.observe",
                implementation_node=self.spec.name,
                aliases=("look", "look through camera", "camera observe", "what do you see"),
                tags=("vision", "camera", "external_evidence"),
                handler=camera,
                description="Capture one local USB-camera frame, analyze it locally, discard raw media, and return a typed observation.",
                read_only=True,
                auto_safe=False,
                shadow_safe=False,
            ),
            CapabilityBinding(
                id="senses.ambient.control",
                implementation_node=self.spec.name,
                aliases=("mute", "unmute", "mute ambient", "unmute ambient", "mute listening", "unmute listening", "resume ambient"),
                tags=("ambient_control", "senses"),
                handler=ambient_control,
                description="Explicitly mute or unmute silent ambient observation without bypassing the capability executor.",
                read_only=False,
                auto_safe=False,
                shadow_safe=True,
            ),
        )
