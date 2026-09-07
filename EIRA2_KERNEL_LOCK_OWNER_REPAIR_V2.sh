#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/domenicleonetti/easystore/EIRA/LIVE
LOCK="$ROOT/var/eira2.lock"
OUT="$ROOT/eira_probe/kernel_lock_owner_repair_v2.json"
WORK="$ROOT/eira_probe/kernel_lock_owner_repair_repo"
cd "$ROOT"
mkdir -p "$ROOT/eira_probe" "$ROOT/var"
python3 - <<'PY' > "$OUT.tmp.$$"
from __future__ import annotations
import fcntl, json, os, signal, socket, subprocess, time, urllib.request
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
LOCK=ROOT/'var'/'eira2.lock'
res={'schema':'eira2_kernel_lock_owner_repair_v2','root':str(ROOT),'lock':str(LOCK),'generated_unix':time.time(),'action':'none','ok':False}
LOCK.parent.mkdir(parents=True,exist_ok=True)

def read_pid_text():
    try: return LOCK.read_text(encoding='utf-8',errors='replace').strip()
    except Exception: return ''
def proc_info(pid:int):
    p=Path('/proc')/str(pid)
    if not p.exists(): return None
    try: cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace').strip()
    except Exception: cmd=''
    try: cwd=os.readlink(p/'cwd')
    except Exception: cwd=''
    try: exe=os.readlink(p/'exe')
    except Exception: exe=''
    return {'pid':pid,'cmdline':cmd,'cwd':cwd,'exe':exe}
def lock_is_free():
    h=LOCK.open('a+',encoding='utf-8')
    try:
        fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(h.fileno(),fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        h.close()
def health_8782():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8782/health',timeout=2) as r:
            body=r.read(4096).decode(errors='replace')
            return {'ok':200 <= r.status < 300,'status':r.status,'body':body}
    except Exception as e:
        return {'ok':False,'error':f'{type(e).__name__}:{e}'}

def holders():
    found=[]
    # Prefer fuser if available; it reports kernel fd ownership rather than trusting lockfile text.
    try:
        p=subprocess.run(['fuser',str(LOCK)],text=True,capture_output=True,timeout=5)
        text=(p.stdout+' '+p.stderr).strip()
        for tok in text.replace(':',' ').split():
            if tok.isdigit(): found.append(int(tok))
    except Exception: pass
    if not found:
        txt=read_pid_text()
        if txt.isdigit():
            pid=int(txt)
            if proc_info(pid) is not None: found.append(pid)
    return sorted(set(found))

res['lockfile_pid_text']=read_pid_text()
res['lock_free_before']=lock_is_free()
res['health_before']=health_8782()
hs=holders(); res['holders_before']=[proc_info(p) for p in hs if proc_info(p)]
if res['lock_free_before']:
    res['action']='lock_already_free'; res['ok']=True
elif not hs:
    res['action']='held_but_owner_unresolved'; res['error']='kernel_reports_lock_busy_but_owner_not_resolved'
else:
    # Never kill merely from PID text. Require exact Easystore provenance and EIRA2 command identity.
    candidates=[]; unsafe=[]
    for pid in hs:
        info=proc_info(pid) or {}
        cmd=info.get('cmdline',''); cwd=info.get('cwd','')
        provenance=(str(ROOT) in cmd) or (cwd==str(ROOT)) or cwd.startswith(str(ROOT)+'/')
        identity=('main.py' in cmd) or ('-m eira2' in cmd) or ('eira2' in cmd.lower())
        if provenance and identity: candidates.append(info)
        else: unsafe.append(info)
    res['eligible_eira2_holders']=candidates; res['protected_noncanonical_holders']=unsafe
    if unsafe or len(candidates)!=len(hs):
        res['action']='refuse_noncanonical_owner'; res['error']='lock owner is not proven canonical EIRA2 process'
    elif res['health_before'].get('ok'):
        res['action']='preserve_healthy_existing_runtime'; res['ok']=True; res['diagnosis']='duplicate_start_attempt_against_healthy_existing_eira2'
    else:
        res['action']='retire_unhealthy_duplicate_runtime'
        killed=[]
        for info in candidates:
            pid=info['pid']
            try: os.kill(pid,signal.SIGTERM); killed.append({'pid':pid,'signal':'TERM'})
            except ProcessLookupError: pass
        deadline=time.time()+8
        while time.time()<deadline and not lock_is_free(): time.sleep(.25)
        if not lock_is_free():
            for info in candidates:
                pid=info['pid']
                if proc_info(pid) is not None:
                    try: os.kill(pid,signal.SIGKILL); killed.append({'pid':pid,'signal':'KILL'})
                    except ProcessLookupError: pass
            deadline=time.time()+3
            while time.time()<deadline and not lock_is_free(): time.sleep(.2)
        res['signals']=killed
        res['lock_free_after']=lock_is_free()
        res['health_after']=health_8782()
        res['ok']=bool(res['lock_free_after'])
        if not res['ok']: res['error']='lock_still_held_after_retiring_proven_unhealthy_eira2_holder'
print(json.dumps(res,indent=2,sort_keys=True))
PY
mv -f "$OUT.tmp.$$" "$OUT"
if [[ ! -d "$WORK/.git" ]]; then
  rm -rf "$WORK"
  git clone --quiet https://github.com/domenicleonetti8-dev/ish-broadcast.git "$WORK"
fi
git -C "$WORK" fetch --quiet origin master
git -C "$WORK" checkout --quiet master
git -C "$WORK" reset --hard --quiet origin/master
DEST="$WORK/eira2_transport_bus/from_superprobe/receipts/kernel_lock_owner_repair_v2__receipt.json"
mkdir -p "$(dirname "$DEST")"
cp "$OUT" "$DEST"
git -C "$WORK" add "eira2_transport_bus/from_superprobe/receipts/kernel_lock_owner_repair_v2__receipt.json"
if ! git -C "$WORK" diff --cached --quiet; then
  git -C "$WORK" -c user.name='EIRA Kernel Repair' -c user.email='eira-kernel-repair@localhost' commit --quiet -m 'Return EIRA2 kernel lock owner repair V2'
  git -C "$WORK" pull --rebase --quiet origin master
  git -C "$WORK" push --quiet origin master
fi
python3 - <<'PY'
import json
p='/media/domenicleonetti/easystore/EIRA/LIVE/eira_probe/kernel_lock_owner_repair_v2.json'
d=json.load(open(p))
print('EIRA2_KERNEL_LOCK_OWNER_REPAIR=' + ('PASS' if d.get('ok') else 'FAIL'))
print('ACTION=' + str(d.get('action')))
if d.get('error'): print('ERROR=' + str(d['error']))
PY
