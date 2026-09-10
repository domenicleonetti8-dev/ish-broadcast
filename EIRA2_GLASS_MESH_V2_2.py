#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "eira2_glass_mesh_v2"
VERSION = "2.2.0"

DEFAULT_INTERVAL = 30.0
SCAN_BATCH = 192
SCAN_BUDGET_SECONDS = 4.0
MAX_PORTALS = 100_000
MAX_TEXT_BYTES = 512_000
MAX_HASH_BYTES = 4_000_000
MAX_SNAPSHOT_BYTES = 80_000_000
HASH_CHUNK = 1024 * 1024
MAX_BLIND_SPOTS = 5000

TEXT_SUFFIXES = {
    ".py", ".json", ".html", ".js", ".md", ".txt",
    ".toml", ".yaml", ".yml", ".css", ".sh",
}
SECRET_NAME_MARKERS = (
    "secret", "token", "password", "passwd", "credential",
    "private_key", ".env", "id_rsa", "id_ed25519",
)
SECRET_JSON_PATTERN = re.compile(
    r"""(?i)(["'](?:api[_-]?key|token|secret|password|passwd|authorization)["']\s*:\s*["'])([^"']*)(["'])"""
)
SECRET_ASSIGN_PATTERN = re.compile(
    r"""(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\s*=\s*(["']?)([^"'\s,;]+)(["']?)"""
)
SECRET_TOKEN_PATTERNS = (
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{12,})\b"),
    re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9_]{12,})\b"),
    re.compile(r"(?i)\b(Bearer\s+[A-Za-z0-9._~+/=-]{8,})\b"),
)

EXCLUDE_PREFIXES = (
    ".git/",
    "eira_probe/glass_viewport/",
    "eira_probe/glass_publisher_repo/",
    "eira_probe/transport_runtime_v6/repo/",
    "eira2_transport_bus/from_superprobe/glass/",
)

GITHUB_ROOT = Path("eira2_transport_bus/from_superprobe/glass")
GITHUB_HEARTBEAT = GITHUB_ROOT / "heartbeat.json"
GITHUB_LATEST = GITHUB_ROOT / "latest.json"
SERVICE_REL = Path("eira_probe/glass_viewport/service.json")
PUBLISH_REPO_REL = Path("eira_probe/glass_publisher_repo")
REPO_URL = "https://github.com/domenicleonetti8-dev/ish-broadcast.git"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_rel(value: str) -> str:
    s = str(value or "").replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")


def _excluded(rel: str) -> bool:
    r = _norm_rel(rel)
    return any(r == p.rstrip("/") or r.startswith(p) for p in EXCLUDE_PREFIXES)


def _secretish_path(rel: str) -> bool:
    low = _norm_rel(rel).casefold()
    parts = [part.casefold() for part in Path(low).parts]
    return any(marker in low or marker in parts for marker in SECRET_NAME_MARKERS)


def _redact_text(text: str) -> tuple[str, int]:
    out = text
    count = 0

    def repl_json(match):
        nonlocal count
        count += 1
        return match.group(1) + "<REDACTED>" + match.group(3)

    def repl_assign(match):
        nonlocal count
        count += 1
        return match.group(1) + "=" + match.group(2) + "<REDACTED>" + match.group(4)

    out = SECRET_JSON_PATTERN.sub(repl_json, out)
    out = SECRET_ASSIGN_PATTERN.sub(repl_assign, out)

    for pattern in SECRET_TOKEN_PATTERNS:
        def repl_token(match):
            nonlocal count
            count += 1
            return "<REDACTED>"
        out = pattern.sub(repl_token, out)

    return out, count


def _safe_root(root: str | Path) -> Path:
    path = Path(root).resolve()
    if not path.is_dir():
        raise RuntimeError("glass_root_missing:" + str(path))
    return path


def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _service_write(root: Path, *, phase: str, ok: bool = True, error: str | None = None,
                   cycle: int = 0, scan_complete: bool = False,
                   portal_count: int = 0, blind_spot_count: int = 0) -> None:
    payload = {
        "schema": SCHEMA,
        "version": VERSION,
        "ok": bool(ok),
        "active": True,
        "pid": os.getpid(),
        "phase": phase,
        "cycle": int(cycle),
        "scan_complete": bool(scan_complete),
        "portal_count": int(portal_count),
        "blind_spot_count": int(blind_spot_count),
        "interval": DEFAULT_INTERVAL,
        "updated_unix": time.time(),
    }
    if error:
        payload["error"] = str(error)[:3000]
    _atomic_json(root / SERVICE_REL, payload)


def _heartbeat(root: Path, *, phase: str, cycle: int,
               scan_complete: bool, portal_count: int,
               blind_spot_count: int) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "ok": True,
        "active": True,
        "pid": os.getpid(),
        "phase": phase,
        "cycle": int(cycle),
        "root": str(root),
        "scan_complete": bool(scan_complete),
        "portal_count": int(portal_count),
        "blind_spot_count": int(blind_spot_count),
        "updated_unix": time.time(),
    }


def _symbol_portals(rel: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    blind: list[dict[str, str]] = []
    if not rel.endswith(".py"):
        return rows, blind
    try:
        tree = ast.parse(text)
    except Exception as exc:
        blind.append({
            "path": rel,
            "kind": "python_parse",
            "reason": f"{type(exc).__name__}:{exc}"[:500],
        })
        return rows, blind

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            rows.append({
                "portal_id": f"{kind}:{rel}:{node.name}:{getattr(node, 'lineno', 0)}",
                "kind": kind,
                "path": rel,
                "name": node.name,
                "lineno": getattr(node, "lineno", None),
                "end_lineno": getattr(node, "end_lineno", None),
            })
    return rows, blind


def _file_portal(root: Path, path: Path, cache: dict[str, Any]) -> tuple[
    dict[str, Any], list[dict[str, Any]], list[dict[str, str]], dict[str, Any]
]:
    rel = path.relative_to(root).as_posix()
    st = path.stat()
    meta = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "inode": st.st_ino}
    row: dict[str, Any] = {
        "portal_id": "file:" + rel,
        "kind": "file",
        "path": rel,
        "bytes": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "mode": st.st_mode,
        "suffix": path.suffix.lower(),
        "redacted": _secretish_path(rel),
    }
    extra: list[dict[str, Any]] = []
    blind: list[dict[str, str]] = []
    old = cache.get(rel) if isinstance(cache.get(rel), dict) else None

    if row["redacted"]:
        row["content_status"] = "redacted_secret_path"
        blind.append({
            "path": rel,
            "kind": "redacted_secret_path",
            "reason": "content intentionally not exported",
        })
        return row, extra, blind, {"meta": meta, "portal": row, "symbols": []}

    if old and old.get("meta") == meta and isinstance(old.get("portal"), dict):
        reused = dict(old["portal"])
        reused["reused"] = True
        return reused, list(old.get("symbols") or []), [], old

    if st.st_size <= MAX_HASH_BYTES:
        try:
            row["sha256"] = _sha_file(path)
            row["hash_status"] = "complete"
        except Exception as exc:
            row["hash_status"] = "error"
            blind.append({
                "path": rel,
                "kind": "hash_error",
                "reason": f"{type(exc).__name__}:{exc}"[:500],
            })
    else:
        row["hash_status"] = "deferred_large_file"
        blind.append({
            "path": rel,
            "kind": "large_file_hash_deferred",
            "reason": f"hash deferred above {MAX_HASH_BYTES} bytes to protect LIVE I/O",
        })

    if path.suffix.lower() in TEXT_SUFFIXES:
        if st.st_size > MAX_TEXT_BYTES:
            row["content_status"] = "oversized_text"
            blind.append({
                "path": rel,
                "kind": "oversized_text",
                "reason": f"content omitted above {MAX_TEXT_BYTES} bytes",
            })
        else:
            try:
                text = path.read_bytes().decode("utf-8", errors="replace")
                text, redactions = _redact_text(text)
                row["source"] = text
                row["encoding"] = "utf-8-replace"
                row["content_redactions"] = redactions
                row["content_status"] = "visible_redacted"
                symbols, errors = _symbol_portals(rel, text)
                extra.extend(symbols)
                blind.extend(errors)
            except Exception as exc:
                row["content_status"] = "read_error"
                blind.append({
                    "path": rel,
                    "kind": "content_read_error",
                    "reason": f"{type(exc).__name__}:{exc}"[:500],
                })
    else:
        row["content_status"] = "binary_metadata_only"
        blind.append({
            "path": rel,
            "kind": "binary_content",
            "reason": "metadata visible; binary body intentionally not exported",
        })

    return row, extra, blind, {"meta": meta, "portal": row, "symbols": extra}


def _iter_entries(root: Path) -> Iterator[Path]:
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as scan:
                entries = list(scan)
        except Exception:
            yield directory
            continue

        entries.sort(key=lambda entry: entry.name, reverse=True)
        for entry in entries:
            path = Path(entry.path)
            rel = path.relative_to(root).as_posix()
            if _excluded(rel):
                continue
            yield path
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
            except OSError:
                continue


def _process_portals(limit: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    blind: list[dict[str, str]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return rows, [{"path": "/proc", "kind": "proc_unavailable", "reason": "process filesystem unavailable"}]

    for path in sorted((p for p in proc.iterdir() if p.name.isdigit()), key=lambda p: int(p.name)):
        if len(rows) >= limit:
            blind.append({
                "path": "/proc",
                "kind": "process_portal_limit",
                "reason": "process portal budget exhausted",
            })
            break
        try:
            pid = int(path.name)
            cmd = (path / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
            if not cmd:
                cmd = (path / "comm").read_text(errors="replace").strip()
            cmd, redactions = _redact_text(cmd)
            rows.append({
                "portal_id": f"process:{pid}",
                "kind": "process",
                "pid": pid,
                "cmd": cmd[:4000],
                "content_redactions": redactions,
            })
        except Exception as exc:
            blind.append({
                "path": str(path),
                "kind": "process_read_error",
                "reason": f"{type(exc).__name__}:{exc}"[:300],
            })
    return rows, blind


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)


def _publisher_repo(root: Path) -> Path:
    repo = root / PUBLISH_REPO_REL
    if not (repo / ".git").is_dir():
        if repo.exists():
            shutil.rmtree(repo)
        proc = subprocess.run(
            ["git", "clone", "--quiet", REPO_URL, str(repo)],
            text=True, capture_output=True, timeout=600, check=False,
        )
        if proc.returncode:
            raise RuntimeError("glass_clone_failed:" + (proc.stdout + proc.stderr)[-1200:])

    for cmd in (
        ["git", "fetch", "--quiet", "origin", "master"],
        ["git", "checkout", "--quiet", "master"],
        ["git", "reset", "--hard", "origin/master"],
        ["git", "clean", "-fd"],
    ):
        proc = _run(cmd, repo, 600)
        if proc.returncode:
            raise RuntimeError("glass_sync_failed:" + (proc.stdout + proc.stderr)[-1200:])
    return repo


def _publish_files(root: Path, files: dict[Path, dict[str, Any]], message: str) -> dict[str, Any]:
    repo = _publisher_repo(root)
    changed: list[str] = []

    for rel, obj in files.items():
        raw = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()
        dest = repo / rel
        old = dest.read_bytes() if dest.is_file() else None
        if old == raw:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=dest.name + ".tmp.", dir=str(dest.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, dest)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        changed.append(rel.as_posix())

    if not changed:
        head = _run(["git", "rev-parse", "HEAD"], repo, 60)
        return {"ok": True, "changed": False, "commit": head.stdout.strip() if head.returncode == 0 else None}

    proc = _run(["git", "add", "--"] + changed, repo, 120)
    if proc.returncode:
        raise RuntimeError("glass_git_add_failed:" + (proc.stdout + proc.stderr)[-1000:])

    proc = _run([
        "git", "-c", "user.name=EIRA Glass", "-c", "user.email=eira-glass@localhost",
        "commit", "--quiet", "-m", message
    ], repo, 120)
    if proc.returncode:
        raise RuntimeError("glass_git_commit_failed:" + (proc.stdout + proc.stderr)[-1200:])

    proc = _run(["git", "pull", "--rebase", "--quiet", "origin", "master"], repo, 600)
    if proc.returncode:
        raise RuntimeError("glass_git_rebase_failed:" + (proc.stdout + proc.stderr)[-1500:])

    proc = _run(["git", "push", "--quiet", "origin", "master"], repo, 600)
    if proc.returncode:
        raise RuntimeError("glass_git_push_failed:" + (proc.stdout + proc.stderr)[-1500:])

    head = _run(["git", "rev-parse", "HEAD"], repo, 60)
    return {
        "ok": True,
        "changed": True,
        "commit": head.stdout.strip() if head.returncode == 0 else None,
        "paths": changed,
    }


def publish_heartbeat(root: str | Path, heartbeat: dict[str, Any]) -> dict[str, Any]:
    live = _safe_root(root)
    return _publish_files(live, {GITHUB_HEARTBEAT: heartbeat}, "Update EIRA Glass heartbeat")


def publish_viewport(root: str | Path, heartbeat: dict[str, Any], viewport: dict[str, Any]) -> dict[str, Any]:
    live = _safe_root(root)
    raw = json.dumps(viewport, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError(f"glass_snapshot_too_large:{len(raw)}")
    return _publish_files(
        live,
        {GITHUB_HEARTBEAT: heartbeat, GITHUB_LATEST: viewport},
        "Update EIRA Glass viewport",
    )


class GlassScan:
    def __init__(self, root: str | Path):
        self.root = _safe_root(root)
        self.cache: dict[str, Any] = {}
        self.portals: dict[str, dict[str, Any]] = {}
        self.blind_by_key: dict[str, dict[str, str]] = {}
        self.scanner: Iterator[Path] = _iter_entries(self.root)
        self.seen: set[str] = set()
        self.scan_complete = False
        self.generation = 1
        self.files_seen = 0
        self.entries_seen = 0
        self.excluded_entries = 0

    def _blind(self, item: dict[str, str]) -> None:
        key = f"{item.get('kind','')}:{item.get('path','')}"
        self.blind_by_key[key] = item

    def _add_portal(self, row: dict[str, Any]) -> None:
        portal_id = str(row.get("portal_id") or "")
        if not portal_id:
            return
        if portal_id not in self.portals and len(self.portals) >= MAX_PORTALS:
            self._blind({
                "path": ".",
                "kind": "portal_limit",
                "reason": f"portal budget {MAX_PORTALS} exhausted",
            })
            return
        self.portals[portal_id] = row
        self.seen.add(portal_id)

    def slice(self, max_entries: int = SCAN_BATCH,
              budget_seconds: float = SCAN_BUDGET_SECONDS) -> dict[str, Any]:
        started = time.monotonic()
        processed = 0

        while processed < max_entries and (time.monotonic() - started) < budget_seconds:
            try:
                path = next(self.scanner)
            except StopIteration:
                self.scan_complete = True
                stale = [portal_id for portal_id in self.portals if portal_id.startswith(("file:", "dir:", "symlink:", "function:", "class:")) and portal_id not in self.seen]
                for portal_id in stale:
                    self.portals.pop(portal_id, None)
                self.generation += 1
                self.scanner = _iter_entries(self.root)
                self.seen = set()
                break

            processed += 1
            self.entries_seen += 1
            try:
                rel = path.relative_to(self.root).as_posix()
                if _excluded(rel):
                    self.excluded_entries += 1
                    continue
                if path.is_symlink():
                    self._add_portal({
                        "portal_id": "symlink:" + rel,
                        "kind": "symlink",
                        "path": rel,
                        "target": os.readlink(path),
                    })
                    continue
                if path.is_dir():
                    self._add_portal({
                        "portal_id": "dir:" + rel,
                        "kind": "directory",
                        "path": rel,
                    })
                    continue
                if not path.is_file():
                    self._blind({
                        "path": rel,
                        "kind": "unsupported_fs_object",
                        "reason": "not regular file/dir/symlink",
                    })
                    continue

                self.files_seen += 1
                row, symbols, blind, new_cache = _file_portal(self.root, path, self.cache)
                self.cache[rel] = new_cache
                self._add_portal(row)
                for symbol in symbols:
                    self._add_portal(symbol)
                for item in blind:
                    self._blind(item)

            except Exception as exc:
                self._blind({
                    "path": str(path),
                    "kind": "scan_error",
                    "reason": f"{type(exc).__name__}:{exc}"[:500],
                })

        return {
            "processed": processed,
            "elapsed": time.monotonic() - started,
            "scan_complete": self.scan_complete,
            "portal_count": len(self.portals),
            "blind_spot_count": len(self.blind_by_key),
        }

    def viewport(self) -> dict[str, Any]:
        portals = list(self.portals.values())

        process_rows, process_blind = _process_portals(max(0, MAX_PORTALS - len(portals)))
        portals.extend(process_rows)
        for item in process_blind:
            self._blind(item)

        portals = portals[:MAX_PORTALS]
        portals.sort(key=lambda row: str(row.get("portal_id") or ""))
        blind = sorted(
            self.blind_by_key.values(),
            key=lambda row: (row.get("kind", ""), row.get("path", "")),
        )

        coverage = {
            "root": str(self.root),
            "generation": self.generation,
            "scan_complete": self.scan_complete,
            "portal_count": len(portals),
            "files_seen": self.files_seen,
            "entries_seen": self.entries_seen,
            "excluded_entries": self.excluded_entries,
            "blind_spot_count": len(blind),
            "blind_spots": blind[:MAX_BLIND_SPOTS],
            "blind_spots_truncated": len(blind) > MAX_BLIND_SPOTS,
            "explicit_noncoverage": [
                "kernel memory not exposed as files",
                "hardware state not exposed by mounted LIVE or /proc",
                "remote services not mirrored into LIVE",
                "secret values intentionally redacted",
                "large file hashes deferred to protect LIVE I/O",
                "binary bodies intentionally not exported",
            ],
        }
        out = {
            "schema": SCHEMA,
            "version": VERSION,
            "ok": True,
            "mutates_observed_live": False,
            "generated_unix": time.time(),
            "coverage": coverage,
            "portals": portals,
        }
        raw = json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise RuntimeError(f"glass_snapshot_too_large:{len(raw)}")
        out["snapshot_sha256"] = _sha_bytes(raw)
        return out


def run_forever(root: str | Path, interval: float = DEFAULT_INTERVAL) -> None:
    live = _safe_root(root)
    interval = max(10.0, float(interval))
    scan = GlassScan(live)
    cycle = 0

    _service_write(
        live, phase="starting", cycle=cycle,
        scan_complete=False, portal_count=0, blind_spot_count=0,
    )

    try:
        hb = _heartbeat(
            live, phase="starting", cycle=cycle,
            scan_complete=False, portal_count=0, blind_spot_count=0,
        )
        publish_heartbeat(live, hb)
    except Exception as exc:
        _service_write(
            live, phase="publisher_start_error", ok=False, error=f"{type(exc).__name__}:{exc}",
            cycle=cycle, scan_complete=False, portal_count=0, blind_spot_count=0,
        )

    while True:
        cycle += 1
        started = time.monotonic()
        phase = "deepening" if not scan.scan_complete else "observing"

        try:
            progress = scan.slice()
            viewport = scan.viewport()
            hb = _heartbeat(
                live,
                phase=phase,
                cycle=cycle,
                scan_complete=bool(progress["scan_complete"]),
                portal_count=int(progress["portal_count"]),
                blind_spot_count=int(progress["blind_spot_count"]),
            )

            _service_write(
                live,
                phase=phase,
                cycle=cycle,
                scan_complete=bool(progress["scan_complete"]),
                portal_count=int(progress["portal_count"]),
                blind_spot_count=int(progress["blind_spot_count"]),
            )

            publish_viewport(live, hb, viewport)

        except Exception as exc:
            _service_write(
                live,
                phase="cycle_error",
                ok=False,
                error=f"{type(exc).__name__}:{exc}",
                cycle=cycle,
                scan_complete=scan.scan_complete,
                portal_count=len(scan.portals),
                blind_spot_count=len(scan.blind_by_key),
            )

        time.sleep(max(1.0, interval - (time.monotonic() - started)))


def status(root: str | Path) -> dict[str, Any]:
    live = _safe_root(root)
    path = live / SERVICE_REL
    if not path.is_file():
        return {"schema": SCHEMA, "version": VERSION, "ok": False, "active": False, "reason": "no_service_receipt"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema": SCHEMA,
            "version": VERSION,
            "ok": False,
            "active": False,
            "reason": f"service_receipt_invalid:{type(exc).__name__}:{exc}",
        }

    interval = max(10.0, float(data.get("interval") or DEFAULT_INTERVAL))
    fresh = time.time() - float(data.get("updated_unix") or 0) < interval * 4
    pid = int(data.get("pid") or 0)
    alive = pid > 0 and Path(f"/proc/{pid}").exists()
    data["active"] = bool(fresh and alive)
    return data


def capabilities() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "extension": "eira.glass.viewport",
        "read_only_observation": True,
        "live_application_write": False,
        "logical_portals": "files+dirs+python-symbols+processes",
        "blind_spot_accounting": True,
        "secret_value_redaction": True,
        "max_portals": MAX_PORTALS,
        "publisher_checkout": "dedicated",
        "heartbeat_first": True,
        "bounded_scan": True,
        "scan_batch": SCAN_BATCH,
        "scan_budget_seconds": SCAN_BUDGET_SECONDS,
        "max_hash_bytes": MAX_HASH_BYTES,
    }


def ask(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    root = _safe_root(payload.get("root") or Path.cwd())
    mode = str(payload.get("mode") or "status").casefold()

    if mode == "status":
        return status(root)
    if mode == "capabilities":
        return capabilities()
    if mode == "snapshot":
        scan = GlassScan(root)
        progress = scan.slice(
            max_entries=max(1, int(payload.get("max_entries") or SCAN_BATCH)),
            budget_seconds=max(0.1, float(payload.get("budget_seconds") or SCAN_BUDGET_SECONDS)),
        )
        viewport = scan.viewport()
        return {
            "schema": SCHEMA,
            "version": VERSION,
            "ok": True,
            "progress": progress,
            "viewport": viewport,
        }
    raise RuntimeError("unsupported_mode:" + mode)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(status(args.root), sort_keys=True))
    else:
        run_forever(args.root, args.interval)
