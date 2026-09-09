#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

from eira2.operations.voice_asset_takeover import (
    provision_native_voice_asset,
    verify_native_voice_asset,
)

ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE").resolve()
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/hfc_female/medium"
MODEL = "en_US-hfc_female-medium.onnx"
CONFIG = MODEL + ".json"
MODEL_SHA256 = "914c473788fc1fa8b63ace1cdcdb44588f4ae523d3ab37df1536616835a140b7"
MODEL_SIZE = 63201294
CONFIG_MD5 = "c3d00f54dac3b4068f2576c15c5da3bc"
CONFIG_SIZE = 5033


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, dst: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "EIRA2-voice-provision/1"})
    with urllib.request.urlopen(request, timeout=300) as response, dst.open("wb") as out:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)


def main() -> int:
    try:
        verified = verify_native_voice_asset(runtime_root=ROOT)
        print(json.dumps({"ok": True, "status": "already_verified", "voice_asset": verified}, indent=2))
        return 0
    except Exception:
        pass

    with tempfile.TemporaryDirectory(prefix="eira2_voice_asset_") as tmp:
        tmpdir = Path(tmp)
        model = tmpdir / MODEL
        config = tmpdir / CONFIG
        fetch(f"{BASE}/{MODEL}?download=true", model)
        fetch(f"{BASE}/{CONFIG}?download=true", config)

        if model.stat().st_size != MODEL_SIZE:
            raise RuntimeError(f"voice_model_size_mismatch:{model.stat().st_size}")
        if sha256(model) != MODEL_SHA256:
            raise RuntimeError("voice_model_sha256_mismatch")
        if config.stat().st_size != CONFIG_SIZE:
            raise RuntimeError(f"voice_config_size_mismatch:{config.stat().st_size}")
        if md5(config) != CONFIG_MD5:
            raise RuntimeError("voice_config_md5_mismatch")

        provision = provision_native_voice_asset(
            runtime_root=ROOT,
            source=model,
            source_config=config,
        )
        verified = verify_native_voice_asset(runtime_root=ROOT)

    print(json.dumps({
        "ok": True,
        "status": "provisioned_and_verified",
        "model_sha256": MODEL_SHA256,
        "provision": provision,
        "voice_asset": verified,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
