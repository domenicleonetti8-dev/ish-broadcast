#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

LIVE = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/media/domenicleonetti/easystore/EIRA/LIVE"
).expanduser().resolve()

MAIN = LIVE / "main.py"
EXT = LIVE / "extensions" / "eira_bluetooth_voice_ai"
RUNTIME = EXT / "runtime.py"
VOICE_DIR = EXT / "voices"
VENDOR = EXT / "_vendor"
VOICE_MODEL = VOICE_DIR / "en_US-hfc_female-medium.onnx"
VOICE_CONFIG = VOICE_DIR / "en_US-hfc_female-medium.onnx.json"

RUNTIME_COMMIT = "0aa3a347a693cf4b84c3243f2c3b27bd732c8d60"
RUNTIME_URL = (
    "https://raw.githubusercontent.com/"
    "domenicleonetti8-dev/ish-broadcast/"
    + RUNTIME_COMMIT
    + "/EIRA_BLUETOOTH_WAKE_VOICE_RUNTIME.py"
)

VOICE_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "en/en_US/hfc_female/medium/"
)
VOICE_MODEL_URL = VOICE_BASE + "en_US-hfc_female-medium.onnx?download=true"
VOICE_CONFIG_URL = VOICE_BASE + "en_US-hfc_female-medium.onnx.json?download=true"

PIPER_VERSION = "1.4.2"


def die(message):
    raise SystemExit("EIRA FINAL BLUETOOTH VOICE: " + message)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(args, timeout=300, env=None):
    return subprocess.run(
        list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def download(url: str, dest: Path, min_bytes: int = 1):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=dest.name + ".", dir=str(dest.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Eira-final-bluetooth-voice"})
        with urllib.request.urlopen(req, timeout=90) as response, temp.open("wb") as out:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 150 * 1024 * 1024:
                    die("download exceeded safety limit: " + url)
                out.write(chunk)
        if temp.stat().st_size < min_bytes:
            die("download too small: " + url)
        temp.replace(dest)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


for path, label in (
    (MAIN, "main.py"),
    (LIVE / "extensions" / "omnivenom_mesh_ai" / "runtime.py", "OmniVenom"),
    (LIVE / "extensions" / "omnivenom_mesh_ai" / "eira_bridge.py", "two-brain bridge"),
    (LIVE / "extensions" / "unified_brain_ai" / "plugin.py", "Unified Brain"),
    (LIVE / "extensions" / "local_brain" / "router.py", "local brain"),
):
    if not path.is_file():
        die(label + " missing: " + str(path))

if not shutil.which("bluetoothctl"):
    die("bluetoothctl missing. BlueZ must exist before Eira can grab a real speaker.")

if not (shutil.which("pactl") or shutil.which("wpctl")):
    die("no PipeWire/PulseAudio routing command found (need pactl or wpctl).")

if not (shutil.which("paplay") or shutil.which("pw-play") or shutil.which("aplay")):
    die("no audio player found (need paplay, pw-play, or aplay).")

main_before = MAIN.read_bytes()
ext_backup = None
stamp = time.strftime("%Y%m%d_%H%M%S")
main_backup = LIVE / f"main.py.bak_final_bluetooth_voice_{stamp}"
shutil.copy2(MAIN, main_backup)

if EXT.exists():
    ext_backup = LIVE / "extensions" / f"eira_bluetooth_voice_ai.bak_{stamp}"
    if ext_backup.exists():
        shutil.rmtree(ext_backup)
    shutil.copytree(EXT, ext_backup)


def rollback():
    MAIN.write_bytes(main_before)
    if EXT.exists():
        shutil.rmtree(EXT)
    if ext_backup and ext_backup.exists():
        shutil.copytree(ext_backup, EXT)


try:
    EXT.mkdir(parents=True, exist_ok=True)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    VENDOR.mkdir(parents=True, exist_ok=True)

    # 1) Install the exact reviewed runtime.
    download(RUNTIME_URL, RUNTIME, min_bytes=10000)
    runtime_text = RUNTIME.read_text(encoding="utf-8")
    required = (
        'ROLE = "eira_bluetooth_voice_ai"',
        "class BluetoothVoiceRuntime:",
        'self._bluetoothctl("connect", mac',
        '"module-combine-sink"',
        "def speak(text: str) -> bool:",
        "def acquire_now() -> dict:",
    )
    missing = [marker for marker in required if marker not in runtime_text]
    if missing:
        die("runtime identity check failed: " + repr(missing))
    compile(runtime_text, str(RUNTIME), "exec")

    (EXT / "__init__.py").write_text(
        'from .runtime import acquire_now, boot, speak, status\n'
        '__all__ = ["acquire_now", "boot", "speak", "status"]\n',
        encoding="utf-8",
    )
    (EXT / "manifest.json").write_text(
        json.dumps(
            {
                "name": "eira_bluetooth_voice_ai",
                "version": "1.0.0",
                "kind": "physical_bluetooth_voice_output",
                "brain_count": 0,
                "reasoning_owner": "unified_brain_ai",
                "tandem_brain": "local_brain",
                "connective_fabric": "omnivenom_mesh_ai",
                "max_outputs": 10,
                "auto_scan": True,
                "auto_pair_best_audio_if_no_paired_audio": True,
                "auto_trust": True,
                "auto_connect": True,
                "auto_reconnect": True,
                "one_outward_voice": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # 2) Install local neural TTS into this extension only.
    piper_ready = False
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    try:
        import piper  # noqa: F401
        piper_ready = True
    except Exception:
        pass

    if not piper_ready:
        pip_base = [
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", "--no-input",
            "--upgrade", "--target", str(VENDOR),
            "piper-tts==" + PIPER_VERSION,
        ]
        result = run(pip_base, timeout=900)
        if result.returncode != 0:
            retry = [
                sys.executable, "-m", "pip", "install",
                "--disable-pip-version-check", "--no-input",
                "--break-system-packages",
                "--upgrade", "--target", str(VENDOR),
                "piper-tts==" + PIPER_VERSION,
            ]
            result = run(retry, timeout=900)
        if result.returncode != 0:
            die("Piper install failed: " + (result.stderr[-2000:] or result.stdout[-2000:]))

    for name in list(sys.modules):
        if name == "piper" or name.startswith("piper."):
            del sys.modules[name]
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    from piper import PiperVoice

    # 3) Pin a real female neural voice.
    if not VOICE_MODEL.is_file() or VOICE_MODEL.stat().st_size < 50_000_000:
        download(VOICE_MODEL_URL, VOICE_MODEL, min_bytes=50_000_000)
    if not VOICE_CONFIG.is_file() or VOICE_CONFIG.stat().st_size < 1000:
        download(VOICE_CONFIG_URL, VOICE_CONFIG, min_bytes=1000)
    with VOICE_CONFIG.open("r", encoding="utf-8") as handle:
        json.load(handle)

    voice = PiperVoice.load(str(VOICE_MODEL))
    fd, wav_name = tempfile.mkstemp(prefix="eira_tts_verify_", suffix=".wav")
    os.close(fd)
    wav_path = Path(wav_name)
    try:
        with wave.open(str(wav_path), "wb") as wav:
            voice.synthesize_wav("Eira voice verification.", wav)
        if wav_path.stat().st_size < 4000:
            die("Piper produced an invalid verification WAV")
    finally:
        try:
            wav_path.unlink()
        except FileNotFoundError:
            pass

    # 4) Replace only outward speech and start Bluetooth acquisition at startup.
    source = MAIN.read_text(encoding="utf-8")
    start = source.find("def _speak(response):")
    if start < 0:
        die("_speak(response) not found")
    end = source.find("\ndef live_runtime_report(", start)
    if end < 0:
        die("live_runtime_report boundary not found")

    speak_block = r'''def _speak(response):
    from extensions.ecosystem_kernel_ai.awareness import run as refresh_awareness
    from extensions.ecosystem_kernel_ai.evidence import render_response
    from extensions.eira_bluetooth_voice_ai import speak as bluetooth_speak

    refresh_awareness()
    evidence_checked = render_response(response)
    identity_checked = outward_text_gate(evidence_checked)
    spoken = str(identity_checked or "").strip()

    print("EIRA:", spoken)
    if spoken and not bluetooth_speak(spoken):
        print("EIRA Bluetooth voice warning: speech queue unavailable")


# EIRA_FINAL_BLUETOOTH_WAKE_VOICE_V1
try:
    from extensions.eira_bluetooth_voice_ai import boot as _boot_bluetooth_voice
    _EIRA_BLUETOOTH_VOICE = _boot_bluetooth_voice()
except Exception as _eira_bt_voice_error:
    print("EIRA Bluetooth voice warning:", _eira_bt_voice_error)

'''
    new_main = source[:start] + speak_block + source[end + 1:]
    if "extensions.omnivenom_mesh_ai.eira_bridge import chat" not in new_main:
        die("two-brain OmniVenom chat route disappeared; refusing patch")
    if "EIRA_FINAL_BLUETOOTH_WAKE_VOICE_V1" not in new_main:
        die("Bluetooth wake marker missing")
    ast.parse(new_main, filename=str(MAIN))
    MAIN.write_text(new_main, encoding="utf-8")

    # 5) Real hardware acquisition attempt.
    sys.path.insert(0, str(LIVE))
    importlib.invalidate_caches()
    bt = importlib.import_module("extensions.eira_bluetooth_voice_ai")
    state = bt.acquire_now()
    connected = state.get("connected_devices") or {}
    sinks = state.get("active_sinks") or []

    live_audio = "WAITING_FOR_DEVICE"
    if connected and sinks:
        runtime_mod = importlib.import_module("extensions.eira_bluetooth_voice_ai.runtime")
        runtime_mod.runtime().speak_now(
            "Eira Bluetooth voice is online. Both brains are connected through OmniVenom."
        )
        live_audio = "PASS"

except BaseException:
    rollback()
    raise

print("EIRA_FINAL_BLUETOOTH_WAKE_VOICE_INSTALL=PASS")
print("BRAINS=2")
print("DOMINANT=unified_brain_ai")
print("TANDEM=local_brain")
print("OMNIVENOM=connective_fabric")
print("BLUETOOTH_WAKE_ACQUIRE=ENABLED")
print("BLUETOOTH_AUTO_PAIR_BEST_AUDIO=ENABLED")
print("BLUETOOTH_AUTO_RECONNECT=ENABLED")
print("MAX_OUTPUTS=10")
print("VOICE=Piper en_US-hfc_female-medium")
print("VOICE_INPUT=UNCHANGED")
print("TYPING_INPUT=AVAILABLE")
print("LIVE_AUDIO_TEST=" + live_audio)
print("CONNECTED_DEVICES=" + json.dumps(connected, sort_keys=True))
print("ACTIVE_SINKS=" + json.dumps(sinks))
print("LAST_ERROR=" + str(state.get("last_error")))
print("RUNTIME_SOURCE_COMMIT=" + RUNTIME_COMMIT)
print("MAIN_BACKUP=" + str(main_backup))
print("MAIN_SHA256=" + sha(MAIN))
print("RUNTIME_SHA256=" + sha(RUNTIME))
print("VOICE_MODEL_SHA256=" + sha(VOICE_MODEL))
