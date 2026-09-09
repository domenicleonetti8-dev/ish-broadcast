#!/usr/bin/env python3
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, shutil, socket, subprocess, sys, time
from pathlib import Path
from typing import Any

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
STATE = ROOT / 'eira_probe' / 'orin_build_probe_v2'
REPO = STATE / 'repo'
ORIGIN = 'https://github.com/domenicleonetti8-dev/ish-broadcast.git'
INBOX = Path('eira2_build_probe/inbox')
OUTBOX = Path('eira2_build_probe/outbox')
SCHEMA = 'eira2_orin_build_probe_v2'
POLL = 3.0
LOCK = STATE / 'worker.lock'
HEARTBEAT = STATE / 'heartbeat.json'

def sd_notify(msg: str) -> None:
    addr = os.environ.get('NOTIFY_SOCKET')
    if not addr:
        return
    if addr.startswith('@'):
        addr = '\0' + addr[1:]
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.connect(addr)
        s.sendall(msg.encode())
        s.close()
    except Exception:
        pass

def run(cmd, cwd=None, timeout=75, check=True):
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True,
                       capture_output=True, timeout=timeout, check=False)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-2500:])
    return p

def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def atomic_json(p: Path, obj: Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    t=p.with_name(p.name+f'.tmp.{os.getpid()}')
    t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    os.replace(t,p)

def heartbeat(ok: bool, phase: str, **extra):
    atomic_json(HEARTBEAT, {'schema':SCHEMA,'ok':ok,'phase':phase,'pid':os.getpid(),'unix':time.time(),**extra})
    sd_notify('WATCHDOG=1\nSTATUS='+phase)

def safe_rel(v: str) -> Path:
    p=Path(str(v or ''))
    if p.is_absolute() or not p.parts or '..' in p.parts or '.git' in p.parts:
        raise ValueError('unsafe_path')
    out=(ROOT/p).resolve()
    if out != ROOT and ROOT not in out.parents:
        raise ValueError('outside_live')
    return out

def sync():
    STATE.mkdir(parents=True,exist_ok=True)
    if not (REPO/'.git').is_dir():
        if REPO.exists(): shutil.rmtree(REPO)
        run(['git','clone','--quiet',ORIGIN,str(REPO)],timeout=75)
    for cmd in (
        ['git','fetch','--quiet','origin','master'],
        ['git','checkout','--quiet','-B','orin_build_probe_runtime','origin/master'],
        ['git','reset','--hard','origin/master'],
        ['git','clean','-fd'],
    ):
        run(cmd,REPO,timeout=75)
    return run(['git','rev-parse','HEAD'],REPO,timeout=20).stdout.strip()

def publish(rid: str, receipt: dict[str,Any]) -> str:
    sync()
    rel=OUTBOX/f'{rid}.json'; p=REPO/rel
    atomic_json(p,receipt)
    run(['git','add',rel.as_posix()],REPO,timeout=20)
    if run(['git','diff','--cached','--quiet'],REPO,timeout=20,check=False).returncode != 0:
        run(['git','-c','user.name=EIRA Orin Build Probe','-c','user.email=eira-build-probe@localhost','commit','--quiet','-m',f'Build probe receipt {rid}'],REPO,timeout=30)
        run(['git','pull','--rebase','--quiet','origin','master'],REPO,timeout=75)
        run(['git','push','--quiet','origin','HEAD:master'],REPO,timeout=75)
    return run(['git','rev-parse','HEAD'],REPO,timeout=20).stdout.strip()

def git_blob(commit: str, repo_path: str) -> bytes:
    if len(commit)!=40 or any(c not in '0123456789abcdefABCDEF' for c in commit): raise ValueError('invalid_commit')
    rel=Path(repo_path)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts: raise ValueError('invalid_repo_path')
    p=subprocess.run(['git','-C',str(REPO),'show',f'{commit}:{rel.as_posix()}'],capture_output=True,timeout=60,check=False)
    if p.returncode: raise RuntimeError('source_blob_missing:'+p.stderr[-1600:].decode(errors='replace'))
    return p.stdout

def backup(rid: str,target: Path):
    if not target.is_file(): return None
    rel=target.relative_to(ROOT); dst=STATE/'backups'/rid/rel
    dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,dst)
    return str(dst.relative_to(ROOT))

def deploy(rid: str, cmd: dict[str,Any]) -> dict[str,Any]:
    src=cmd.get('source') or {}; target=safe_rel(str(cmd.get('target_path') or ''))
    raw=git_blob(str(src.get('commit') or ''),str(src.get('path') or ''))
    expected=str(src.get('sha256') or '').lower()
    if expected and sha_bytes(raw)!=expected: raise RuntimeError('source_sha256_mismatch')
    if target.suffix=='.py': compile(raw.decode('utf-8'),str(target),'exec')
    before=target.read_bytes() if target.is_file() else None; bak=backup(rid,target)
    target.parent.mkdir(parents=True,exist_ok=True); tmp=target.with_name(target.name+'.build_probe_tmp')
    tmp.write_bytes(raw); os.replace(tmp,target); after=sha_file(target)
    if after!=sha_bytes(raw):
        if before is None: target.unlink(missing_ok=True)
        else: target.write_bytes(before)
        raise RuntimeError('post_write_hash_mismatch_rolled_back')
    if target.suffix=='.py':
        q=run(['python3','-m','py_compile',str(target)],timeout=30,check=False)
        if q.returncode:
            if before is None: target.unlink(missing_ok=True)
            else: target.write_bytes(before)
            raise RuntimeError('python_compile_failed_rolled_back:'+q.stderr[-1200:])
    return {'target_path':str(target.relative_to(ROOT)),'before_sha256':sha_bytes(before) if before is not None else None,'after_sha256':after,'payload_sha256':sha_bytes(raw),'backup':bak,'compile_ok':True if target.suffix=='.py' else None}

def inspect(cmd: dict[str,Any]) -> dict[str,Any]:
    op=str(cmd.get('op') or '')
    if op=='read':
        p=safe_rel(str(cmd.get('path') or '')); b=p.read_bytes(); lim=min(max(int(cmd.get('max_bytes',500000)),1),2000000)
        return {'path':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':sha_bytes(b),'text':b[:lim].decode('utf-8','replace'),'truncated':len(b)>lim}
    if op=='list':
        p=safe_rel(str(cmd.get('path') or '.')); lim=min(max(int(cmd.get('limit',500)),1),5000)
        return {'path':str(p.relative_to(ROOT)) if p!=ROOT else '.','items':[{'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir())[:lim]]}
    if op=='search':
        term=str(cmd.get('term') or ''); roots=[safe_rel(x) for x in (cmd.get('roots') or ['eira2','extensions','tools'])]; lim=min(max(int(cmd.get('limit',100)),1),500); hits=[]
        for base in roots:
            if not base.exists(): continue
            for p in base.rglob('*'):
                if len(hits)>=lim: break
                if not p.is_file() or p.suffix.lower() not in {'.py','.json','.js','.html','.md','.txt'}: continue
                try: text=p.read_text(errors='replace')
                except Exception: continue
                if term in text: hits.append({'path':str(p.relative_to(ROOT)),'sha256':sha_file(p),'bytes':p.stat().st_size})
        return {'term':term,'hits':hits}
    if op=='compile':
        p=safe_rel(str(cmd.get('path') or '')); q=run(['python3','-m','py_compile',str(p)],timeout=30,check=False)
        return {'path':str(p.relative_to(ROOT)),'ok':q.returncode==0,'returncode':q.returncode,'stderr':q.stderr[-2000:]}
    if op=='health': return {'root':str(ROOT),'state':str(STATE),'repo':str(REPO),'pid':os.getpid(),'always_on':True}
    raise ValueError('unsupported_op')

def execute(cmd: dict[str,Any]) -> dict[str,Any]:
    rid=str(cmd.get('id') or '').strip()
    if not rid: raise ValueError('missing_id')
    op=str(cmd.get('op') or '').strip(); base={'schema':SCHEMA,'id':rid,'op':op,'root':str(ROOT),'unix':time.time()}
    if op=='deploy': base.update(ok=True,result=deploy(rid,cmd))
    else: base.update(ok=True,result=inspect(cmd))
    return base

def acquire_lock():
    STATE.mkdir(parents=True,exist_ok=True)
    f=LOCK.open('w')
    try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise RuntimeError('build_probe_already_running')
    f.write(str(os.getpid())); f.flush()
    return f

def loop(interval: float):
    lockf=acquire_lock(); executed=STATE/'executed'; executed.mkdir(parents=True,exist_ok=True)
    sd_notify('READY=1\nSTATUS=starting')
    heartbeat(True,'starting')
    while True:
        try:
            head=sync(); heartbeat(True,'synced',head=head)
            inbox=REPO/INBOX; inbox.mkdir(parents=True,exist_ok=True)
            for p in sorted(inbox.glob('*.json')):
                raw=p.read_bytes(); digest=sha_bytes(raw); marker=executed/f'{digest}.json'
                if marker.exists(): continue
                try: cmd=json.loads(raw.decode('utf-8')); rec=execute(cmd)
                except Exception as e: rec={'schema':SCHEMA,'id':p.stem,'ok':False,'error':f'{type(e).__name__}:{e}'[:4000],'unix':time.time(),'root':str(ROOT)}
                rec['command_sha256']=digest; atomic_json(marker,rec); rec['return_commit']=publish(str(rec.get('id') or p.stem),rec); heartbeat(True,'published',last_id=str(rec.get('id') or p.stem))
            time.sleep(max(1.0,interval)); heartbeat(True,'idle',head=head)
        except Exception as e:
            heartbeat(False,'error',error=f'{type(e).__name__}:{e}'[:3000]); time.sleep(max(2.0,interval))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--interval',type=float,default=POLL); args=ap.parse_args(); loop(args.interval)
if __name__=='__main__': main()
