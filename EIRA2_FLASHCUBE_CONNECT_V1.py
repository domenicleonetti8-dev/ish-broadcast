from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eira2.delivery.native_bluetooth_voice import NativeBluetoothVoiceRuntime
from eira2.delivery.voice import _sink_matches_device

PREFERRED = 'Flash Cube'


def main() -> int:
    runtime = NativeBluetoothVoiceRuntime(ROOT)
    state = dict(runtime.acquire() or {})
    connected = state.get('connected_devices') or {}
    if not isinstance(connected, dict):
        connected = {}
    matches = [(str(mac), str(name)) for mac, name in connected.items() if str(name).strip().casefold() == PREFERRED.casefold()]
    if not matches:
        print(json.dumps({'ok': False, 'error': 'flash_cube_not_connected', 'connected_devices': connected, 'last_error': state.get('last_error')}, indent=2))
        return 2

    sinks = [str(x) for x in (state.get('active_sinks') or []) if str(x).strip()]
    preferred_sink = None
    for sink in sinks:
        if any(_sink_matches_device(sink, mac=mac, name=name) for mac, name in matches):
            preferred_sink = sink
            break
    if preferred_sink is None and len(matches) == 1 and len(sinks) == 1:
        preferred_sink = sinks[0]
    if preferred_sink is None:
        print(json.dumps({'ok': False, 'error': 'flash_cube_sink_not_identified', 'connected_devices': connected, 'active_sinks': sinks}, indent=2))
        return 3

    runtime._default_sink = preferred_sink
    runtime._active_sinks = [preferred_sink]
    phrase = ' '.join(sys.argv[1:]).strip()
    if phrase:
        runtime.speak_now(phrase)
    final = dict(runtime.status() or {})
    print(json.dumps({'ok': True, 'preferred_device': PREFERRED, 'preferred_sink': preferred_sink, 'spoken': bool(phrase), 'connected_devices': final.get('connected_devices'), 'last_error': final.get('last_error')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
