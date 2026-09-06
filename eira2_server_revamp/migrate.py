#!/usr/bin/env python3
"""Fail-closed transactional migration for the isolated EIRA 2 super server.

This migrates only the eira2_server_revamp package. It does not modify EIRA1,
conversation/core architecture, or unrelated LIVE files. Dry-run is the default.
A committed cutover requires --commit and an explicit --target path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REQUIRED = (
    "server.py", "doctor.py", "hardening.py", "qualify.py",
    "static/index.html", "static/reference.css",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def package_manifest(root: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for rel in REQUIRED:
        p = (root / rel).resolve()
        if root.resolve() not in p.parents and p != root.resolve():
            raise RuntimeError(f"source_path_escape:{rel}")
        if not p.is_file():
            raise RuntimeError(f"required_source_missing:{rel}")
        st = p.stat()
        files[rel] = {"size": st.st_size, "sha256": sha256(p)}
    return {"format": 1, "package": "eira2_server_revamp", "files": files}


def verify_tree(root: Path, manifest: dict[str, Any]) -> None:
    for rel, expected in manifest["files"].items():
        p = (root / rel).resolve()
        if root.resolve() not in p.parents and p != root.resolve():
            raise RuntimeError(f"verify_path_escape:{rel}")
        if not p.is_file():
            raise RuntimeError(f"verify_missing:{rel}")
        if p.stat().st_size != int(expected["size"]):
            raise RuntimeError(f"verify_size_mismatch:{rel}")
        if sha256(p) != expected["sha256"]:
            raise RuntimeError(f"verify_sha256_mismatch:{rel}")


def compile_python(root: Path) -> None:
    files = [root / x for x in ("server.py", "doctor.py", "hardening.py", "qualify.py")]
    cp = subprocess.run([sys.executable, "-m", "py_compile", *map(str, files)], capture_output=True, text=True)
    if cp.returncode:
        raise RuntimeError(f"python_compile_failed:{(cp.stderr or cp.stdout).strip()[-3000:]}")


def js_check(root: Path) -> None:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node_required_for_migration_js_check")
    html = (root / "static/index.html").read_text(encoding="utf-8")
    start = html.find("<script>")
    end = html.rfind("</script>")
    if start < 0 or end <= start:
        raise RuntimeError("inline_javascript_not_found")
    script = html[start + len("<script>"):end]
    cp = subprocess.run([node, "--check"], input=script, capture_output=True, text=True)
    if cp.returncode:
        raise RuntimeError(f"javascript_syntax_failed:{(cp.stderr or cp.stdout).strip()[-3000:]}")


def copy_package(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=False)
    for rel in REQUIRED:
        s = src / rel
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def refuse_live_owner(target: Path) -> None:
    # Migration never guesses whether another server is safe to kill.
    for candidate in (target / ".state/server.pid", target.parent / ".state/server.pid"):
        if not candidate.is_file():
            continue
        try:
            pid = int(candidate.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except Exception as exc:
            raise RuntimeError(f"cannot_validate_existing_server_owner:{candidate}:{exc}") from exc
        raise RuntimeError(f"existing_server_process_alive:{pid}:{candidate}")


def safe_target(target: Path, live_root: Path) -> None:
    target = target.resolve()
    live_root = live_root.resolve()
    if target == live_root:
        raise RuntimeError("target_must_not_equal_live_root")
    if live_root not in target.parents:
        raise RuntimeError(f"target_must_be_inside_live_root:{target}")
    if target.name in {"", ".", "..", "LIVE", "eira", "eira2"}:
        raise RuntimeError(f"unsafe_target_name:{target.name}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    src = HERE.resolve()
    live_root = Path(args.live_root).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()
    safe_target(target, live_root)
    if not live_root.is_dir():
        raise RuntimeError(f"live_root_missing:{live_root}")

    manifest = package_manifest(src)
    verify_tree(src, manifest)
    compile_python(src)
    js_check(src)
    refuse_live_owner(target)

    txn_root = live_root / ".eira2_server_migrations"
    txn_id = time.strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    stage = txn_root / f"stage-{txn_id}"
    backup = txn_root / f"backup-{txn_id}"
    receipt = txn_root / f"receipt-{txn_id}.json"

    copy_package(src, stage)
    verify_tree(stage, manifest)
    atomic_json(stage / "package_manifest.json", manifest)

    report: dict[str, Any] = {
        "ok": True,
        "mode": "commit" if args.commit else "dry-run",
        "transaction_id": txn_id,
        "source": str(src),
        "live_root": str(live_root),
        "target": str(target),
        "stage": str(stage),
        "backup": None,
        "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
        "files": sorted(manifest["files"]),
        "cutover": False,
        "rollback_ready": False,
    }

    if not args.commit:
        shutil.rmtree(stage)
        report["stage"] = None
        return report

    txn_root.mkdir(parents=True, exist_ok=True)
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
            report["backup"] = str(backup)
            report["rollback_ready"] = True
        os.replace(stage, target)
        verify_tree(target, manifest)
        atomic_json(target / "package_manifest.json", manifest)
        report["cutover"] = True
        atomic_json(receipt, report)
        return report
    except Exception:
        # Roll back atomically wherever possible. Never leave an unverified target active.
        try:
            if target.exists():
                failed = txn_root / f"failed-{txn_id}"
                os.replace(target, failed)
            if backup.exists():
                os.replace(backup, target)
        finally:
            raise


def main() -> int:
    p = argparse.ArgumentParser(description="Transactional EIRA 2 server package migration")
    p.add_argument("--live-root", required=True, help="Existing Easystore LIVE root")
    p.add_argument("--target", required=True, help="Explicit server package destination inside LIVE")
    p.add_argument("--commit", action="store_true", help="Perform atomic cutover; default is dry-run")
    args = p.parse_args()
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
