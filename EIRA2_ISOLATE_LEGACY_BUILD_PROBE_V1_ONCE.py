#!/usr/bin/env python3
from __future__ import annotations
import json, os, signal, time
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
HB = ROOT/'eira_probe'/'orin_build_probe_v1'/'heartbeat.json'
STATE = ROOT/'eira_probe'/'isolation'/'legacy_build_probe_v1'
RECEIPT = STATE/'dormant_receipt.json'


def atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
    os.replace(tmp, path)


def main() -> int:
    if not HB.is_file():
        raise RuntimeError('legacy_v1_heartbeat_missing')
    hb = json.loads(HB.read_text())
    if hb.get('schema') != 'eira2_orin_build_probe_v1':
        raise RuntimeError('legacy_v1_schema_mismatch')
    pid = int(hb.get('pid') or 0)
    if pid <= 1:
        raise RuntimeError('legacy_v1_pid_invalid')
    cmdline_path = Path('/proc')/str(pid)/'cmdline'
    if not cmdline_path.is_file():
        atomic_json(RECEIPT, {
            'schema':'eira2_legacy_build_probe_v1_dormant_v1',
            'ok':True,'already_stopped':True,'pid':pid,'unix':time.time(),
            'preserved_state':str(HB.parent.relative_to(ROOT)),
            'keeper':'eira2_orin_build_probe_v3'
        })
        return 0
    cmdline = cmdline_path.read_bytes().replace(b'\x00', b' ').decode('utf-8','replace')
    if 'eira2_orin_build_probe.py' not in cmdline:
        raise RuntimeError('pid_command_not_build_probe')
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 8.0
    while time.time() < deadline and cmdline_path.exists():
        time.sleep(0.2)
    atomic_json(RECEIPT, {
        'schema':'eira2_legacy_build_probe_v1_dormant_v1',
        'ok':not cmdline_path.exists(),
        'pid':pid,
        'cmdline':cmdline,
        'signal':'SIGTERM',
        'unix':time.time(),
        'preserved_state':str(HB.parent.relative_to(ROOT)),
        'keeper':'eira2_orin_build_probe_v3'
    })
    return 0 if not cmdline_path.exists() else 3

if __name__ == '__main__':
    raise SystemExit(main())
