#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_glass_mesh_v1"
VERSION = "1.0.0"
DEFAULT_INTERVAL = 15.0
MAX_TEXT_BYTES = 2_000_000
MAX_PORTALS = 100_000
TEXT_SUFFIXES = {".py", ".json", ".html", ".js", ".md", ".txt", ".toml", ".yaml", ".yml", ".css", ".sh"}
SECRET_MARKERS = ("secret", "token", "password", "passwd", "credential", "private_key", ".env", "id_rsa", "id_ed25519")
OUT_REL = Path("eira_probe/glass_viewport")
GITHUB_REL = Path("eira2_transport_bus/from_superprobe/glass")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _secretish(rel: str) -> bool:
    low = rel.casefold()
    return any(x in low for x in SECRET_MARKERS)


def _safe_root(root: str | Path) -> Path:
    p = Path(root).resolve()
    if not p.is_dir():
        raise RuntimeError("glass_root_missing:" + str(p))
    return p


def _file_portal(root: Path, p: Path) -> dict[str, Any]:
    rel = p.relative_to(root).as_posix()
    st = p.stat()
    row: dict[str, Any] = {
        "portal_id": "file:" + rel,
        "kind": "file",
        "path": rel,
        "bytes": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "mode": st.st_mode,
        "suffix": p.suffix.lower(),
        "redacted": _secretish(rel),
    }
    if row["redacted"]:
        return row
    raw = p.read_bytes()
    row["sha256"] = _sha(raw)
    if p.suffix.lower() in TEXT_SUFFIXES and len(raw) <= MAX_TEXT_BYTES:
        row["encoding"] = "utf-8-replace"
        row["source"] = raw.decode("utf-8", errors="replace")
    return row


def _process_portals() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return rows
    for p in sorted((x for x in proc.iterdir() if x.name.isdigit()), key=lambda x: int(x.name)):
        try:
            pid = int(p.name)
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
            if not cmd:
                cmd = (p / "comm").read_text(errors="replace").strip()
            rows.append({"portal_id": f"process:{pid}", "kind": "process", "pid": pid, "cmd": cmd[:4000]})
        except Exception:
            continue
    return rows


def snapshot(root: str | Path) -> dict[str, Any]:
    live = _safe_root(root)
    portals: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for p in live.rglob("*"):
        if len(portals) >= MAX_PORTALS:
            break
        try:
            if p.is_symlink():
                rel = p.relative_to(live).as_posix()
                portals.append({"portal_id": "symlink:" + rel, "kind": "symlink", "path": rel, "target": os.readlink(p)})
            elif p.is_file():
                portals.append(_file_portal(live, p))
        except Exception as exc:
            try:
                rel = p.relative_to(live).as_posix()
            except Exception:
                rel = str(p)
            errors.append({"path": rel, "error": f"{type(exc).__name__}:{exc}"[:500]})
    portals.extend(_process_portals())
    portals.sort(key=lambda x: str(x.get("portal_id") or ""))
    out = {
        "schema": SCHEMA,
        "version": VERSION,
        "ok": True,
        "mutates_observed_live": False,
        "root": str(live),
        "generated_unix": time.time(),
        "portal_count": len(portals),
        "portals": portals,
        "errors": errors[:1000],
        "security": {
            "secret_content_exported": False,
            "secret_path_metadata_visible": True,
            "note": "Glass is read-only. Secret-like paths are visible but their contents and hashes are not exported to GitHub.",
        },
    }
    raw = json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    out["snapshot_sha256"] = _sha(raw)
    return out


def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_local(root: str | Path, snap: dict[str, Any]) -> Path:
    live = _safe_root(root)
    out = live / OUT_REL / "latest.json"
    _atomic_json(out, snap)
    return out


def publish_github(root: str | Path, snap: dict[str, Any]) -> dict[str, Any]:
    live = _safe_root(root)
    repo = live / "eira_probe" / "transport_runtime_v6" / "repo"
    if not (repo / ".git").is_dir():
        raise RuntimeError("glass_transport_repo_missing")
    rel = GITHUB_REL / "latest.json"
    _atomic_json(repo / rel, snap)
    cmds = [
        ["git", "add", rel.as_posix()],
        ["git", "-c", "user.name=EIRA Glass", "-c", "user.email=eira-glass@localhost", "commit", "--quiet", "-m", "Update EIRA glass viewport"],
        ["git", "pull", "--rebase", "--quiet", "origin", "master"],
        ["git", "push", "--quiet", "origin", "master"],
    ]
    commit = None
    for i, cmd in enumerate(cmds):
        p = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True, timeout=300, check=False)
        if i == 1 and p.returncode != 0 and "nothing to commit" in (p.stdout + p.stderr).casefold():
            continue
        if p.returncode != 0:
            raise RuntimeError("glass_git_failed:" + " ".join(cmd[:2]) + ":" + (p.stdout + p.stderr)[-1200:])
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), text=True, capture_output=True, timeout=60, check=False)
    if p.returncode == 0:
        commit = p.stdout.strip()
    return {"ok": True, "path": rel.as_posix(), "commit": commit, "portal_count": snap.get("portal_count")}


def run_once(root: str | Path, *, publish: bool = True) -> dict[str, Any]:
    snap = snapshot(root)
    local_path = write_local(root, snap)
    result = {"schema": SCHEMA, "ok": True, "portal_count": snap["portal_count"], "snapshot_sha256": snap["snapshot_sha256"], "local_path": str(local_path), "published": False}
    if publish:
        result["github"] = publish_github(root, snap)
        result["published"] = True
    return result


def run_forever(root: str | Path, interval: float = DEFAULT_INTERVAL) -> None:
    interval = max(5.0, float(interval))
    live = _safe_root(root)
    state = live / OUT_REL / "service.json"
    while True:
        started = time.time()
        try:
            result = run_once(live, publish=True)
            _atomic_json(state, {"schema": SCHEMA, "ok": True, "pid": os.getpid(), "last": result, "updated_unix": time.time()})
        except Exception as exc:
            _atomic_json(state, {"schema": SCHEMA, "ok": False, "pid": os.getpid(), "error": f"{type(exc).__name__}:{exc}"[:3000], "updated_unix": time.time()})
        elapsed = time.time() - started
        time.sleep(max(1.0, interval - elapsed))


def status(root: str | Path) -> dict[str, Any]:
    live = _safe_root(root)
    p = live / OUT_REL / "service.json"
    if not p.is_file():
        return {"schema": SCHEMA, "ok": False, "active": False, "reason": "no_service_receipt"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": SCHEMA, "ok": False, "active": False, "reason": f"service_receipt_invalid:{type(exc).__name__}:{exc}"}
    data["active"] = bool(data.get("pid")) and (time.time() - float(data.get("updated_unix") or 0) < DEFAULT_INTERVAL * 4)
    return data


def ask(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    root = payload.get("root") or Path.cwd()
    mode = str(payload.get("mode") or "status").casefold()
    if mode == "snapshot":
        return run_once(root, publish=bool(payload.get("publish", True)))
    if mode == "status":
        return status(root)
    raise RuntimeError("unsupported_mode:" + mode)


def capabilities() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "extension": "eira.glass.viewport",
        "read_only_observation": True,
        "logical_portals": "one-per-visible-file-plus-runtime-process",
        "max_portals": MAX_PORTALS,
        "github_viewport": (GITHUB_REL / "latest.json").as_posix(),
        "write_authority": "snapshot-output-only",
        "live_application_write": False,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = ap.parse_args()
    if args.once:
        print(json.dumps(run_once(args.root, publish=not args.no_publish), sort_keys=True))
    else:
        run_forever(args.root, args.interval)
