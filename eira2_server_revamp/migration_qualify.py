#!/usr/bin/env python3
"""Isolated qualification for migrate.py. Never touches Easystore LIVE."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIGRATE = ROOT / "migrate.py"


def run(*args: str, expect: int = 0) -> tuple[subprocess.CompletedProcess[str], dict]:
    cp = subprocess.run([sys.executable, str(MIGRATE), *args], capture_output=True, text=True, timeout=30)
    if cp.returncode != expect:
        raise AssertionError(f"expected rc={expect}, got {cp.returncode}\nstdout={cp.stdout}\nstderr={cp.stderr}")
    text = cp.stdout if cp.returncode == 0 else cp.stderr
    payload = json.loads(text)
    return cp, payload


def main() -> int:
    checks: list[str] = []

    def ok(name: str) -> None:
        checks.append(name)
        print(f"PASS {name}")

    with tempfile.TemporaryDirectory(prefix="eira2_migration_qual_") as td:
        live = Path(td) / "LIVE"
        target = live / "eira2_server_revamp"
        live.mkdir()

        _, dry = run("--live-root", str(live), "--target", str(target))
        assert dry["ok"] and dry["mode"] == "dry-run" and not dry["cutover"]
        assert not target.exists()
        migrations = live / ".eira2_server_migrations"
        assert not migrations.exists() or not list(migrations.glob("stage-*"))
        ok("dry_run_no_cutover_no_stage_leak")

        target.mkdir()
        (target / "OLD_SERVER_MARKER").write_text("old", encoding="utf-8")
        _, committed = run("--live-root", str(live), "--target", str(target), "--commit")
        assert committed["ok"] and committed["cutover"] and committed["rollback_ready"]
        assert (target / "server.py").is_file()
        assert (target / "doctor.py").is_file()
        assert (target / "hardening.py").is_file()
        assert (target / "qualify.py").is_file()
        assert (target / "static/index.html").is_file()
        assert (target / "static/reference.css").is_file()
        assert (target / "package_manifest.json").is_file()
        backup = Path(committed["backup"])
        assert (backup / "OLD_SERVER_MARKER").read_text(encoding="utf-8") == "old"
        ok("atomic_cutover_and_backup")

        manifest = json.loads((target / "package_manifest.json").read_text(encoding="utf-8"))
        assert sorted(manifest["files"]) == sorted(committed["files"])
        ok("sealed_manifest_written")

        receipts = list(migrations.glob("receipt-*.json"))
        assert receipts
        receipt = json.loads(receipts[-1].read_text(encoding="utf-8"))
        assert receipt["cutover"] is True and receipt["target"] == str(target.resolve())
        ok("cutover_receipt_written")

        _, unsafe = run("--live-root", str(live), "--target", str(live), expect=1)
        assert "target_must_not_equal_live_root" in unsafe["error"]
        ok("live_root_overwrite_refused")

        outside = Path(td) / "outside"
        _, unsafe = run("--live-root", str(live), "--target", str(outside), expect=1)
        assert "target_must_be_inside_live_root" in unsafe["error"]
        ok("outside_target_refused")

        guarded = live / "guarded_server"
        (guarded / ".state").mkdir(parents=True)
        (guarded / ".state/server.pid").write_text(str(os.getpid()), encoding="utf-8")
        _, blocked = run("--live-root", str(live), "--target", str(guarded), "--commit", expect=1)
        assert "existing_server_process_alive" in blocked["error"]
        assert (guarded / ".state/server.pid").is_file()
        ok("running_owner_not_killed_or_overwritten")

    print(f"EIRA2_MIGRATION_QUALIFICATION=PASS checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
