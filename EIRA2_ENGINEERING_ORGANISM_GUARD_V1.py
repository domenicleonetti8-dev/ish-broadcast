#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/organism_guard.py"
NEW = r'''from __future__ import annotations

from typing import Any

SCHEMA = "eira2_engineering_organism_guard_v1"

PROTECTED_PRINCIPLES = (
    "repair_only_when_broken_or_materially_interfering",
    "preserve_working_behavior",
    "no_duplicate_or_overlapping_subsystems",
    "prefer_repair_or_replacement_over_parallel_paths",
    "one_canonical_owner_per_capability",
    "prove_failure_before_mutation",
    "prove_improvement_before_deployment",
    "stop_when_system_is_healthy",
    "move_to_next_verified_issue_instead_of_polishing_without_evidence",
)


def evaluate_issue(record: dict[str, Any]) -> dict[str, Any]:
    evidence = record.get("failure_evidence") or []
    interference = record.get("organism_interference") or []
    healthy = bool(record.get("healthy"))
    duplicate = bool(record.get("would_create_overlap"))
    regression = bool(record.get("would_regress_working_behavior"))
    canonical_conflict = bool(record.get("canonical_owner_conflict"))

    if healthy and not evidence and not interference:
        return {"decision": "CHILL_AND_MOVE_ON", "ok_to_build": False,
                "reason": "no_verified_defect_or_interference"}
    if not evidence and not interference:
        return {"decision": "INSPECT_MORE", "ok_to_build": False,
                "reason": "mutation_requires_verified_failure_or_organism_interference"}
    if duplicate or canonical_conflict:
        return {"decision": "REJECT_OVERLAP", "ok_to_build": False,
                "reason": "repair_must_not_create_parallel_or_competing_capability"}
    if regression:
        return {"decision": "REJECT_REGRESSION", "ok_to_build": False,
                "reason": "candidate_damages_verified_working_behavior"}
    return {"decision": "BUILD_REPAIR_OR_REPLACEMENT", "ok_to_build": True,
            "reason": "verified_problem_justifies_change"}


def evaluate_candidate(record: dict[str, Any]) -> dict[str, Any]:
    tests = record.get("tests") or []
    truth_ok = bool(record.get("truth_honesty_ok"))
    regression_ok = bool(record.get("regression_ok"))
    architecture_ok = bool(record.get("architecture_ok"))
    overlap_free = bool(record.get("overlap_free"))
    stronger_needed = bool(record.get("stronger_needed"))
    stronger_proven = bool(record.get("stronger_proven"))

    failures = []
    if not tests or any(t.get("ok") is not True for t in tests):
        failures.append("tests_not_proven")
    if not truth_ok:
        failures.append("truth_honesty_not_proven")
    if not regression_ok:
        failures.append("regression_safety_not_proven")
    if not architecture_ok:
        failures.append("organism_architecture_not_proven")
    if not overlap_free:
        failures.append("overlap_or_duplicate_path_detected")
    if stronger_needed and not stronger_proven:
        failures.append("required_hardening_not_proven")

    if failures:
        return {"decision": "REBUILD_OR_REJECT", "deploy": False, "failures": failures}
    return {"decision": "DEPLOY_THEN_STOP_TOUCHING_THIS_AREA", "deploy": True,
            "failures": [], "next_action": "work_on_next_verified_issue_or_idle"}


def self_test() -> dict[str, Any]:
    healthy = evaluate_issue({"healthy": True})
    broken = evaluate_issue({"failure_evidence": ["repro"]})
    overlap = evaluate_issue({"failure_evidence": ["repro"], "would_create_overlap": True})
    return {"schema": SCHEMA, "ok": (
        healthy["decision"] == "CHILL_AND_MOVE_ON" and
        broken["ok_to_build"] is True and
        overlap["decision"] == "REJECT_OVERLAP"
    ), "principles": list(PROTECTED_PRINCIPLES)}
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print("EIRA2_ENGINEERING_ORGANISM_GUARD_V1=PASS")
