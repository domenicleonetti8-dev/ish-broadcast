#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, os, time
from pathlib import Path

SCHEMA = "eira2_orin_live_viewport_v1"
TEXT_SUFFIXES = {".py", ".json", ".html", ".js", ".md", ".txt", ".toml", ".yaml", ".yml"}
SECRET_MARKERS = ("secret", "token", "password", "passwd", "credential", "private_key", ".env", "id_rsa")
ROOT_HINTS = ("extensions", "eira_probe", "tools", "eira2", "engine", "brain", "council", "routers", "voice", "memory")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def redacted_path(rel: str) -> bool:
    low = rel.casefold()
    return any(x in low for x in SECRET_MARKERS)


def proc_rows(limit: int = 256) -> list[dict]:
    rows = []
    proc = Path("/proc")
    if not proc.is_dir():
        return rows
    for p in sorted((x for x in proc.iterdir() if x.name.isdigit()), key=lambda x: int(x.name)):
        if len(rows) >= limit:
            break
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
            if not cmd:
                cmd = (p / "comm").read_text(errors="replace").strip()
            rows.append({"pid": int(p.name), "cmd": cmd[:1200]})
        except Exception:
            continue
    return rows


def recent_json(root: Path, relroot: str, limit: int = 20) -> list[dict]:
    base = root / relroot
    if not base.exists():
        return []
    rows = []
    try:
        files = sorted((p for p in base.rglob("*.json") if p.is_file()), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    except Exception:
        return []
    for p in files[:limit]:
        try:
            raw = p.read_bytes()
            rows.append({
                "path": p.relative_to(root).as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "mtime_ns": p.stat().st_mtime_ns,
            })
        except Exception:
            continue
    return rows


def main() -> int:
    root = Path.cwd().resolve()
    files = []
    dirs = 0
    total_bytes = 0
    suffix_counts: dict[str, int] = {}
    errors = []

    for p in root.rglob("*"):
        try:
            if p.is_symlink():
                continue
            if p.is_dir():
                dirs += 1
                continue
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            st = p.stat()
            total_bytes += st.st_size
            suffix = p.suffix.lower() or "<none>"
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
            row = {
                "path": rel,
                "bytes": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "suffix": suffix,
                "redacted": redacted_path(rel),
            }
            if not row["redacted"] and st.st_size <= 32 * 1024 * 1024:
                try:
                    row["sha256"] = sha256_file(p)
                except Exception as exc:
                    row["hash_error"] = f"{type(exc).__name__}:{exc}"[:300]
            files.append(row)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}:{exc}"[:500])

    files.sort(key=lambda x: x["path"])
    roots = {}
    for name in ROOT_HINTS:
        p = root / name
        roots[name] = {"exists": p.exists(), "is_dir": p.is_dir()}

    manifest = root / "eira2-package-manifest.json"
    manifest_info = {"exists": manifest.is_file()}
    if manifest.is_file():
        try:
            raw = manifest.read_bytes()
            manifest_info.update({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        except Exception as exc:
            manifest_info["error"] = f"{type(exc).__name__}:{exc}"[:500]

    out = {
        "schema": SCHEMA,
        "ok": True,
        "mutates_live": False,
        "generated_unix": time.time(),
        "root": str(root),
        "file_count": len(files),
        "dir_count": dirs,
        "total_bytes": total_bytes,
        "suffix_counts": dict(sorted(suffix_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "root_map": roots,
        "manifest": manifest_info,
        "processes": proc_rows(),
        "recent_probe_json": recent_json(root, "eira_probe", 40),
        "recent_transport_json": recent_json(root, "eira2_transport_bus", 40),
        "files": files,
        "errors": errors[:100],
        "security": {
            "content_redaction": True,
            "redacted_name_markers": list(SECRET_MARKERS),
            "note": "Paths and metadata remain visible; secret-like file contents and hashes are not exported.",
        },
    }
    print(json.dumps(out, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
