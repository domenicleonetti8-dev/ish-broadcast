#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "eira2_bidirectional_transport_v2"
REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"
DEFAULT_ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
DEFAULT_STATE = Path.home() / ".local" / "state" / "eira2-transport-v2"
IN_LANES = ("requests", "blueprints", "jobs", "builds", "artifacts")
OUT_LANES = ("receipts", "jobs", "builds", "artifacts", "diagnostics")
REMOTE_IN = Path("eira2_transport_bus/to_superprobe")
REMOTE_OUT = Path("eira2_transport_bus/from_superprobe")
BLUEPRINT_CONSUMER = "EIRA2_BIDIRECTIONAL_BLUEPRINT_CONSUMER_V1.py"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def atomic_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + f".tmp.{os.getpid()}")
    t.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(t, p)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, check=False)


def ensure_dirs(state: Path) -> None:
    for lane in IN_LANES:
        (state / "inbox" / lane).mkdir(parents=True, exist_ok=True)
    for lane in OUT_LANES:
        (state / "outbox" / lane).mkdir(parents=True, exist_ok=True)
    (state / "handled").mkdir(parents=True, exist_ok=True)
    (state / "runtime").mkdir(parents=True, exist_ok=True)


def sync_repo(state: Path) -> Path:
    repo = state / "repo"
    if not (repo / ".git").is_dir():
        if repo.exists():
            shutil.rmtree(repo)
        p = run(["git", "clone", "--quiet", REPO_URL, str(repo)], timeout=600)
        if p.returncode:
            raise RuntimeError("git_clone_failed:" + p.stderr[-1200:])
    for cmd in (["git", "fetch", "--quiet", "origin", "master"], ["git", "checkout", "--quiet", "master"], ["git", "reset", "--hard", "origin/master"]):
        p = run(list(cmd), cwd=repo, timeout=300)
        if p.returncode:
            raise RuntimeError("git_sync_failed:" + p.stderr[-1200:])
    return repo


def mirror_inbound(repo: Path, state: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lane in IN_LANES:
        src = repo / REMOTE_IN / lane
        dst = state / "inbox" / lane
        n = 0
        if src.is_dir():
            for p in sorted(src.iterdir()):
                if not p.is_file():
                    continue
                digest = sha256_file(p)
                marker = state / "handled" / f"mirror__{lane}__{digest}.json"
                if marker.exists():
                    continue
                target = dst / p.name
                if not target.exists() or sha256_file(target) != digest:
                    shutil.copy2(p, target)
                atomic_json(marker, {"schema": SCHEMA, "lane": lane, "name": p.name, "sha256": digest, "mirrored_utc": utc()})
                n += 1
        counts[lane] = n
    return counts


def git_publish(repo: Path, rels: list[Path], message: str) -> str | None:
    if not rels:
        return None
    p = run(["git", "fetch", "--quiet", "origin", "master"], cwd=repo, timeout=300)
    if p.returncode:
        raise RuntimeError("publish_fetch_failed:" + p.stderr[-800:])
    p = run(["git", "reset", "--hard", "origin/master"], cwd=repo, timeout=300)
    if p.returncode:
        raise RuntimeError("publish_reset_failed:" + p.stderr[-800:])
    p = run(["git", "add", *[r.as_posix() for r in rels]], cwd=repo, timeout=120)
    if p.returncode:
        raise RuntimeError("publish_add_failed:" + p.stderr[-800:])
    if run(["git", "diff", "--cached", "--quiet"], cwd=repo, timeout=120).returncode == 0:
        return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    p = run(["git", "-c", "user.name=EIRA2 Bidirectional Transport", "-c", "user.email=eira2-transport@localhost", "commit", "--quiet", "-m", message], cwd=repo, timeout=120)
    if p.returncode:
        raise RuntimeError("publish_commit_failed:" + p.stderr[-1000:])
    p = run(["git", "pull", "--rebase", "--quiet", "origin", "master"], cwd=repo, timeout=300)
    if p.returncode:
        raise RuntimeError("publish_rebase_failed:" + p.stderr[-1200:])
    p = run(["git", "push", "--quiet", "origin", "master"], cwd=repo, timeout=300)
    if p.returncode:
        raise RuntimeError("publish_push_failed:" + p.stderr[-1200:])
    return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()


def publish_outbound(repo: Path, state: Path) -> dict[str, int]:
    copied: list[Path] = []
    counts: dict[str, int] = {}
    for lane in OUT_LANES:
        src = state / "outbox" / lane
        n = 0
        for p in sorted(src.iterdir()):
            if not p.is_file():
                continue
            digest = sha256_file(p)
            marker = state / "handled" / f"publish__{lane}__{digest}.json"
            if marker.exists():
                continue
            rel = REMOTE_OUT / lane / p.name
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            copied.append(rel)
            atomic_json(marker, {"schema": SCHEMA, "lane": lane, "name": p.name, "sha256": digest, "queued_utc": utc()})
            n += 1
        counts[lane] = n
    if copied:
        commit = git_publish(repo, copied, "Return EIRA2 bidirectional transport payloads")
        for marker in (state / "handled").glob("publish__*.json"):
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                if "commit" not in data:
                    data["commit"] = commit
                    data["published_utc"] = utc()
                    atomic_json(marker, data)
            except Exception:
                pass
    return counts


def mount_snapshot(root: Path) -> dict[str, Any]:
    # This is intentionally /proc based: no stat/open on the NTFS tree.
    rows = []
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if str(root).startswith(line.split()[4].replace("\\040", " ")):
                rows.append(line)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}", "rows": []}
    return {"ok": bool(rows), "rows": rows[-8:]}


def d_state_snapshot() -> list[dict[str, str]]:
    p = run(["ps", "-eo", "pid=,stat=,comm=,wchan="], timeout=30)
    rows = []
    for line in p.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[1].startswith("D"):
            rows.append({"pid": parts[0], "stat": parts[1], "comm": parts[2], "wchan": parts[3] if len(parts) > 3 else ""})
    return rows


def storage_admission(root: Path) -> tuple[bool, dict[str, Any]]:
    mounts = mount_snapshot(root)
    drows = d_state_snapshot()
    ntfs_blocked = [r for r in drows if "ntfs" in r.get("wchan", "").lower() or r.get("comm") in {"tar", "python3", "bash"}]
    ok = bool(mounts.get("ok")) and not ntfs_blocked
    return ok, {"mount": mounts, "d_state": drows, "blocked_candidates": ntfs_blocked}


def blueprint_worker_tick(repo: Path, root: Path, state: Path) -> dict[str, Any]:
    runtime = state / "runtime"
    pidfile = runtime / "blueprint_worker.pid"
    statusfile = runtime / "blueprint_worker.json"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            return {"state": "RUNNING", "pid": pid}
        except Exception:
            pidfile.unlink(missing_ok=True)
    pending = list((state / "inbox" / "blueprints").glob("*.json"))
    if not pending:
        return {"state": "IDLE"}
    ok, evidence = storage_admission(root)
    if not ok:
        atomic_json(statusfile, {"schema": SCHEMA, "state": "STORAGE_BLOCKED", "utc": utc(), "evidence": evidence})
        return {"state": "STORAGE_BLOCKED", "evidence": evidence}
    consumer = repo / BLUEPRINT_CONSUMER
    if not consumer.is_file():
        return {"state": "ERROR", "error": "blueprint_consumer_missing"}
    log = runtime / "blueprint_worker.log"
    with log.open("ab") as fh:
        proc = subprocess.Popen([sys.executable, str(consumer), "--root", str(root), "--work", str(state / "blueprint-work"), "--once"], cwd=str(Path.home()), stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    pidfile.write_text(str(proc.pid) + "\n")
    atomic_json(statusfile, {"schema": SCHEMA, "state": "STARTED", "pid": proc.pid, "utc": utc(), "evidence": evidence})
    return {"state": "STARTED", "pid": proc.pid}


def emit(state: Path, lane: str, source: Path, name: str | None) -> dict[str, Any]:
    if lane not in OUT_LANES:
        raise SystemExit(f"invalid outbound lane: {lane}")
    if not source.is_file():
        raise SystemExit("source file missing")
    dst = state / "outbox" / lane / (name or source.name)
    shutil.copy2(source, dst)
    return {"schema": SCHEMA, "queued": True, "lane": lane, "path": str(dst), "sha256": sha256_file(dst)}


def status(state: Path, root: Path) -> dict[str, Any]:
    ok, evidence = storage_admission(root)
    return {
        "schema": SCHEMA,
        "utc": utc(),
        "control_plane": str(state),
        "control_plane_on_live_drive": str(state).startswith(str(root)),
        "live_root": str(root),
        "storage_admitted": ok,
        "storage_evidence": evidence,
        "inbox": {lane: len(list((state / "inbox" / lane).glob("*"))) for lane in IN_LANES},
        "outbox": {lane: len(list((state / "outbox" / lane).glob("*"))) for lane in OUT_LANES},
    }


def once(root: Path, state: Path) -> dict[str, Any]:
    ensure_dirs(state)
    repo = sync_repo(state)
    inbound = mirror_inbound(repo, state)
    worker = blueprint_worker_tick(repo, root, state)
    repo = sync_repo(state)
    outbound = publish_outbound(repo, state)
    s = status(state, root)
    heartbeat = {"schema": SCHEMA, "utc": utc(), "inbound": inbound, "worker": worker, "outbound": outbound, "status": s}
    atomic_json(state / "runtime" / "heartbeat.json", heartbeat)
    return heartbeat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once")
    d = sub.add_parser("daemon"); d.add_argument("--interval", type=float, default=3.0)
    sub.add_parser("status")
    e = sub.add_parser("emit"); e.add_argument("lane", choices=OUT_LANES); e.add_argument("source"); e.add_argument("--name")
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    state = Path(args.state).expanduser()
    ensure_dirs(state)
    if args.cmd == "status":
        print(json.dumps(status(state, root), indent=2)); return 0
    if args.cmd == "emit":
        print(json.dumps(emit(state, args.lane, Path(args.source).expanduser(), args.name), indent=2)); return 0
    if args.cmd == "once":
        print(json.dumps(once(root, state), indent=2)); return 0
    while True:
        try:
            print(json.dumps(once(root, state), separators=(",", ":")), flush=True)
        except Exception as exc:
            atomic_json(state / "runtime" / "last_error.json", {"schema": SCHEMA, "utc": utc(), "error": f"{type(exc).__name__}:{exc}"})
            print(json.dumps({"EIRA2_BIDIRECTIONAL_TRANSPORT_V2": "FAIL", "error": f"{type(exc).__name__}:{exc}"}), file=sys.stderr, flush=True)
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
