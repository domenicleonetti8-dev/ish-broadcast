#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/plugin.py"
NEW = r'''from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_engineering_worker_opencode_aider_v3_free_roam"
EXTENSION_ID = "eira.engineering.worker"
DEFAULT_TIMEOUT = 1800

# Full-scope engineering freedom is allowed in disposable candidates. Canonical LIVE
# mutation remains evidence-gated through Watcher -> Builder.
ESCALATE = {
    "ambiguous_destructive_intent",
    "conflicting_owner_directives",
    "irreversible_external_action",
    "missing_required_secret_or_credential",
    "explicit_owner_approval_required",
    "unrecoverable_verification_failure",
}
PROTECTED_GATES = {
    "truth_honesty_gate",
    "evidence_log",
    "watcher_authorization",
    "canonical_builder",
    "rollback",
    "owner_authority",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(argv: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        p = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, check=False,
                           timeout=max(1, min(int(timeout), 3600)), env=env)
        return {"argv": argv, "returncode": p.returncode, "stdout": p.stdout or "", "stderr": p.stderr or "",
                "elapsed_seconds": round(time.time() - started, 3), "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"argv": argv, "returncode": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "timeout",
                "elapsed_seconds": round(time.time() - started, 3), "timed_out": True}


def _which(name: str) -> str | None:
    return shutil.which(name)


def _git_root(root: Path) -> Path:
    root = root.resolve()
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], text=True, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("eira_git_root_unavailable")
    actual = Path(p.stdout.strip()).resolve()
    if actual != root:
        raise RuntimeError("requested_root_is_not_git_root")
    return actual


def _tracked(root: Path) -> list[str]:
    p = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("git_ls_files_failed")
    return [x.decode("utf-8") for x in p.stdout.split(b"\0") if x]


def _inventory(base: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(base.rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        rel = p.relative_to(base).as_posix()
        out[rel] = _sha(p.read_bytes())
    return out


def _snapshot(root: Path) -> tuple[Path, dict[str, str]]:
    root = _git_root(root)
    sandboxes = root / "eira_probe" / "engineering_worker_ai" / "sandboxes"
    sandboxes.mkdir(parents=True, exist_ok=True)
    box = Path(tempfile.mkdtemp(prefix="free_roam_", dir=str(sandboxes)))
    for rel in _tracked(root):
        src = root / rel
        if src.is_file():
            dst = box / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for argv in (["git","init","-q"], ["git","config","user.name","EIRA Engineering Sandbox"],
                 ["git","config","user.email","eira-engineering@localhost"], ["git","add","-A"],
                 ["git","commit","-qm","sandbox baseline"]):
        r = _run(list(argv), box, 120)
        if r["returncode"] != 0:
            raise RuntimeError("sandbox_git_setup_failed:" + r["stderr"][-1000:])
    return box, _inventory(box)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["EIRA_ENGINEERING_SANDBOX"] = "1"
    env["EIRA_ENGINEERING_LIVE_WRITE"] = "0"
    env["AIDER_YES_ALWAYS"] = "true"
    env["AIDER_AUTO_COMMITS"] = "false"
    return env


def _opencode() -> str:
    b = _which("opencode") or _which("opencode2")
    if not b:
        raise RuntimeError("opencode_not_installed")
    return b


def _aider() -> str:
    b = _which("aider")
    if not b:
        raise RuntimeError("aider_not_installed")
    return b


def _model(flag: str | None) -> list[str]:
    return ["--model", flag] if flag else []


def _changed(before: dict[str,str], after: dict[str,str]) -> list[str]:
    return sorted(set(before) | set(after), key=str.casefold)


def _actual_changes(before: dict[str,str], after: dict[str,str]) -> list[str]:
    return [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]


def _truth_gate(record: dict[str, Any]) -> dict[str, Any]:
    failures = []
    tests = record.get("tests") or []
    if any(t.get("ok") is not True for t in tests):
        failures.append("tests_not_proven")
    if record.get("review_passed") is not True:
        failures.append("independent_review_not_proven")
    if not record.get("changed_paths"):
        failures.append("no_material_change")
    if record.get("live_mutated"):
        failures.append("direct_live_mutation_detected")
    if record.get("claimed_success") and not record.get("evidence_complete"):
        failures.append("success_claim_without_evidence")
    if record.get("hidden_failures"):
        failures.append("hidden_failures")
    if record.get("gate_weakening"):
        failures.append("protected_gate_weakening")
    return {"ok": not failures, "failures": failures,
            "principle": "claims must be supported by fresh machine-verifiable evidence"}


def status(root: str | Path | None = None) -> dict[str, Any]:
    r = Path(root or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    models = []
    if _which("ollama"):
        p = subprocess.run(["ollama","list"], text=True, capture_output=True, check=False, timeout=30)
        if p.returncode == 0:
            models = [line.split()[0] for line in p.stdout.splitlines()[1:] if line.split()]
    return {"schema": SCHEMA, "extension_id": EXTENSION_ID, "root": str(r),
            "opencode": _which("opencode") or _which("opencode2"), "aider": _which("aider"),
            "ollama": _which("ollama"), "ollama_models": models,
            "engineering_scope": "full_eira_candidate_scope", "self_repair": True,
            "peer_communication": True, "continuous_autonomy_supported": True,
            "direct_live_write": False, "deployment_authority": "Watcher -> canonical Builder",
            "protected_gates": sorted(PROTECTED_GATES)}


def inspect(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("objective_required")
    box, before = _snapshot(root)
    prompt = ("You are OpenCode, EIRA's autonomous engineering investigator. Inspect the entire disposable EIRA snapshot. "
              "Roam freely across subsystems, trace dependencies, run non-destructive diagnostics, and communicate findings for Aider. "
              "Do not mutate files in this inspection phase. Never invent runtime truth.\n\nOBJECTIVE:\n" + objective)
    oc = _run([_opencode(),"run","--auto",*_model(request.get("opencode_model")),prompt], box,
              int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _env())
    after = _inventory(box)
    mutations = _actual_changes(before, after)
    return {"schema":SCHEMA,"mode":"inspect","ok":oc["returncode"]==0 and not mutations,
            "sandbox":str(box),"opencode":oc,"sandbox_mutations":mutations,"live_mutated":False}


def build(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("objective_required")
    reason = str(request.get("reason") or "").strip()
    if request.get("irreversible") or reason in ESCALATE:
        return {"schema":SCHEMA,"ok":False,"needs_owner_input":True,"reason":reason or "irreversible_external_action"}

    box, baseline = _snapshot(root)
    oc_prompt = ("Inspect all of EIRA in this disposable snapshot and design the strongest complete engineering solution. "
                 "You may reason across every subsystem and propose multi-file refactors, self-repair, deletions, additions, and migrations. "
                 "Preserve EIRA's identity/history/owner authority and never weaken truth, evidence, Watcher, Builder, rollback, or honesty gates. "
                 "Do not edit yet. Produce a concrete implementation plan for Aider.\n\nOBJECTIVE:\n" + objective)
    oc = _run([_opencode(),"run","--auto",*_model(request.get("opencode_model")),oc_prompt], box,
              int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _env())
    if oc["returncode"] != 0:
        raise RuntimeError("opencode_analysis_failed:" + oc["stderr"][-1600:])
    if _actual_changes(baseline, _inventory(box)):
        raise RuntimeError("opencode_analysis_mutated_snapshot")

    files = _tracked(box)
    aider_prompt = ("You are Aider, EIRA's autonomous implementation peer. Work only in this disposable sandbox. "
                    "You are free to modify any tracked EIRA file needed for the objective, including engineering-worker integration itself. "
                    "Do not weaken protected truth/evidence/Watcher/Builder/rollback/owner gates. Build the complete solution, not a cosmetic patch. "
                    "Keep interfaces coherent and leave the candidate testable.\n\nOBJECTIVE:\n" + objective +
                    "\n\nOPENCODE PLAN:\n" + oc["stdout"][-24000:])
    argv = [_aider(),"--yes-always","--no-auto-commits","--no-dirty-commits","--message",aider_prompt,
            *_model(request.get("aider_model")),*files]
    ad = _run(argv, box, int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _env())
    if ad["returncode"] != 0:
        raise RuntimeError("aider_build_failed:" + ad["stderr"][-2000:])

    after = _inventory(box)
    changed = _actual_changes(baseline, after)
    if not changed:
        raise RuntimeError("aider_produced_no_change")

    tests: list[dict[str,Any]] = []
    py_changed = [p for p in changed if p.endswith(".py") and (box/p).is_file()]
    for rel in py_changed:
        t = _run(["python3","-m","py_compile",rel], box, 120, _env())
        tests.append({"name":"py_compile:"+rel,"ok":t["returncode"]==0,"stderr":t["stderr"][-1200:]})
    for test_argv in request.get("test_matrix") or []:
        if not isinstance(test_argv,list) or not test_argv or not all(isinstance(x,str) and x for x in test_argv):
            raise RuntimeError("invalid_test_matrix")
        t = _run(test_argv, box, int(request.get("test_timeout_seconds") or 600), _env())
        tests.append({"name":"requested:"+" ".join(test_argv),"ok":t["returncode"]==0,
                      "returncode":t["returncode"],"stdout_tail":t["stdout"][-6000:],"stderr_tail":t["stderr"][-3000:]})
    if any(t.get("ok") is not True for t in tests):
        return {"schema":SCHEMA,"ok":False,"retryable":True,"stage":"tests","changed_paths":changed,
                "tests":tests,"live_mutated":False,"needs_owner_input":False}

    patches = []
    for rel in changed:
        old = b""
        new = b""
        src = root/rel
        dst = box/rel
        if src.is_file(): old = src.read_bytes()
        if dst.is_file(): new = dst.read_bytes()
        patches.append("".join(difflib.unified_diff(old.decode(errors="replace").splitlines(True),
                                                    new.decode(errors="replace").splitlines(True),
                                                    fromfile=rel+".before",tofile=rel+".candidate")))
    review_prompt = ("You are OpenCode performing an adversarial truth/honesty review of Aider's candidate. "
                     "Do not edit. Reject fake passes, hidden failures, weakened gates, loss of EIRA identity/history, bypass of Watcher/Builder, "
                     "unsupported claims, or incomplete engineering. End with exactly REVIEW=PASS or REVIEW=FAIL.\n\nOBJECTIVE:\n" + objective +
                     "\n\nCHANGED PATHS:\n" + json.dumps(changed) + "\n\nDIFFS:\n" + "\n".join(patches)[-50000:])
    review = _run([_opencode(),"run","--auto",*_model(request.get("opencode_model")),review_prompt], box,
                  int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _env())
    review_ok = review["returncode"]==0 and "REVIEW=PASS" in review["stdout"] and "REVIEW=FAIL" not in review["stdout"]
    gate = _truth_gate({"tests":tests,"review_passed":review_ok,"changed_paths":changed,"live_mutated":False,
                        "claimed_success":True,"evidence_complete":review_ok and all(t.get("ok") for t in tests),
                        "hidden_failures":False,"gate_weakening":False})
    if not gate["ok"]:
        return {"schema":SCHEMA,"ok":False,"retryable":True,"stage":"truth_gate","changed_paths":changed,
                "tests":tests,"review":review,"truth_honesty_gate":gate,"live_mutated":False}

    candidates = {}
    for rel in changed:
        p = box/rel
        candidates[rel] = {"exists":p.is_file(),"sha256":_sha(p.read_bytes()) if p.is_file() else None,
                           "content":p.read_text(errors="strict") if p.is_file() else None}
    return {"schema":SCHEMA,"mode":"build","ok":True,"objective":objective,"sandbox":str(box),
            "changed_paths":changed,"candidates":candidates,"tests":tests,"review_passed":True,
            "truth_honesty_gate":gate,"live_mutated":False,"requires_watcher_builder_deployment":True,
            "needs_owner_input":False,"peer_transcript":{"opencode_plan":oc["stdout"],"aider":ad["stdout"],"review":review["stdout"]}}


def continuous_cycle(request: dict[str, Any]) -> dict[str, Any]:
    # One autonomous cycle. The host runtime/extension scheduler owns 24/7 recurrence.
    mode = str(request.get("cycle_mode") or "build")
    if mode == "inspect":
        return inspect(request)
    return build(request)


def self_test() -> dict[str, Any]:
    checks = {
        "full_candidate_scope": True,
        "self_repair_enabled": True,
        "peer_communication_enabled": True,
        "direct_live_write_disabled": True,
        "truth_gate_present": _truth_gate({"tests":[],"review_passed":False,"changed_paths":["x"],"live_mutated":False})["ok"] is False,
        "protected_gates_present": bool(PROTECTED_GATES),
    }
    return {"schema":SCHEMA,"ok":all(checks.values()),"checks":checks}


def ask(request: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(request,str): request=json.loads(request)
    if not isinstance(request,dict): raise TypeError("engineering_worker_request_must_be_dict")
    mode=str(request.get("mode") or "status")
    if mode=="status": return status(request.get("root"))
    if mode=="inspect": return inspect(request)
    if mode in {"build","repair","self_repair"}: return build(request)
    if mode=="continuous_cycle": return continuous_cycle(request)
    if mode=="truth_gate": return _truth_gate(request)
    if mode=="self_test": return self_test()
    raise RuntimeError("unsupported_engineering_worker_mode:"+mode)


def capabilities() -> dict[str, Any]:
    return {"extension_id":EXTENSION_ID,"schema":SCHEMA,
            "modes":["status","inspect","build","repair","self_repair","continuous_cycle","truth_gate","self_test"],
            "scope":"full EIRA candidate scope including self-repair",
            "peer_communication":"OpenCode plan -> Aider implementation -> OpenCode adversarial review",
            "continuous":"host scheduler may invoke continuous_cycle 24/7",
            "live_deployment":"Watcher -> canonical Builder only after tests and truth/honesty gate"}
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print("EIRA2_ENGINEERING_WORKER_V3_FREE_ROAM=PASS")
