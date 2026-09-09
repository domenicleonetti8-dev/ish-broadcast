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
STATE = ROOT / 'eira_probe' / 'orin_build_probe_supervisor_v2'
LOCK = STATE / 'supervisor.lock'
STATUS = STATE / 'status.json'
HEARTBEAT = ROOT / 'eira_probe' / 'orin_build_probe_v1' / 'heartbeat.json'
LOG = STATE / 'probe.log'
STARTUP_GRACE = 120.0
MAX_HEARTBEAT_AGE = 45.0
CHECK_INTERVAL = 5.0
MAX_BACKOFF = 30.0


def atomic_status(**extra):
    STATE.mkdir(parents=True, exist_ok=True)
    payload = {'schema':'eira2_orin_build_probe_supervisor_v2','unix':time.time(),**extra}
    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True)+'\n')
    os.replace(tmp, STATUS)


def heartbeat_state():
    try:
        data=json.loads(HEARTBEAT.read_text())
        stamp=float(data.get('unix',0.0))
        return bool(data.get('ok')), stamp, data
    except Exception as e:
        return False, 0.0, {'error':f'{type(e).__name__}:{e}'}


def stop_proc(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    lockf=LOCK.open('w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        atomic_status(ok=True, phase='already_supervised')
        return 0

    if not PROBE.is_file():
        atomic_status(ok=False, phase='probe_missing', probe=str(PROBE))
        return 2

    stopping=False
    proc=None
    restarts=0
    backoff=2.0
    started_at=0.0
    last_seen_hb=0.0
    last_progress_at=0.0

    def handle_stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    with LOG.open('ab', buffering=0) as log:
        while not stopping:
            now=time.time()
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    atomic_status(ok=False, phase='probe_exited', returncode=proc.returncode, restarts=restarts)
                    time.sleep(backoff)
                    backoff=min(MAX_BACKOFF, backoff*2.0)
                restarts += 1
                proc=subprocess.Popen([sys.executable, str(PROBE)], cwd=str(ROOT), stdout=log, stderr=log, start_new_session=True)
                started_at=time.time()
                last_seen_hb=0.0
                last_progress_at=started_at
                atomic_status(ok=True, phase='started', pid=proc.pid, restarts=restarts, startup_grace=STARTUP_GRACE)
                time.sleep(CHECK_INTERVAL)
                continue

            hb_ok, hb_stamp, hb_payload = heartbeat_state()
            now=time.time()
            if hb_stamp > last_seen_hb:
                last_seen_hb=hb_stamp
                last_progress_at=now
                backoff=2.0

            in_startup = (now-started_at) <= STARTUP_GRACE
            hb_age = now-hb_stamp if hb_stamp else None
            stalled = (not in_startup and (not hb_ok or hb_age is None or hb_age > MAX_HEARTBEAT_AGE))

            if stalled:
                old_pid=proc.pid
                stop_proc(proc)
                proc=None
                atomic_status(ok=False, phase='stale_heartbeat_restart', old_pid=old_pid,
                              heartbeat_age=hb_age, last_progress_age=now-last_progress_at,
                              restarts=restarts, heartbeat=hb_payload)
                time.sleep(backoff)
                backoff=min(MAX_BACKOFF, backoff*2.0)
                continue

            atomic_status(ok=True, phase='starting' if in_startup and not hb_ok else 'healthy',
                          pid=proc.pid, restarts=restarts, heartbeat_age=hb_age,
                          heartbeat_unix=hb_stamp, startup_age=now-started_at)
            time.sleep(CHECK_INTERVAL)

    stop_proc(proc)
    atomic_status(ok=True, phase='stopped', restarts=restarts)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
