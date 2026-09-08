from __future__ import annotations

TARGET = "eira2/evidence/gutenberg_refresh.py"

NEW = r'''from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
DEFAULT_ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
DEFAULT_STATE = DEFAULT_ROOT / "eira_probe" / "universe_library" / "gutenberg_refresh_state.json"

POLICY = {
    "catalog_refresh_seconds": 24 * 60 * 60,
    "bulk_archive_refresh_seconds": 7 * 24 * 60 * 60,
    "extract_after_bulk_change": True,
    "source_is_not_fact": True,
    "failure_backoff_seconds": 6 * 60 * 60,
    "max_consecutive_failures_before_hold": 8,
}

class GutenbergRefreshError(RuntimeError):
    pass


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _due(last_success: float | int | None, interval: int, now: float) -> bool:
    if not last_success:
        return True
    return now - float(last_success) >= int(interval)


class GutenbergRefreshScheduler:
    """Schedules Project Gutenberg refreshes without granting Gutenberg truth authority."""

    def __init__(
        self,
        state_path: str | Path = DEFAULT_STATE,
        *,
        catalog_runner: Callable[[], dict[str, Any]] | None = None,
        bulk_runner: Callable[[], dict[str, Any]] | None = None,
        extract_runner: Callable[[], dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.state_path = Path(state_path)
        self.clock = clock
        self._catalog_runner = catalog_runner
        self._bulk_runner = bulk_runner
        self._extract_runner = extract_runner

    def _default_runners(self):
        if self._catalog_runner and self._bulk_runner and self._extract_runner:
            return self._catalog_runner, self._bulk_runner, self._extract_runner
        from eira2.evidence.universe_public_library import PublicLibraryVault
        vault = PublicLibraryVault()
        return (
            vault.ingest_gutenberg_catalog,
            vault.download_gutenberg_full_text_archive,
            vault.extract_gutenberg_full_text_archive,
        )

    def status(self) -> dict[str, Any]:
        state = _load(self.state_path)
        now = self.clock()
        failures = int(state.get("consecutive_failures", 0) or 0)
        hold = failures >= POLICY["max_consecutive_failures_before_hold"]
        return {
            "schema": "eira2_gutenberg_refresh_status_v1",
            "schema_version": SCHEMA_VERSION,
            "state_path": str(self.state_path),
            "catalog_due": _due(state.get("catalog_last_success"), POLICY["catalog_refresh_seconds"], now),
            "bulk_due": _due(state.get("bulk_last_success"), POLICY["bulk_archive_refresh_seconds"], now),
            "consecutive_failures": failures,
            "held_for_repeated_failure": hold,
            "source_is_not_fact": True,
            "policy": dict(POLICY),
            "state": state,
        }

    def _record_success(self, state: dict[str, Any], key: str, result: dict[str, Any], now: float) -> None:
        state[f"{key}_last_success"] = now
        state[f"{key}_last_result"] = result
        state["consecutive_failures"] = 0
        state["last_error"] = ""
        state["updated_unix"] = now
        _atomic_json(self.state_path, state)

    def _record_failure(self, state: dict[str, Any], key: str, exc: Exception, now: float) -> None:
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0) or 0) + 1
        state["last_error"] = f"{type(exc).__name__}:{exc}"[:2000]
        state["last_failed_operation"] = key
        state["last_failure_unix"] = now
        state["updated_unix"] = now
        _atomic_json(self.state_path, state)

    def run_due(self, *, force_catalog: bool = False, force_bulk: bool = False) -> dict[str, Any]:
        now = self.clock()
        state = _load(self.state_path)
        failures = int(state.get("consecutive_failures", 0) or 0)
        if failures >= POLICY["max_consecutive_failures_before_hold"]:
            return {
                "ok": False,
                "status": "HELD_REPEATED_FAILURE",
                "consecutive_failures": failures,
                "source_is_not_fact": True,
            }
        last_failure = float(state.get("last_failure_unix", 0) or 0)
        if last_failure and failures and now - last_failure < POLICY["failure_backoff_seconds"]:
            return {
                "ok": True,
                "status": "BACKOFF",
                "retry_after_seconds": int(POLICY["failure_backoff_seconds"] - (now - last_failure)),
                "source_is_not_fact": True,
            }

        catalog_runner, bulk_runner, extract_runner = self._default_runners()
        operations: list[dict[str, Any]] = []

        if force_catalog or _due(state.get("catalog_last_success"), POLICY["catalog_refresh_seconds"], now):
            try:
                result = dict(catalog_runner())
                self._record_success(state, "catalog", result, now)
                operations.append({"operation": "catalog", "ok": True, "result": result})
            except Exception as exc:
                self._record_failure(state, "catalog", exc, now)
                return {"ok": False, "status": "CATALOG_FAILED", "operations": operations, "error": f"{type(exc).__name__}:{exc}", "source_is_not_fact": True}

        if force_bulk or _due(state.get("bulk_last_success"), POLICY["bulk_archive_refresh_seconds"], now):
            try:
                before = state.get("bulk_last_result") or {}
                result = dict(bulk_runner())
                self._record_success(state, "bulk", result, now)
                operations.append({"operation": "bulk", "ok": True, "result": result})
                old_sha = (((before or {}).get("download") or {}).get("sha256"))
                new_sha = (((result or {}).get("download") or {}).get("sha256"))
                changed = bool(new_sha) and new_sha != old_sha
                if POLICY["extract_after_bulk_change"] and changed:
                    extracted = dict(extract_runner())
                    state = _load(self.state_path)
                    state["extract_last_success"] = now
                    state["extract_last_result"] = extracted
                    state["updated_unix"] = now
                    _atomic_json(self.state_path, state)
                    operations.append({"operation": "extract", "ok": True, "result": extracted})
            except Exception as exc:
                state = _load(self.state_path)
                self._record_failure(state, "bulk", exc, now)
                return {"ok": False, "status": "BULK_FAILED", "operations": operations, "error": f"{type(exc).__name__}:{exc}", "source_is_not_fact": True}

        return {
            "ok": True,
            "status": "REFRESH_COMPLETE" if operations else "NOT_DUE",
            "operations": operations,
            "source_is_not_fact": True,
            "policy": dict(POLICY),
        }


def self_test_25x2() -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    for round_no in (1, 2):
        with tempfile.TemporaryDirectory(prefix=f"eira_gutenberg_refresh_r{round_no}_") as td:
            state_path = Path(td) / "state.json"
            calls = {"catalog": 0, "bulk": 0, "extract": 0}
            now = [1_000_000.0]
            def clock(): return now[0]
            def catalog(): calls["catalog"] += 1; return {"ok": True, "inserted": 10, "updated": 2}
            def bulk(): calls["bulk"] += 1; return {"ok": True, "download": {"sha256": f"sha{calls['bulk']}"}}
            def extract(): calls["extract"] += 1; return {"ok": True, "extracted_files": 3}
            s = GutenbergRefreshScheduler(state_path, catalog_runner=catalog, bulk_runner=bulk, extract_runner=extract, clock=clock)
            st0 = s.status()
            checks += [
                (f"r{round_no}_01_schema", st0["schema_version"] == 1),
                (f"r{round_no}_02_daily_policy", POLICY["catalog_refresh_seconds"] == 86400),
                (f"r{round_no}_03_weekly_policy", POLICY["bulk_archive_refresh_seconds"] == 604800),
                (f"r{round_no}_04_source_not_fact", st0["source_is_not_fact"] is True),
                (f"r{round_no}_05_catalog_due_initial", st0["catalog_due"] is True),
                (f"r{round_no}_06_bulk_due_initial", st0["bulk_due"] is True),
            ]
            first = s.run_due()
            checks += [
                (f"r{round_no}_07_first_ok", first["ok"] is True),
                (f"r{round_no}_08_catalog_called", calls["catalog"] == 1),
                (f"r{round_no}_09_bulk_called", calls["bulk"] == 1),
                (f"r{round_no}_10_extract_called_on_change", calls["extract"] == 1),
                (f"r{round_no}_11_state_exists", state_path.exists()),
                (f"r{round_no}_12_catalog_success_recorded", bool(_load(state_path).get("catalog_last_success"))),
                (f"r{round_no}_13_bulk_success_recorded", bool(_load(state_path).get("bulk_last_success"))),
                (f"r{round_no}_14_extract_success_recorded", bool(_load(state_path).get("extract_last_success"))),
            ]
            second = s.run_due()
            checks += [
                (f"r{round_no}_15_not_due", second["status"] == "NOT_DUE"),
                (f"r{round_no}_16_no_extra_catalog", calls["catalog"] == 1),
                (f"r{round_no}_17_no_extra_bulk", calls["bulk"] == 1),
            ]
            now[0] += 86401
            daily = s.run_due()
            checks += [
                (f"r{round_no}_18_daily_catalog_runs", calls["catalog"] == 2),
                (f"r{round_no}_19_weekly_bulk_not_yet", calls["bulk"] == 1),
                (f"r{round_no}_20_daily_status_ok", daily["ok"] is True),
            ]
            now[0] += 6 * 86400
            weekly = s.run_due()
            checks += [
                (f"r{round_no}_21_weekly_bulk_runs", calls["bulk"] == 2),
                (f"r{round_no}_22_weekly_extract_runs_changed", calls["extract"] == 2),
                (f"r{round_no}_23_weekly_status_ok", weekly["ok"] is True),
            ]
            forced = s.run_due(force_catalog=True)
            checks += [
                (f"r{round_no}_24_force_catalog", calls["catalog"] == 4),
                (f"r{round_no}_25_force_preserves_truth_boundary", forced["source_is_not_fact"] is True),
            ]
    failed = [n for n, ok in checks if not ok]
    return {"schema": "eira2_gutenberg_refresh_qualification_v1", "distinct_tests": 25, "rounds": 2, "clean_passes": sum(1 for _,ok in checks if ok), "total": len(checks), "failed": failed, "pass": len(checks) == 50 and not failed}
'''

if __name__ == "__main__":
    ns = {"__name__": "eira2_gutenberg_refresh_payload"}
    exec(compile(NEW, TARGET, "exec"), ns, ns)
    result = ns["self_test_25x2"]()
    print(__import__("json").dumps(result, indent=2, sort_keys=True))
    if not result.get("pass"):
        raise SystemExit(1)
