#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/autonomy.py"
NEW = r'''from __future__ import annotations

import json
from typing import Any

SCHEMA = "eira2_engineering_worker_autonomy_v2"
DEFAULT_MODE = "autonomous"

HUMAN_ESCALATION_REASONS = {
    "ambiguous_destructive_intent",
    "conflicting_owner_directives",
    "unrecoverable_verification_failure",
    "missing_required_secret_or_credential",
    "irreversible_external_action",
    "explicit_owner_approval_required",
}

ROUTINE_AUTONOMOUS_ACTIONS = {
    "inspect_repository",
    "trace_failure",
    "form_plan",
    "create_sandbox",
    "edit_sandbox",
    "run_tests",
    "review_diff",
    "retry_failed_candidate",
    "reject_bad_candidate",
    "collect_evidence",
    "prepare_watcher_builder_handoff",
}


def policy() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "default_mode": DEFAULT_MODE,
        "human_input_default": False,
        "routine_decisions_require_human": False,
        "continue_without_prompt_when_safe": True,
        "retry_without_prompt_when_recoverable": True,
        "sandbox_first": True,
        "live_direct_write_allowed": False,
        "conversation_authority": False,
        "deployment_authority": "repair_watcher_ai -> canonical builder lane",
        "model_authority": False,
        "ollama_role": "candidate_backend_only",
        "opencode_role": "autonomous_inspector_planner_reviewer",
        "aider_role": "autonomous_sandbox_code_surgeon",
        "routine_autonomous_actions": sorted(ROUTINE_AUTONOMOUS_ACTIONS),
        "human_escalation_reasons": sorted(HUMAN_ESCALATION_REASONS),
    }


def human_input_required(event: dict[str, Any] | None = None) -> dict[str, Any]:
    event = event or {}
    reason = str(event.get("reason") or "").strip()
    required = reason in HUMAN_ESCALATION_REASONS
    return {
        "schema": SCHEMA,
        "required": required,
        "reason": reason if required else None,
        "continue_autonomously": not required,
    }


def ask(request: dict[str, Any] | str | None = None) -> dict[str, Any]:
    if isinstance(request, str):
        request = json.loads(request)
    request = request or {}
    if not isinstance(request, dict):
        raise TypeError("engineering_autonomy_request_must_be_dict")
    mode = str(request.get("mode") or "policy")
    if mode in {"policy", "status"}:
        return policy()
    if mode in {"human_input_required", "escalation_gate"}:
        return human_input_required(request.get("event") or request)
    raise RuntimeError("unsupported_engineering_autonomy_mode:" + mode)


def capabilities() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "capabilities": ["engineering_autonomy_policy", "engineering_human_escalation_gate"],
        "default_mode": DEFAULT_MODE,
        "human_input_default": False,
        "conversation_authority": False,
        "live_direct_write_allowed": False,
    }
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    import hashlib
    print(json.dumps({"ok": True, "target": TARGET, "bytes": len(NEW.encode()), "sha256": hashlib.sha256(NEW.encode()).hexdigest()}))
