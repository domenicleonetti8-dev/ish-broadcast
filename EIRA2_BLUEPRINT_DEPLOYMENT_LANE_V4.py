#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from typing import Any

NORMAL_WRAPPER_COMMIT = "e18144c74324de86bfbf3a0c7480abb6cd949355"
NORMAL_WRAPPER_PATH = "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"
INSPECTION_PREFIX = "inspect_revamp_mic_lifecycle_v1"
SIGNATURES = ["/v1/listen", "getUserMedia", "packPCM16", "state.active", "transcribing", "inactive"]


def run(cmd: list[str], *, cwd: Path, timeout: int = 2400) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def publish(repo: Path, rel: Path, payload: dict[str, Any]) -> str:
    reset = run(["git", "reset", "--hard", "origin/master"], cwd=repo, timeout=300)
    if reset.returncode:
        raise RuntimeError("inspection_reset_failed:" + reset.stderr[-800:])
    atomic_json(repo / rel, payload)
    add = run(["git", "add", rel.as_posix()], cwd=repo, timeout=120)
    if add.returncode:
        raise RuntimeError("inspection_git_add_failed:" + add.stderr[-800:])
    if run(["git", "diff", "--cached", "--quiet"], cwd=repo, timeout=120).returncode != 0:
        commit = run([
            "git", "-c", "user.name=EIRA Read Only Probe", "-c", "user.email=eira-probe@localhost",
            "commit", "--quiet", "-m", "Return read-only revamp mic inspection",
        ], cwd=repo, timeout=120)
        if commit.returncode:
            raise RuntimeError("inspection_commit_failed:" + commit.stderr[-800:])
        pull = run(["git", "pull", "--rebase", "--quiet", "origin", "master"], cwd=repo, timeout=300)
        if pull.returncode:
            raise RuntimeError("inspection_rebase_failed:" + pull.stderr[-1000:])
        push = run(["git", "push", "--quiet", "origin", "master"], cwd=repo, timeout=300)
        if push.returncode:
            raise RuntimeError("inspection_push_failed:" + push.stderr[-1000:])
    return run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=120).stdout.strip()


def context(lines: list[str], indexes: list[int], radius: int = 80) -> list[dict[str, Any]]:
    spans = []
    used: set[tuple[int, int]] = set()
    for idx in indexes:
        start = max(0, idx - radius)
        end = min(len(lines), idx + radius + 1)
        key = (start, end)
        if key in used:
            continue
        used.add(key)
        spans.append({
            "start_line": start + 1,
            "end_line": end,
            "source": "\n".join(f"{i+1:05d}: {lines[i]}" for i in range(start, end)),
        })
    return spans[:12]


def inspect_live(root: Path, packet_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    candidates: list[Path] = []
    for base in (root / "eira2", root / "extensions"):
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".js", ".html"}:
                candidates.append(p)
    for p in sorted(set(candidates)):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matched = [s for s in SIGNATURES if s in text]
        if not matched:
            continue
        lines = text.splitlines()
        indexes = [i for i, line in enumerate(lines) if any(s in line for s in matched)]
        try:
            rel = p.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            rel = str(p)
        rows.append({
            "path": rel,
            "sha256": sha256_file(p),
            "bytes": p.stat().st_size,
            "matched_signatures": matched,
            "match_line_numbers": [i + 1 for i in indexes[:80]],
            "contexts": context(lines, indexes),
        })
    rows.sort(key=lambda r: (-len(r["matched_signatures"]), r["path"]))
    return {
        "schema": "eira2_read_only_revamp_mic_inspection_v1",
        "packet_id": packet_id,
        "mode": "read_only",
        "mutates_live": False,
        "root": str(root),
        "signatures": SIGNATURES,
        "candidate_files_scanned": len(candidates),
        "matching_files": rows[:20],
        "best_match": rows[0] if rows else None,
        "generated_unix": time.time(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--source-repo-root", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    packet_path = Path(a.packet).resolve()
    repo = Path(a.source_repo_root).resolve()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet_id = str(packet.get("packet_id") or "")

    if packet_id.startswith(INSPECTION_PREFIX):
        payload = inspect_live(root, packet_id)
        rel = Path("eira2_transport_bus/from_superprobe/inspections") / "inspect_revamp_mic_lifecycle_v1__result.json"
        commit = publish(repo, rel, payload)
        print(json.dumps({
            "EIRA2_BLUEPRINT_DEPLOYMENT_V4": "PASS",
            "inspection_only": True,
            "mutates_live": False,
            "packet_id": packet_id,
            "matching_files": len(payload.get("matching_files") or []),
            "return_transport_commit": commit,
        }, indent=2))
        return 0

    delegate = Path("/tmp") / f"eira2_lane_v4_normal_{os.getpid()}.py"
    show = subprocess.run([
        "git", "-C", str(repo), "show", f"{NORMAL_WRAPPER_COMMIT}:{NORMAL_WRAPPER_PATH}"
    ], capture_output=True, timeout=120, check=False)
    if show.returncode:
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4": "FAIL", "error": "normal_wrapper_fetch_failed"}), file=sys.stderr)
        return 2
    delegate.write_bytes(show.stdout)
    try:
        proc = run([
            sys.executable, str(delegate), "--root", str(root), "--packet", str(packet_path),
            "--source-repo-root", str(repo),
        ], cwd=root, timeout=3600)
    finally:
        try:
            delegate.unlink()
        except OSError:
            pass
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
