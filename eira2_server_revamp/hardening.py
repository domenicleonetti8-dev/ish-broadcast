from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class VerifiedBridge:
    name: str
    configured: bool
    resolvable: bool
    verified: bool
    latency_ms: float | None
    detail: str

    @property
    def healthy(self) -> bool:
        return self.configured and self.resolvable and self.verified

    def payload(self) -> dict[str, Any]:
        out = asdict(self)
        out["healthy"] = self.healthy
        return out


def _resolve_executable(raw: str) -> tuple[bool, str]:
    if not raw:
        return False, "command_not_configured"
    try:
        argv = shlex.split(raw)
    except Exception as exc:
        return False, f"invalid_command:{type(exc).__name__}:{exc}"
    if not argv:
        return False, "empty_command"
    exe = argv[0]
    if os.path.sep in exe:
        ok = Path(exe).exists()
    else:
        from shutil import which
        ok = which(exe) is not None
    return ok, "resolved" if ok else f"executable_not_found:{exe}"


def verify_command_bridge(
    name: str,
    command: str,
    probe_command: str = "",
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float = 6.0,
) -> VerifiedBridge:
    configured = bool(command)
    resolvable, detail = _resolve_executable(command)
    if not configured or not resolvable:
        return VerifiedBridge(name, configured, resolvable, False, None, detail)

    # Verification is intentionally separate from simple executable resolution.
    # A side-effect-free probe command must be supplied for a bridge to become green.
    probe = probe_command.strip()
    if not probe:
        return VerifiedBridge(name, True, True, False, None, "probe_not_configured")
    probe_resolvable, probe_detail = _resolve_executable(probe)
    if not probe_resolvable:
        return VerifiedBridge(name, True, True, False, None, f"probe_{probe_detail}")

    started = time.perf_counter()
    try:
        cp = subprocess.run(
            shlex.split(probe),
            input=json.dumps({"probe": True, "source": "eira2_super_server"}),
            text=True,
            capture_output=True,
            cwd=str(cwd),
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return VerifiedBridge(name, True, True, False, round((time.perf_counter()-started)*1000, 2), "probe_timeout")
    latency = round((time.perf_counter() - started) * 1000, 2)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "probe_failed").strip()[-1200:]
        return VerifiedBridge(name, True, True, False, latency, f"probe_exit_{cp.returncode}:{err}")
    text = (cp.stdout or "").strip()
    if not text:
        return VerifiedBridge(name, True, True, False, latency, "probe_empty")
    try:
        payload = json.loads(text)
    except Exception:
        payload = {"ok": text.lower() in {"ok", "pass", "ready"}}
    ok = bool(payload.get("ok", True)) if isinstance(payload, dict) else True
    return VerifiedBridge(name, True, True, ok, latency, "verified" if ok else "probe_reported_not_ready")


def verify_json_source(name: str, raw: str, live_root: Path) -> VerifiedBridge:
    if not raw:
        return VerifiedBridge(name, False, False, False, None, "json_source_not_configured")
    path = Path(raw)
    if not path.is_absolute():
        path = live_root / path
    if not path.exists():
        return VerifiedBridge(name, True, False, False, None, f"missing:{path}")
    started = time.perf_counter()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, (dict, list)):
            raise ValueError("top_level_not_object_or_array")
    except Exception as exc:
        return VerifiedBridge(name, True, True, False, round((time.perf_counter()-started)*1000,2), f"invalid_json:{type(exc).__name__}:{exc}")
    return VerifiedBridge(name, True, True, True, round((time.perf_counter()-started)*1000,2), str(path))


def verify_ar_roots(roots: list[Path]) -> VerifiedBridge:
    configured = bool(roots)
    live = [p for p in roots if p.exists() and p.is_dir()]
    if not configured:
        return VerifiedBridge("apple_ar", False, False, False, None, "ar_roots_not_configured")
    if not live:
        return VerifiedBridge("apple_ar", True, False, False, None, "ar_roots_unavailable")
    count = 0
    for root in live:
        try:
            count += sum(1 for _ in root.rglob("*.usdz"))
        except Exception:
            pass
    return VerifiedBridge("apple_ar", True, True, count > 0, None, f"verified_usdz={count}" if count else "no_usdz_artifacts")


def verify_manifest(manifest_path: str, root: Path) -> dict[str, Any]:
    if not manifest_path:
        return {"configured": False, "healthy": False, "detail": "package_manifest_not_configured", "checked": 0}
    manifest = Path(manifest_path)
    if not manifest.is_absolute():
        manifest = root / manifest
    if not manifest.exists():
        return {"configured": True, "healthy": False, "detail": f"manifest_missing:{manifest}", "checked": 0}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        files = data.get("files", data) if isinstance(data, dict) else data
        if not isinstance(files, (list, dict)):
            raise ValueError("manifest_files_invalid")
        entries = files.items() if isinstance(files, dict) else ((e.get("path"), e) for e in files if isinstance(e, dict))
        checked = 0
        for rel, meta in entries:
            if not rel or not isinstance(meta, dict):
                raise ValueError("manifest_entry_invalid")
            p = (root / rel).resolve()
            if root != p and root not in p.parents:
                raise ValueError(f"manifest_path_escape:{rel}")
            if not p.is_file():
                raise FileNotFoundError(rel)
            if "size" in meta and p.stat().st_size != int(meta["size"]):
                raise ValueError(f"size_mismatch:{rel}")
            expected = str(meta.get("sha256", "")).lower().strip()
            if expected:
                actual = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual != expected:
                    raise ValueError(f"sha256_mismatch:{rel}")
            checked += 1
        return {"configured": True, "healthy": True, "detail": "verified", "checked": checked, "manifest": str(manifest)}
    except Exception as exc:
        return {"configured": True, "healthy": False, "detail": f"{type(exc).__name__}:{exc}", "checked": 0, "manifest": str(manifest)}
