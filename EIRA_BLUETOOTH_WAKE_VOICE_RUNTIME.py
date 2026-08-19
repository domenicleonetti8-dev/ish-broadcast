from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Optional

ROLE = "eira_bluetooth_voice_ai"
VERSION = "1.0.1"

AUDIO_UUID_MARKERS = (
    "audio sink",
    "advanced audio",
    "0000110b",
    "0000110d",
)
AUDIO_ICON_MARKERS = ("audio-card", "audio-headset", "headset", "headphones")
MAC_RE = re.compile(r"(?i)\b([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b")


def _live_root() -> Path:
    configured = os.environ.get("EIRA_LIVE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


class BluetoothVoiceRuntime:
    def __init__(self) -> None:
        self.live = _live_root()
        self.root = Path(__file__).resolve().parent
        self.vendor = self.root / "_vendor"
        self.voice_model = self.root / "voices" / "en_US-hfc_female-medium.onnx"
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._speech_thread: Optional[threading.Thread] = None
        self._speech_queue: queue.Queue[str] = queue.Queue(maxsize=12)
        self._connected: dict[str, str] = {}
        self._active_sinks: list[str] = []
        self._default_sink: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_acquire = 0.0
        self._last_spoken = 0.0
        self._voice = None
        self._player = self._detect_player()

    @staticmethod
    def _run(args, timeout=20, input_text=None):
        return subprocess.run(
            list(args),
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )

    @staticmethod
    def _detect_player() -> Optional[str]:
        for command in ("paplay", "pw-play", "aplay"):
            if shutil.which(command):
                return command
        return None

    def _bluetoothctl(self, *args, timeout=20):
        return self._run(("bluetoothctl", *args), timeout=timeout)

    @staticmethod
    def _parse_devices(text: str) -> list[tuple[str, str]]:
        found = []
        seen = set()
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

    def _devices(self, paired_only=False) -> list[tuple[str, str]]:
        commands = []
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

    def _info(self, mac: str) -> dict:
        result = self._bluetoothctl("info", mac, timeout=10)
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        low = text.lower()
        rssi_match = re.search(r"(?im)^\s*rssi:\s*(-?\d+)", text)
        return {
            "raw": text,
            "paired": "paired: yes" in low,
            "trusted": "trusted: yes" in low,
            "connected": "connected: yes" in low,
            "audio": (
                any(marker in low for marker in AUDIO_UUID_MARKERS)
                or any(("icon: " + marker) in low for marker in AUDIO_ICON_MARKERS)
            ),
            "rssi": int(rssi_match.group(1)) if rssi_match else -999,
        }

    def _scan_once(self, seconds=8) -> None:
        if not shutil.which("bluetoothctl"):
            raise RuntimeError("bluetoothctl is not installed")
        self._bluetoothctl("power", "on", timeout=8)
        self._bluetoothctl(
            "--timeout",
            str(int(seconds)),
            "scan",
            "on",
            timeout=int(seconds) + 5,
        )

    def _pair_best_audio_if_needed(self) -> None:
        paired = self._devices(paired_only=True)
        if any(self._info(mac).get("audio") for mac, _ in paired):
            return
        if os.environ.get("EIRA_BT_AUTO_PAIR", "1").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return

        candidates = []
        for mac, name in self._devices(paired_only=False):
            info = self._info(mac)
            if info["audio"] and not info["paired"]:
                candidates.append((info["rssi"], mac, name))
        candidates.sort(reverse=True)
        if not candidates:
            return

        _, mac, _ = candidates[0]
        paired_result = self._bluetoothctl("pair", mac, timeout=35)
        if paired_result.returncode != 0:
            raise RuntimeError(
                "automatic Bluetooth pairing failed for "
                + mac
                + ": "
                + (paired_result.stderr.strip() or paired_result.stdout.strip())
            )
        self._bluetoothctl("trust", mac, timeout=10)

    def _connect_audio_devices(self) -> dict[str, str]:
        devices = self._devices(paired_only=True)
        eligible = []
        for mac, name in devices:
            info = self._info(mac)
            if info["paired"] and info["audio"]:
                eligible.append((info["rssi"], mac, name, info))

        eligible.sort(reverse=True)
        connected: dict[str, str] = {}
        max_outputs = max(
            1,
            min(10, int(os.environ.get("EIRA_BT_MAX_OUTPUTS", "10"))),
        )
        for _, mac, name, info in eligible[:max_outputs]:
            if not info["trusted"]:
                self._bluetoothctl("trust", mac, timeout=10)
            if not info["connected"]:
                result = self._bluetoothctl("connect", mac, timeout=25)
                if result.returncode != 0:
                    continue
                time.sleep(1.2)
                info = self._info(mac)
            if info["connected"]:
                connected[mac] = name
        return connected

    @staticmethod
    def _pactl_sinks() -> list[str]:
        if not shutil.which("pactl"):
            return []
        result = BluetoothVoiceRuntime._run(
            ("pactl", "list", "short", "sinks"), timeout=10
        )
        if result.returncode != 0:
            return []
        sinks = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "bluez" in parts[1].lower():
                sinks.append(parts[1])
        return sinks

    @staticmethod
    def _wpctl_sinks() -> list[tuple[str, str]]:
        if not shutil.which("wpctl"):
            return []
        result = BluetoothVoiceRuntime._run(("wpctl", "status", "-n"), timeout=10)
        if result.returncode != 0:
            return []
        sinks = []
        in_sinks = False
        for line in result.stdout.splitlines():
            low = line.lower()
            if "sinks:" in low:
                in_sinks = True
                continue
            if in_sinks and (
                "sources:" in low or "filters:" in low or "streams:" in low
            ):
                break
            if in_sinks and "bluez" in low:
                match = re.search(r"(\d+)\.\s+(.+?)(?:\s+\[|$)", line)
                if match:
                    sinks.append((match.group(1), match.group(2).strip()))
        return sinks

    def _route_audio(self) -> list[str]:
        sinks = self._pactl_sinks()
        if sinks:
            target = sinks[0]
            if len(sinks) > 1:
                modules = self._run(
                    ("pactl", "list", "short", "modules"), timeout=10
                )
                if modules.returncode == 0:
                    for line in modules.stdout.splitlines():
                        if (
                            "module-combine-sink" in line
                            and "sink_name=eira_broadcast" in line
                        ):
                            module_id = line.split()[0]
                            self._run(
                                ("pactl", "unload-module", module_id), timeout=8
                            )
                combined = self._run(
                    (
                        "pactl",
                        "load-module",
                        "module-combine-sink",
                        "sink_name=eira_broadcast",
                        "sink_properties=device.description=Eira_Broadcast",
                        "slaves=" + ",".join(sinks),
                    ),
                    timeout=15,
                )
                if combined.returncode == 0:
                    target = "eira_broadcast"
            self._run(("pactl", "set-default-sink", target), timeout=8)
            self._default_sink = target
            return sinks

        wp_sinks = self._wpctl_sinks()
        if wp_sinks:
            sink_id, sink_name = wp_sinks[0]
            self._run(("wpctl", "set-default", sink_id), timeout=8)
            self._default_sink = sink_name
            return [name for _, name in wp_sinks]

        self._default_sink = None
        return []

    def acquire(self) -> dict:
        with self._lock:
            self._last_acquire = time.time()
            self._last_error = None
            try:
                # Fast path: hold/reconnect known audio first. Do not scan while
                # Eira already owns a usable Bluetooth output.
                self._connected = self._connect_audio_devices()

                # Discovery is only needed when no known paired audio device
                # can be connected. Then Eira scans, pairs the best candidate,
                # trusts it, and immediately attempts the connection again.
                if not self._connected:
                    self._scan_once(
                        seconds=int(os.environ.get("EIRA_BT_SCAN_SECONDS", "8"))
                    )
                    self._pair_best_audio_if_needed()
                    self._connected = self._connect_audio_devices()

                deadline = time.time() + 8
                sinks = []
                while time.time() < deadline:
                    sinks = self._route_audio()
                    if sinks or not self._connected:
                        break
                    time.sleep(1)
                self._active_sinks = sinks
            except Exception as exc:
                self._last_error = str(exc)
            return self.status()

    def ensure(self) -> dict:
        with self._lock:
            needs_acquire = (
                not self._connected
                or not self._active_sinks
                or (time.time() - self._last_acquire) > 20
            )
        if needs_acquire:
            return self.acquire()
        return self.status()

    def _load_voice(self):
        if self._voice is not None:
            return self._voice
        if not self.voice_model.is_file():
            raise RuntimeError(
                "Piper female voice model is missing: " + str(self.voice_model)
            )
        if str(self.vendor) not in sys.path:
            sys.path.insert(0, str(self.vendor))
        from piper import PiperVoice

        self._voice = PiperVoice.load(str(self.voice_model))
        return self._voice

    def _synthesize(self, text: str, output: Path) -> None:
        voice = self._load_voice()
        with wave.open(str(output), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)

    def _play(self, wav_path: Path) -> None:
        player = self._player or self._detect_player()
        if not player:
            raise RuntimeError("no audio player found (paplay, pw-play, or aplay)")
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

        result = self._run(args, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                player
                + " failed: "
                + (result.stderr.strip() or result.stdout.strip())
            )

    def speak_now(self, text: str) -> None:
        spoken = str(text or "").strip()
        if not spoken:
            return

        state = self.ensure()
        if not state["connected_devices"]:
            raise RuntimeError("no paired/trusted Bluetooth audio device is connected")
        if not state["active_sinks"]:
            raise RuntimeError("Bluetooth connected but no audio sink is available yet")

        fd, tmp_name = tempfile.mkstemp(prefix="eira_voice_", suffix=".wav")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            self._synthesize(spoken, tmp)
            self._play(tmp)
            self._last_spoken = time.time()
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def enqueue(self, text: str) -> bool:
        spoken = str(text or "").strip()
        if not spoken:
            return False
        try:
            self._speech_queue.put_nowait(spoken)
            return True
        except queue.Full:
            try:
                self._speech_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._speech_queue.put_nowait(spoken)
                return True
            except queue.Full:
                return False

    def _connection_loop(self) -> None:
        while not self._stop.is_set():
            self.acquire()
            self._stop.wait(
                max(3, int(os.environ.get("EIRA_BT_RECONNECT_SECONDS", "5")))
            )

    def _speech_loop(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.speak_now(text)
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)

    def start(self) -> "BluetoothVoiceRuntime":
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._connection_loop,
                name="eira-bluetooth-reconnect",
                daemon=True,
            )
            self._speech_thread = threading.Thread(
                target=self._speech_loop,
                name="eira-bluetooth-speech",
                daemon=True,
            )
            self._thread.start()
            self._speech_thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        with self._lock:
            return {
                "ok": self._last_error is None,
                "role": ROLE,
                "version": VERSION,
                "connected_devices": dict(self._connected),
                "active_sinks": list(self._active_sinks),
                "default_sink": self._default_sink,
                "voice_model": str(self.voice_model),
                "voice_model_ready": self.voice_model.is_file(),
                "player": self._player,
                "last_error": self._last_error,
                "last_acquire": self._last_acquire,
                "last_spoken": self._last_spoken,
            }


_RUNTIME: Optional[BluetoothVoiceRuntime] = None
_RUNTIME_LOCK = threading.RLock()


def boot() -> BluetoothVoiceRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = BluetoothVoiceRuntime()
        return _RUNTIME.start()


def runtime() -> BluetoothVoiceRuntime:
    return boot()


def speak(text: str) -> bool:
    return runtime().enqueue(text)


def status() -> dict:
    return runtime().status()


def acquire_now() -> dict:
    return runtime().acquire()
