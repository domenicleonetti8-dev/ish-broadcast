#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/hardening.py"
NEW = r'''from __future__ import annotations

import json
from typing import Any

SCHEMA = "eira2_engineering_worker_hardening_v2"

HARD_RULES = {
    "sandbox_only": True,
    "live_direct_write_allowed": False,
    "conversation_authority": False,
    "model_authority": False,
    "watcher_builder_required_for_live": True,
    "single_target_edit_default": True,
    "fail_closed_on_scope_violation": True,
    "fail_closed_on_missing_tool": True,
    "fail_closed_on_failed_review": True,
    "fail_closed_on_failed_tests": True,
    "fail_closed_on_ambiguous_destructive_action": True,
    "preserve_owner_approval_gates": True,
    "ollama_role": "candidate_backend_only",
    "opencode_role": "inspector_planner_reviewer",
    "aider_role": "sandbox_code_surgeon",
}

ESCALATE = {
    "ambiguous_destructive_intent",
    "conflicting_owner_directives",
    "irreversible_external_action",
    "missing_required_secret_or_credential",
    "explicit_owner_approval_required",
    "unrecoverable_verification_failure",
}


def evaluate(event: dict[str, Any] | None = None) -> dict[str, Any]:
    event = event or {}
    reason = str(event.get("reason") or "").strip()
    destructive = bool(event.get("destructive"))
    irreversible = bool(event.get("irreversible"))
    scope_violation = bool(event.get("scope_violation"))
    tests_ok = event.get("tests_ok", True)
    review_ok = event.get("review_ok", True)
    watcher_authorized = event.get("watcher_authorized", False)
    wants_live_deploy = bool(event.get("wants_live_deploy"))

    if scope_violation:
        return {"schema": SCHEMA, "decision": "REJECT", "reason": "scope_violation"}
    if tests_ok is False:
        return {"schema": SCHEMA, "decision": "RETRY_OR_REJECT", "reason": "tests_failed"}
    if review_ok is False:
        return {"schema": SCHEMA, "decision": "RETRY_OR_REJECT", "reason": "review_failed"}
    if destructive and not reason:
        return {"schema": SCHEMA, "decision": "ASK_OWNER", "reason": "ambiguous_destructive_intent"}
    if irreversible:
        return {"schema": SCHEMA, "decision": "ASK_OWNER", "reason": reason or "irreversible_external_action"}
    if reason in ESCALATE:
        return {"schema": SCHEMA, "decision": "ASK_OWNER", "reason": reason}
    if wants_live_deploy and not watcher_authorized:
        return {"schema": SCHEMA, "decision": "BLOCK", "reason": "watcher_authorization_required"}
    return {"schema": SCHEMA, "decision": "CONTINUE_AUTONOMOUSLY", "reason": None}


def self_test() -> dict[str, Any]:
    cases = [
        (evaluate({})["decision"] == "CONTINUE_AUTONOMOUSLY", "safe_default"),
        (evaluate({"scope_violation": True})["decision"] == "REJECT", "scope_fail_closed"),
        (evaluate({"tests_ok": False})["decision"] == "RETRY_OR_REJECT", "tests_fail_closed"),
        (evaluate({"review_ok": False})["decision"] == "RETRY_OR_REJECT", "review_fail_closed"),
        (evaluate({"destructive": True})["decision"] == "ASK_OWNER", "destructive_escalation"),
        (evaluate({"wants_live_deploy": True, "watcher_authorized": False})["decision"] == "BLOCK", "watcher_gate"),
        (evaluate({"wants_live_deploy": True, "watcher_authorized": True})["decision"] == "CONTINUE_AUTONOMOUSLY", "watcher_authorized"),
    ]
    return {"schema": SCHEMA, "ok": all(ok for ok, _ in cases), "checks": [{"name": name, "ok": ok} for ok, name in cases]}


def policy() -> dict[str, Any]:
    return {"schema": SCHEMA, "rules": HARD_RULES, "escalation_reasons": sorted(ESCALATE), "self_test": self_test()}


def ask(request: dict[str, Any] | str | None = None) -> dict[str, Any]:
    if isinstance(request, str):
        request = json.loads(request)
    request = request or {}
    if not isinstance(request, dict):
        raise TypeError("engineering_worker_hardening_request_must_be_dict")
    mode = str(request.get("mode") or "policy")
    if mode in {"policy", "status"}:
        return policy()
    if mode in {"evaluate", "gate"}:
        return evaluate(request.get("event") or request)
    if mode == "self_test":
        return self_test()
    raise RuntimeError("unsupported_engineering_worker_hardening_mode:" + mode)
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    import hashlib, json
    print(json.dumps({"ok": True, "target": TARGET, "bytes": len(NEW.encode()), "sha256": hashlib.sha256(NEW.encode()).hexdigest()}))
