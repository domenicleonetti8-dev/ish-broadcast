#!/usr/bin/env python3
from __future__ import annotations
import json, os, shutil, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MODEL_NAME = 'en_US-hfc_female-medium.onnx'
MODEL_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/' + MODEL_NAME
CONFIG_URL = MODEL_URL + '.json'
TEST_PHRASE = 'Hey Dom. Flash Cube is connected to my voice.'

sys.path.insert(0, str(ROOT))
from eira2.operations.voice_asset_takeover import provision_native_voice_asset, verify_native_voice_asset
from eira2.delivery.native_bluetooth_voice import NativeBluetoothVoiceRuntime


def _external_candidates():
    roots = [
        Path('/media/domenicleonetti/easystore/EIRA'),
        Path.home(),
        Path('/tmp'),
    ]
    seen = set()
    for base in roots:
        if not base.exists():
            continue
        try:
            for p in base.rglob(MODEL_NAME):
                try:
                    rp = p.resolve()
                except Exception:
                    continue
                if rp in seen or ROOT == rp or ROOT in rp.parents:
                    continue
                seen.add(rp)
                cfg = Path(str(rp) + '.json')
                if rp.is_file() and cfg.is_file() and rp.stat().st_size > 0 and cfg.stat().st_size > 0:
                    yield rp, cfg, 'preserved_external'
        except (OSError, PermissionError):
            continue


def _download_pair():
    d = Path(tempfile.mkdtemp(prefix='eira2_voice_asset_'))
    model = d / MODEL_NAME
    config = d / (MODEL_NAME + '.json')
    headers = {'User-Agent': 'EIRA2-Voice-Path-Completion/1.0'}
    for url, dst in ((MODEL_URL, model), (CONFIG_URL, config)):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r, dst.open('wb') as f:
            shutil.copyfileobj(r, f)
        if not dst.is_file() or dst.stat().st_size <= 0:
            raise RuntimeError('voice_asset_download_empty:' + str(dst))
    return model, config, 'canonical_piper_download'


def _preferred_flash_cube(state):
    connected = state.get('connected_devices') or {}
    target = 'flash cube'
    for mac, name in connected.items():
        if str(name).strip().casefold() == target:
            sinks = [str(x) for x in (state.get('active_sinks') or [])]
            token = str(mac).replace(':', '_').casefold()
            for sink in sinks:
                if token in sink.casefold() or 'flash' in sink.casefold():
                    return str(mac), str(name), sink
            if len(sinks) == 1:
                return str(mac), str(name), sinks[0]
            return str(mac), str(name), None
    return None


def main():
    phrase = ' '.join(sys.argv[1:]).strip() or TEST_PHRASE
    source = next(_external_candidates(), None)
    if source is None:
        source = _download_pair()
    model, config, source_mode = source

    takeover = provision_native_voice_asset(
        runtime_root=ROOT,
        source=model,
        source_config=config,
    )
    verified = verify_native_voice_asset(runtime_root=ROOT)

    runtime = NativeBluetoothVoiceRuntime(ROOT)
    state = dict(runtime.acquire() or {})
    preferred = _preferred_flash_cube(state)
    if preferred is None:
        raise RuntimeError('flash_cube_not_connected:' + json.dumps(state, sort_keys=True)[:1800])
    mac, name, sink = preferred
    if sink and hasattr(runtime, '_default_sink'):
        runtime._default_sink = sink
    if sink and hasattr(runtime, '_active_sinks'):
        runtime._active_sinks = [sink]
    runtime.speak_now(phrase)

    out = {
        'schema': 'eira2_voice_path_completion_v1',
        'ok': True,
        'path': 'voice_asset_takeover -> verified_piper_pair -> native_bluetooth_voice -> Flash Cube',
        'source_mode': source_mode,
        'source_model': str(model),
        'takeover': takeover,
        'verified': verified,
        'flash_cube': {'mac': mac, 'name': name, 'sink': sink},
        'spoken': phrase,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
