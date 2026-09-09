#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
PROBE = ROOT / 'tools' / 'eira2_orin_build_probe.py'
STATE = ROOT / 'eira_probe' / 'orin_build_probe_supervisor_v1'
LOCK = STATE / 'supervisor.lock'
STATUS = STATE / 'status.json'
HEARTBEAT = ROOT / 'eira_probe' / 'orin_build_probe_v1' / 'heartbeat.json'
LOG = STATE / 'probe.log'
MAX_HEARTBEAT_AGE = 30.0
RESTART_DELAY = 2.0


def write_status(**extra):
    STATE.mkdir(parents=True, exist_ok=True)
    payload = {'schema':'eira2_orin_build_probe_supervisor_v1','unix':time.time(),**extra}
    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True)+'\n')
    os.replace(tmp, STATUS)


def heartbeat_fresh() -> bool:
    try:
        data=json.loads(HEARTBEAT.read_text())
        return bool(data.get('ok')) and time.time()-float(data.get('unix',0)) <= MAX_HEARTBEAT_AGE
    except Exception:
        return False


def stop_proc(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait(timeout=5)


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    lockf=LOCK.open('w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        write_status(ok=True, phase='already_supervised')
        return 0

    if not PROBE.is_file():
        write_status(ok=False, phase='probe_missing', probe=str(PROBE))
        return 2

    stopping=False
    proc=None
    restarts=0

    def handle_stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    with LOG.open('ab', buffering=0) as log:
        while not stopping:
            if proc is None or proc.poll() is not None:
                restarts += 1
                proc=subprocess.Popen([sys.executable, str(PROBE)], cwd=str(ROOT), stdout=log, stderr=log, start_new_session=True)
                write_status(ok=True, phase='started', pid=proc.pid, restarts=restarts)
                time.sleep(5)

            if not heartbeat_fresh():
                old_pid = proc.pid if proc else None
                stop_proc(proc)
                proc=None
                write_status(ok=False, phase='stale_heartbeat_restart', old_pid=old_pid, restarts=restarts)
                time.sleep(RESTART_DELAY)
                continue

            write_status(ok=True, phase='healthy', pid=proc.pid, restarts=restarts, heartbeat_age=max(0.0,time.time()-HEARTBEAT.stat().st_mtime))
            time.sleep(5)

    stop_proc(proc)
    write_status(ok=True, phase='stopped', restarts=restarts)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
