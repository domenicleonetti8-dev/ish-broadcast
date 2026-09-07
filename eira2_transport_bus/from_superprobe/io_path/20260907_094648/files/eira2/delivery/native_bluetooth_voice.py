from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

from .voice_prosody import cadence_chunks, synthesis_controls


AUDIO_UUID_MARKERS = (
    "audio sink",
    "advanced audio",
    "0000110b",
    "0000110d",
)
AUDIO_ICON_MARKERS = ("audio-card", "audio-headset", "headset", "headphones")
MAC_RE = re.compile(r"(?i)\b([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b")


class NativeBluetoothVoiceRuntime:
    """EIRA2-owned synchronous Bluetooth/Piper spoken-output backend.

    This backend deliberately has no global boot hook, reconnect daemon, queue, or
    import path into the retired EIRA1 tree. Lifecycle authority remains with the
    EIRA2 Supervisor through ``delivery.voice``. Voice models and optional Piper
    vendor packages live under EIRA2 ``var/voice`` unless explicitly overridden.
    """

    def __init__(self, runtime_root: Path, *, voice_model: Path | None = None) -> None:
        self.runtime_root = runtime_root.expanduser().resolve()
        self.voice_root = self.runtime_root / "var" / "voice"
        vendor_override = str(os.environ.get("EIRA2_PIPER_VENDOR", "")).strip()
        self.vendor = Path(vendor_override).expanduser().resolve() if vendor_override else self.voice_root / "_vendor"
        model_override = str(os.environ.get("EIRA2_VOICE_MODEL", "")).strip()
        self.voice_model = (
            Path(model_override).expanduser().resolve()
            if model_override
            else voice_model.expanduser().resolve() if voice_model is not None else self.voice_root / "voices" / "en_US-hfc_female-medium.onnx"
        )
        self._lock = threading.RLock()
        self._connected: dict[str, str] = {}
        self._active_sinks: list[str] = []
        self._default_sink: str | None = None
        self._last_error: str | None = None
        self._last_acquire = 0.0
        self._last_spoken = 0.0
        self._connect_attempt_at: dict[str, float] = {}
        self._connect_cooldown_seconds = float(os.environ.get("EIRA2_BT_CONNECT_COOLDOWN_SECONDS", "12"))
        self._voice: Any | None = None
        self._loaded_voice_model: Path | None = None
        self._player = self._detect_player()

    @staticmethod
    def _run(args, *, timeout: int | float | None = 20, input_text: str | None = None):
        return subprocess.run(
            list(args), input=input_text, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, check=False,
        )

    @staticmethod
    def _detect_player() -> str | None:
        for command in ("paplay", "pw-play", "aplay"):
            if shutil.which(command):
                return command
        return None

    def set_voice_model(self, model: Path) -> None:
        selected = model.expanduser().resolve()
        if selected == self.voice_model:
            return
        self.voice_model = selected
        self._voice = None
        self._loaded_voice_model = None

    def _bluetoothctl(self, *args: str, timeout: int = 20):
        return self._run(("bluetoothctl", *args), timeout=timeout)

    @staticmethod
    def _parse_devices(text: str) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw in str(text or "").splitlines():
            match = MAC_RE.search(raw)
            if not match:
                continue
            mac = match.group(1).upper()
            if mac in seen:
                continue
            name = raw[match.end():].strip() or mac
            seen.add(mac)
            found.append((mac, name))
        return found

    def _devices(self, *, paired_only: bool = False) -> list[tuple[str, str]]:
        commands: list[tuple[str, ...]] = []
        if paired_only:
            commands.extend((("devices", "Paired"), ("paired-devices",)))
        else:
            commands.append(("devices",))
        for command in commands:
            result = self._bluetoothctl(*command, timeout=12)
            if result.returncode == 0:
                devices = self._parse_devices(result.stdout)
                if devices or not paired_only:
                    return devices
        return []

    def _info(self, mac: str) -> dict[str, Any]:
        result = self._bluetoothctl("info", mac, timeout=10)
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        low = text.lower()
        rssi_match = re.search(r"(?im)^\s*rssi:\s*(-?\d+)", text)
        return {
            "raw": text,
            "paired": "paired: yes" in low,
            "trusted": "trusted: yes" in low,
            "connected": "connected: yes" in low,
            "audio": any(marker in low for marker in AUDIO_UUID_MARKERS) or any(("icon: " + marker) in low for marker in AUDIO_ICON_MARKERS),
            "rssi": int(rssi_match.group(1)) if rssi_match else -999,
        }

    def _scan_once(self, *, seconds: int = 8) -> None:
        if not shutil.which("bluetoothctl"):
            raise RuntimeError("bluetoothctl_not_installed")
        self._bluetoothctl("power", "on", timeout=8)
        self._bluetoothctl("--timeout", str(int(seconds)), "scan", "on", timeout=int(seconds) + 5)

    def _pair_best_audio_if_needed(self) -> None:
        enabled = str(os.environ.get("EIRA2_BT_AUTO_PAIR", "1")).strip().casefold()
        if enabled not in {"1", "true", "yes", "on"}:
            return
        candidates: list[tuple[int, str, str]] = []
        for mac, name in self._devices(paired_only=False):
            info = self._info(mac)
            if info["audio"] and not info["paired"]:
                candidates.append((int(info["rssi"]), mac, name))
        candidates.sort(reverse=True)
        if not candidates:
            return
        _, mac, _ = candidates[0]
        paired = self._bluetoothctl("pair", mac, timeout=35)
        if paired.returncode != 0:
            raise RuntimeError("automatic_bluetooth_pairing_failed:" + mac + ":" + (paired.stderr.strip() or paired.stdout.strip()))
        self._bluetoothctl("trust", mac, timeout=10)

    def _connect_audio_devices(self) -> dict[str, str]:
        eligible: list[tuple[int, str, str, dict[str, Any]]] = []
        for mac, name in self._devices(paired_only=True):
            info = self._info(mac)
            if info["paired"] and info["audio"]:
                eligible.append((int(info["rssi"]), mac, name, info))
        eligible.sort(reverse=True)
        connected: dict[str, str] = {}
        max_outputs = max(1, min(10, int(os.environ.get("EIRA2_BT_MAX_OUTPUTS", "10"))))
        for _, mac, name, info in eligible[:max_outputs]:
            if not info["trusted"]:
                self._bluetoothctl("trust", mac, timeout=10)
            live_info = self._info(mac)
            if live_info["connected"]:
                connected[mac] = name
                continue
            now = time.monotonic()
            last_attempt = self._connect_attempt_at.get(mac, 0.0)
            if now - last_attempt < self._connect_cooldown_seconds:
                continue
            self._connect_attempt_at[mac] = now
            result = self._bluetoothctl("connect", mac, timeout=25)
            if result.returncode != 0:
                continue
            time.sleep(1.2)
            live_info = self._info(mac)
            if live_info["connected"]:
                connected[mac] = name
        return connected

    @classmethod
    def _pactl_sinks(cls) -> list[str]:
        if not shutil.which("pactl"):
            return []
        result = cls._run(("pactl", "list", "short", "sinks"), timeout=10)
        if result.returncode != 0:
            return []
        sinks: list[str] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "bluez" in parts[1].casefold():
                sinks.append(parts[1])
        return sinks

    @classmethod
    def _wpctl_sinks(cls) -> list[tuple[str, str]]:
        if not shutil.which("wpctl"):
            return []
        result = cls._run(("wpctl", "status", "-n"), timeout=10)
        if result.returncode != 0:
            return []
        sinks: list[tuple[str, str]] = []
        in_sinks = False
        for line in result.stdout.splitlines():
            low = line.casefold()
            if "sinks:" in low:
                in_sinks = True
                continue
            if in_sinks and ("sources:" in low or "filters:" in low or "streams:" in low):
                break
            if in_sinks and "bluez" in low:
                match = re.search(r"(\d+)\.\s+(.+?)(?:\s+\[|$)", line)
                if match:
                    sinks.append((match.group(1), match.group(2).strip()))
        return sinks

    def _route_audio(self) -> list[str]:
        sinks = self._pactl_sinks()
        if sinks:
            self._run(("pactl", "set-default-sink", sinks[0]), timeout=8)
            self._default_sink = sinks[0]
            return sinks
        wp_sinks = self._wpctl_sinks()
        if wp_sinks:
            sink_id, sink_name = wp_sinks[0]
            self._run(("wpctl", "set-default", sink_id), timeout=8)
            self._default_sink = sink_name
            return [name for _, name in wp_sinks]
        self._default_sink = None
        return []

    def acquire(self) -> dict[str, Any]:
        with self._lock:
            self._last_acquire = time.time()
            self._last_error = None
            try:
                self._connected = self._connect_audio_devices()
                if not self._connected:
                    self._scan_once(seconds=int(os.environ.get("EIRA2_BT_SCAN_SECONDS", "8")))
                    self._pair_best_audio_if_needed()
                    self._connected = self._connect_audio_devices()
                deadline = time.time() + 8
                sinks: list[str] = []
                while time.time() < deadline:
                    sinks = self._route_audio()
                    if sinks or not self._connected:
                        break
                    time.sleep(1)
                self._active_sinks = sinks
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}:{exc}"
            return self.status()

    def ensure(self) -> dict[str, Any]:
        with self._lock:
            needs_acquire = not self._connected or not self._active_sinks or (time.time() - self._last_acquire) > 20
        if needs_acquire:
            return self.acquire()
        return self.status()

    def _load_voice(self):
        if self._voice is not None and self._loaded_voice_model == self.voice_model:
            return self._voice
        if not self.voice_model.is_file():
            raise RuntimeError("piper_voice_model_missing:" + str(self.voice_model))
        if self.vendor.is_dir() and str(self.vendor) not in sys.path:
            sys.path.insert(0, str(self.vendor))
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError("piper_runtime_missing:install_piper_or_migrate_EIRA2_PIPER_VENDOR") from exc
        self._voice = PiperVoice.load(str(self.voice_model))
        self._loaded_voice_model = self.voice_model
        return self._voice

    def _synthesize(self, text: str, output: Path) -> None:
        spoken = str(text or "").strip()
        if not spoken:
            raise ValueError("empty_speech_chunk")
        voice = self._load_voice()
        try:
            from piper.config import SynthesisConfig
        except ImportError as exc:
            raise RuntimeError("piper_synthesis_config_missing") from exc
        controls = synthesis_controls(spoken)
        config = SynthesisConfig(
            length_scale=float(controls["length_scale"]),
            noise_scale=float(controls["noise_scale"]),
            noise_w_scale=float(controls["noise_w_scale"]),
        )
        with wave.open(str(output), "wb") as wav_file:
            voice.synthesize_wav(spoken, wav_file, syn_config=config)

    def _play(self, wav_path: Path) -> None:
        player = self._player or self._detect_player()
        if not player:
            raise RuntimeError("audio_player_missing:paplay_or_pw-play_or_aplay")
        self._player = player
        if player == "paplay":
            args = ["paplay"]
            if self._default_sink:
                args.append("--device=" + self._default_sink)
            args.append(str(wav_path))
        elif player == "pw-play":
            args = ["pw-play", str(wav_path)]
        else:
            args = ["aplay", "-q", str(wav_path)]
        result = self._run(args, timeout=None)
        if result.returncode != 0:
            raise RuntimeError("audio_playback_failed:" + player + ":" + (result.stderr.strip() or result.stdout.strip()))

    def speak_now(self, text: str) -> None:
        spoken = str(text or "").strip()
        if not spoken:
            return
        state = self.ensure()
        if not state["connected_devices"]:
            raise RuntimeError("no_bluetooth_audio_device_connected")
        if not state["active_sinks"]:
            raise RuntimeError("bluetooth_connected_without_audio_sink")
        fd, tmp_name = tempfile.mkstemp(prefix="eira2_voice_", suffix=".wav")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            for phrase, pause in cadence_chunks(spoken):
                self._synthesize(phrase, tmp)
                self._play(tmp)
                if pause > 0:
                    time.sleep(pause)
            self._last_spoken = time.time()
            self._last_error = None
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}:{exc}"
            raise
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": self._last_error is None,
                "role": "eira2_native_bluetooth_voice",
                "runtime_authority": "delivery.voice",
                "connected_devices": dict(self._connected),
                "active_sinks": list(self._active_sinks),
                "default_sink": self._default_sink,
                "voice_model": str(self.voice_model),
                "voice_model_ready": self.voice_model.is_file(),
                "piper_vendor": str(self.vendor),
                "piper_vendor_ready": self.vendor.is_dir(),
                "player": self._player,
                "last_error": self._last_error,
                "last_acquire": self._last_acquire,
                "last_spoken": self._last_spoken,
                "synthetic_breath_audio": False,
                "phrase_specific_prosody": True,
                "background_runtime_threads": False,
                "eira1_runtime_delegation": False,
            }
