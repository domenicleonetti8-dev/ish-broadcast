#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any

CORE_COMMIT = "f61240000d4fd3eb8ddab7ff6800c5555f501490"
CORE_PATH = "EIRA2_BLUEPRINT_DEPLOYMENT_LANE_V4.py"


def run(cmd: list[str], *, cwd: Path, timeout: int = 2400) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def request_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, Any]:
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=raw, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return int(r.status), parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return int(exc.code), parsed


def request_binary(url: str, payload: bytes, timeout: float) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return int(r.status), parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return int(exc.code), parsed


def live_acceptance(root: Path, port: int = 8782) -> dict[str, Any]:
    base = f"http://127.0.0.1:{port}"
    result: dict[str, Any] = {
        "schema": "eira2_live_http_acceptance_v1",
        "base_url": base,
        "tested_unix": time.time(),
    }

    try:
        status, body = request_json(
            base + "/v1/text",
            {"text": "Respond with a short greeting for this internal EIRA2 acceptance check.", "source": "acceptance_probe"},
            120.0,
        )
        payload = body.get("result") if isinstance(body, dict) else None
        answer = ""
        if isinstance(payload, dict):
            answer = str(payload.get("text") or payload.get("response") or "").strip()
        elif isinstance(body, dict):
            answer = str(body.get("text") or body.get("response") or body.get("reply") or "").strip()
        result["text"] = {
            "http_status": status,
            "not_501": status != 501,
            "response_present": bool(answer),
            "response_preview": answer[:240],
            "ok": status == 200 and bool(answer),
        }
    except Exception as exc:
        result["text"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:1200]}

    try:
        silence = b"\x00\x00" * 1600
        status, body = request_binary(
            base + "/v1/listen?sample_rate=16000&channels=1&sample_width=2",
            silence,
            60.0,
        )
        utterance = str(body.get("utterance") or body.get("text") or "").strip() if isinstance(body, dict) else ""
        result["listen"] = {
            "http_status": status,
            "not_501": status != 501,
            "route_reached": status != 501,
            "full_transcription_verified": status == 200 and bool(utterance),
            "body_preview": json.dumps(body, sort_keys=True)[:320] if isinstance(body, dict) else str(body)[:320],
        }
    except Exception as exc:
        result["listen"] = {
            "route_reached": False,
            "full_transcription_verified": False,
            "error": f"{type(exc).__name__}:{exc}"[:1200],
        }

    live_py = root / "eira2" / "live.py"
    voice_py = root / "eira2" / "delivery" / "voice.py"
    live_source = live_py.read_text(encoding="utf-8", errors="replace") if live_py.is_file() else ""
    voice_source = voice_py.read_text(encoding="utf-8", errors="replace") if voice_py.is_file() else ""
    result["voice_delivery"] = {
        "live_voice_enabled_declared": "voice_enabled=True" in live_source,
        "delivery_voice_module_present": voice_py.is_file(),
        "voice_sink_source_present": "sink_for_turn" in voice_source or "native" in voice_source or "Bluetooth" in voice_source,
        "flashcube_audio_observed": False,
        "note": "Physical Flashcube sound is not claimed without an observed audio event.",
    }
    result["runtime_acceptance_ok"] = bool(
        (result.get("text") or {}).get("ok") is True
        and (result.get("listen") or {}).get("route_reached") is True
    )
    return result


def publish_acceptance(repo: Path, packet_id: str, payload: dict[str, Any]) -> str:
    rel = Path("eira2_transport_bus/from_superprobe/acceptance") / f"{packet_id}.json"
    reset = run(["git", "reset", "--hard", "origin/master"], cwd=repo, timeout=300)
    if reset.returncode:
        raise RuntimeError("acceptance_reset_failed:" + reset.stderr[-800:])
    dest = repo / rel
    atomic_json(dest, payload)
    add = run(["git", "add", rel.as_posix()], cwd=repo, timeout=120)
    if add.returncode:
        raise RuntimeError("acceptance_git_add_failed:" + add.stderr[-800:])
    diff = run(["git", "diff", "--cached", "--quiet"], cwd=repo, timeout=120)
    if diff.returncode == 0:
        return run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=120).stdout.strip()
    commit = run([
        "git", "-c", "user.name=EIRA Acceptance Transport",
        "-c", "user.email=eira-acceptance@localhost",
        "commit", "--quiet", "-m", f"Return EIRA2 acceptance {packet_id}",
    ], cwd=repo, timeout=120)
    if commit.returncode:
        raise RuntimeError("acceptance_commit_failed:" + commit.stderr[-800:])
    pull = run(["git", "pull", "--rebase", "--quiet", "origin", "master"], cwd=repo, timeout=300)
    if pull.returncode:
        raise RuntimeError("acceptance_rebase_failed:" + pull.stderr[-1000:])
    push = run(["git", "push", "--quiet", "origin", "master"], cwd=repo, timeout=300)
    if push.returncode:
        raise RuntimeError("acceptance_push_failed:" + push.stderr[-1000:])
    return run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=120).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--source-repo-root", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    repo = Path(args.source_repo_root).resolve()
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    packet_id = str(packet.get("packet_id") or "")
    receipt_path = root / "eira_probe" / "blueprint_receipts" / f"{packet_id}.lane_v4.json"

    core = Path("/tmp") / f"eira2_lane_v4_core_{os.getpid()}.py"
    show = subprocess.run(
        ["git", "-C", str(repo), "show", f"{CORE_COMMIT}:{CORE_PATH}"],
        capture_output=True, timeout=120, check=False,
    )
    if show.returncode:
        print(json.dumps({"EIRA2_BLUEPRINT_DEPLOYMENT_V4": "FAIL", "error": "core_lane_fetch_failed"}), file=sys.stderr)
        return 2
    core.write_bytes(show.stdout)

    proc = run(
        [sys.executable, str(core), "--root", str(root), "--packet", str(Path(args.packet).resolve()), "--source-repo-root", str(repo)],
        cwd=root,
        timeout=3600,
    )
    try:
        core.unlink()
    except OSError:
        pass

    combo = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode or "EIRA2_BLUEPRINT_DEPLOYMENT_V4" not in combo or "PASS" not in combo:
        sys.stderr.write(proc.stderr or proc.stdout)
        return proc.returncode or 2

    acceptance = live_acceptance(root)
    acceptance_transport = {
        "schema": "eira2_live_acceptance_return_v1",
        "packet_id": packet_id,
        "completed_unix": time.time(),
        "package_and_superprobe_qualified": True,
        "live_http_acceptance": acceptance,
    }
    transport_commit = publish_acceptance(repo, packet_id, acceptance_transport)
    acceptance_transport["return_transport_commit"] = transport_commit

    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                receipt = value
        except Exception:
            receipt = {}
    receipt["live_http_acceptance"] = acceptance
    receipt["runtime_acceptance_separate_from_package_integrity"] = True
    receipt["runtime_acceptance_failure_does_not_rollback_valid_package"] = True
    atomic_json(receipt_path, receipt)

    print(json.dumps({
        "EIRA2_BLUEPRINT_DEPLOYMENT_V4": "PASS",
        "packet_id": packet_id,
        "package_and_superprobe_qualified": True,
        "live_http_acceptance": acceptance,
        "acceptance_return_transport_commit": transport_commit,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
