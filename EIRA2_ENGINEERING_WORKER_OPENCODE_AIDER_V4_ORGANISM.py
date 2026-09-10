#!/usr/bin/env python3
from __future__ import annotations

TARGET = "extensions/engineering_worker_ai/plugin.py"
NEW = r'''from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = "eira2_engineering_worker_opencode_aider_v4_organism"
EXTENSION_ID = "eira.engineering.worker"
DEFAULT_TIMEOUT = 1800
DEFAULT_OPENCODE_MODEL = "ollama/qwen2.5-coder:3b"
DEFAULT_AIDER_MODEL = "ollama_chat/qwen2.5-coder:3b"
PROTECTED_GATES = {
    "truth_honesty_gate", "evidence_log", "watcher_authorization",
    "canonical_builder", "rollback", "owner_authority",
}
ESCALATE = {
    "ambiguous_destructive_intent", "conflicting_owner_directives",
    "irreversible_external_action", "missing_required_secret_or_credential",
    "explicit_owner_approval_required", "unrecoverable_verification_failure",
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


def _resolve_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    candidates = {
        "aider": [home / ".local/bin/aider"],
        "opencode": [home / ".opencode/bin/opencode", home / ".local/bin/opencode", home / "bin/opencode"],
    }.get(name, [])
    for p in candidates:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    raise RuntimeError(name + "_not_installed_or_not_executable")


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


def _copy_snapshot(root: Path, dst: Path) -> None:
    for rel in _tracked(root):
        src = root / rel
        if src.is_file():
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
    for argv in (["git","init","-q"], ["git","config","user.name","EIRA Engineering Sandbox"],
                 ["git","config","user.email","eira-engineering@localhost"], ["git","add","-A"],
                 ["git","commit","-qm","sandbox baseline"]):
        r = _run(list(argv), dst, 120)
        if r["returncode"] != 0:
            raise RuntimeError("sandbox_git_setup_failed:" + r["stderr"][-1200:])


def _workspace(root: Path) -> dict[str, Path]:
    root = _git_root(root)
    session = Path(tempfile.mkdtemp(prefix="eira_engineering_", dir="/tmp"))
    opencode_box = session / "opencode"
    aider_box = session / "aider"
    review_box = session / "review"
    shared = session / "collaboration"
    for p in (opencode_box, aider_box, review_box, shared):
        p.mkdir(parents=True, exist_ok=True)
    _copy_snapshot(root, opencode_box)
    _copy_snapshot(root, aider_box)
    return {"session": session, "opencode": opencode_box, "aider": aider_box, "review": review_box, "shared": shared}


def _inventory(base: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(base.rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        rel = p.relative_to(base).as_posix()
        out[rel] = _sha(p.read_bytes())
    return out


def _changes(before: dict[str,str], after: dict[str,str]) -> list[str]:
    return [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]


def _env() -> dict[str,str]:
    env = dict(os.environ)
    env["EIRA_ENGINEERING_SANDBOX"] = "1"
    env["EIRA_ENGINEERING_LIVE_WRITE"] = "0"
    env["AIDER_YES_ALWAYS"] = "true"
    env["AIDER_AUTO_COMMITS"] = "false"
    return env


def _append_exchange(shared: Path, role: str, phase: str, payload: str) -> None:
    row = {"unix": time.time(), "role": role, "phase": phase, "payload": payload}
    with (shared / "exchange.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _organism_issue_gate(request: dict[str, Any]) -> dict[str, Any]:
    evidence = request.get("failure_evidence") or []
    interference = request.get("organism_interference") or []
    if request.get("healthy") and not evidence and not interference:
        return {"decision":"CHILL_AND_MOVE_ON","ok_to_build":False,"reason":"healthy_no_verified_problem"}
    if not evidence and not interference:
        return {"decision":"INSPECT_MORE","ok_to_build":False,"reason":"verified_failure_or_interference_required"}
    if request.get("would_create_overlap") or request.get("canonical_owner_conflict"):
        return {"decision":"REJECT_OVERLAP","ok_to_build":False,"reason":"parallel_or_competing_capability"}
    if request.get("would_regress_working_behavior"):
        return {"decision":"REJECT_REGRESSION","ok_to_build":False,"reason":"working_behavior_must_be_preserved"}
    return {"decision":"BUILD_REPAIR_OR_REPLACEMENT","ok_to_build":True,"reason":"verified_problem"}


def _structural_scan(box: Path, changed: list[str]) -> dict[str, Any]:
    duplicate_basenames: dict[str,list[str]] = {}
    seen: dict[str,list[str]] = {}
    for p in box.rglob("*.py"):
        if ".git" in p.parts:
            continue
        seen.setdefault(p.name, []).append(p.relative_to(box).as_posix())
    for name, paths in seen.items():
        if len(paths) > 1 and any(x in changed for x in paths):
            duplicate_basenames[name] = paths
    suspicious = [p for p in changed if any(k in p.lower() for k in ("_new.", "_v2.", "_v3.", "duplicate", "parallel", "backup"))]
    protected_touched = [p for p in changed if any(k in p.lower() for k in ("watcher", "builder", "truth", "rollback", "owner"))]
    return {"duplicate_changed_basenames":duplicate_basenames, "suspicious_parallel_names":suspicious,
            "protected_paths_touched":protected_touched,
            "ok": not duplicate_basenames and not suspicious and not protected_touched}


def _tests(box: Path, changed: list[str], request: dict[str,Any]) -> list[dict[str,Any]]:
    tests: list[dict[str,Any]] = []
    diffcheck = _run(["git","diff","--check"], box, 120, _env())
    tests.append({"name":"git_diff_check","ok":diffcheck["returncode"]==0,"stderr":diffcheck["stderr"][-2000:]})
    for rel in [p for p in changed if p.endswith(".py") and (box/p).is_file()]:
        t = _run(["python3","-m","py_compile",rel], box, 120, _env())
        tests.append({"name":"py_compile:"+rel,"ok":t["returncode"]==0,"stderr":t["stderr"][-1600:]})
    verify = request.get("verification_argv")
    if not isinstance(verify, list) or not verify or not all(isinstance(x,str) and x for x in verify):
        tests.append({"name":"defect_reproduction_verification","ok":False,"stderr":"verification_argv_required"})
    else:
        t = _run(verify, box, int(request.get("test_timeout_seconds") or 600), _env())
        tests.append({"name":"defect_reproduction_verification","ok":t["returncode"]==0,"returncode":t["returncode"],
                      "stdout_tail":t["stdout"][-6000:],"stderr_tail":t["stderr"][-3000:]})
    for argv in request.get("test_matrix") or []:
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv):
            tests.append({"name":"invalid_test_matrix_entry","ok":False})
            continue
        t = _run(argv, box, int(request.get("test_timeout_seconds") or 600), _env())
        tests.append({"name":"requested:"+" ".join(argv),"ok":t["returncode"]==0,"returncode":t["returncode"],
                      "stdout_tail":t["stdout"][-6000:],"stderr_tail":t["stderr"][-3000:]})
    return tests


def _truth_gate(*, tests: list[dict[str,Any]], review_ok: bool, structural: dict[str,Any], changed: list[str], issue_gate: dict[str,Any]) -> dict[str,Any]:
    failures = []
    if not changed: failures.append("no_material_change")
    if not tests or any(t.get("ok") is not True for t in tests): failures.append("tests_not_proven")
    if not review_ok: failures.append("independent_review_not_proven")
    if not structural.get("ok"): failures.append("structural_overlap_or_protected_gate_risk")
    if issue_gate.get("ok_to_build") is not True: failures.append("repair_not_justified_by_verified_problem")
    return {"ok":not failures,"failures":failures,"evidence_complete":not failures}


def status(root: str | Path | None = None) -> dict[str,Any]:
    r = Path(root or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    return {"schema":SCHEMA,"extension_id":EXTENSION_ID,"root":str(r),
            "opencode":_resolve_binary("opencode"),"aider":_resolve_binary("aider"),
            "opencode_model":DEFAULT_OPENCODE_MODEL,"aider_model":DEFAULT_AIDER_MODEL,
            "personal_sandboxes":"/tmp only","peer_communication":True,"continuous_daemon_supported":True,
            "self_repair":True,"direct_live_write":False,"deployment_authority":"Watcher -> canonical Builder",
            "protected_gates":sorted(PROTECTED_GATES)}


def inspect(request: dict[str,Any]) -> dict[str,Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    objective = str(request.get("objective") or "inspect EIRA end to end for verified defects and organism interference").strip()
    ws = _workspace(root)
    before = _inventory(ws["opencode"])
    prompt = ("Inspect the whole EIRA snapshot as one organism. Find only reproducible defects or interference. "
              "Do not propose cosmetic churn, duplicate paths, or parallel authorities. Do not edit. Identify exact evidence, canonical owner, "
              "reproduction method, and whether the correct action is repair, replacement, or CHILL_AND_MOVE_ON.\n\nOBJECTIVE:\n"+objective)
    oc = _run([_resolve_binary("opencode"),"run","--model",request.get("opencode_model") or DEFAULT_OPENCODE_MODEL,prompt],
              ws["opencode"], int(request.get("timeout_seconds") or DEFAULT_TIMEOUT), _env())
    mutations = _changes(before,_inventory(ws["opencode"]))
    _append_exchange(ws["shared"],"opencode","inspection",oc["stdout"])
    return {"schema":SCHEMA,"mode":"inspect","ok":oc["returncode"]==0 and not mutations,
            "workspace":str(ws["session"]),"opencode":oc,"sandbox_mutations":mutations,"live_mutated":False}


def build(request: dict[str,Any]) -> dict[str,Any]:
    root = Path(request.get("root") or os.environ.get("EIRA_ROOT") or Path.cwd()).resolve()
    objective = str(request.get("objective") or "").strip()
    if not objective: raise RuntimeError("objective_required")
    reason = str(request.get("reason") or "").strip()
    if request.get("irreversible") or reason in ESCALATE:
        return {"schema":SCHEMA,"ok":False,"needs_owner_input":True,"reason":reason or "irreversible_external_action"}
    issue_gate = _organism_issue_gate(request)
    if issue_gate["ok_to_build"] is not True:
        return {"schema":SCHEMA,"ok":False,"needs_owner_input":False,"organism_issue_gate":issue_gate,"live_mutated":False}

    ws = _workspace(root)
    oc_before = _inventory(ws["opencode"])
    plan_prompt = ("You are OpenCode, EIRA engineering investigator. Treat EIRA as one organism. The problem is already evidence-gated. "
                   "Trace the canonical path end to end and produce a repair/replacement plan for Aider. Prefer replacing the broken canonical path; "
                   "do not add parallel systems, duplicate owners, cosmetic rewrites, or unnecessary hardening. Preserve working behavior and protected gates. "
                   "Do not edit.\n\nOBJECTIVE:\n"+objective+"\n\nFAILURE EVIDENCE:\n"+json.dumps(request.get("failure_evidence") or [])+
                   "\n\nORGANISM INTERFERENCE:\n"+json.dumps(request.get("organism_interference") or []))
    oc = _run([_resolve_binary("opencode"),"run","--model",request.get("opencode_model") or DEFAULT_OPENCODE_MODEL,plan_prompt],
              ws["opencode"],int(request.get("timeout_seconds") or DEFAULT_TIMEOUT),_env())
    if oc["returncode"] != 0: raise RuntimeError("opencode_plan_failed:"+oc["stderr"][-1800:])
    if _changes(oc_before,_inventory(ws["opencode"])): raise RuntimeError("opencode_plan_mutated_its_sandbox")
    _append_exchange(ws["shared"],"opencode","plan",oc["stdout"])

    baseline = _inventory(ws["aider"])
    plan_file = ws["shared"] / "opencode_plan.txt"
    plan_file.write_text(oc["stdout"],encoding="utf-8")
    aider_prompt = ("You are Aider, OpenCode's implementation peer. Work only in your personal disposable sandbox. Repair or replace only what the evidence proves broken. "
                    "No overlapping subsystem, no competing capability owner, no cosmetic churn. Preserve everything already working. Build the smallest complete end-to-end fix; "
                    "strengthen further only when tests prove it is needed. You may edit multiple files when the canonical repair truly requires it.\n\nOBJECTIVE:\n"+objective+
                    "\n\nOPENCODE PLAN:\n"+oc["stdout"][-24000:])
    ad = _run([_resolve_binary("aider"),"--yes-always","--no-auto-commits","--no-dirty-commits","--model",
               request.get("aider_model") or DEFAULT_AIDER_MODEL,"--message",aider_prompt],
              ws["aider"],int(request.get("timeout_seconds") or DEFAULT_TIMEOUT),_env())
    if ad["returncode"] != 0: raise RuntimeError("aider_build_failed:"+ad["stderr"][-2000:])
    changed = _changes(baseline,_inventory(ws["aider"]))
    _append_exchange(ws["shared"],"aider","implementation",ad["stdout"])
    if not changed: return {"schema":SCHEMA,"ok":False,"stage":"no_change","retryable":False,"live_mutated":False}

    structural = _structural_scan(ws["aider"],changed)
    tests = _tests(ws["aider"],changed,request)
    if any(t.get("ok") is not True for t in tests) or not structural["ok"]:
        return {"schema":SCHEMA,"ok":False,"stage":"qualification","retryable":True,"changed_paths":changed,
                "tests":tests,"structural_scan":structural,"live_mutated":False,"workspace":str(ws["session"])}

    shutil.copytree(ws["aider"],ws["review"],dirs_exist_ok=True,ignore=shutil.ignore_patterns(".git"))
    review_prompt = ("You are OpenCode performing an adversarial review of Aider's candidate as an organism-level repair. Do not edit. "
                     "Reject if the defect is not actually resolved, working behavior regresses, a duplicate/parallel capability appears, canonical ownership is split, "
                     "protected gates are weakened, evidence is missing, or the candidate keeps polishing after health is restored. End exactly REVIEW=PASS or REVIEW=FAIL. "
                     "\n\nOBJECTIVE:\n"+objective+"\n\nCHANGED PATHS:\n"+json.dumps(changed)+"\n\nTESTS:\n"+json.dumps(tests))
    review = _run([_resolve_binary("opencode"),"run","--model",request.get("opencode_model") or DEFAULT_OPENCODE_MODEL,review_prompt],
                  ws["review"],int(request.get("timeout_seconds") or DEFAULT_TIMEOUT),_env())
    review_ok = review["returncode"]==0 and "REVIEW=PASS" in review["stdout"] and "REVIEW=FAIL" not in review["stdout"]
    _append_exchange(ws["shared"],"opencode","adversarial_review",review["stdout"])
    gate = _truth_gate(tests=tests,review_ok=review_ok,structural=structural,changed=changed,issue_gate=issue_gate)
    if not gate["ok"]:
        return {"schema":SCHEMA,"ok":False,"stage":"truth_honesty_gate","retryable":True,"changed_paths":changed,
                "tests":tests,"structural_scan":structural,"review":review,"truth_honesty_gate":gate,
                "live_mutated":False,"workspace":str(ws["session"])}

    candidates = {}
    for rel in changed:
        p = ws["aider"]/rel
        candidates[rel] = {"exists":p.is_file(),"sha256":_sha(p.read_bytes()) if p.is_file() else None,
                           "content":p.read_text(errors="strict") if p.is_file() else None}
    return {"schema":SCHEMA,"mode":"build","ok":True,"objective":objective,"workspace":str(ws["session"]),
            "changed_paths":changed,"candidates":candidates,"tests":tests,"structural_scan":structural,
            "review_passed":True,"truth_honesty_gate":gate,"organism_issue_gate":issue_gate,
            "live_mutated":False,"requires_watcher_builder_deployment":True,"needs_owner_input":False,
            "next_action_after_verified_deploy":"CHILL_AND_MOVE_ON_TO_NEXT_VERIFIED_ISSUE",
            "peer_exchange":str(ws["shared"] / "exchange.jsonl")}


def continuous_cycle(request: dict[str,Any]) -> dict[str,Any]:
    mode = str(request.get("cycle_mode") or "inspect")
    return build(request) if mode in {"build","repair","self_repair"} else inspect(request)


def run_forever(request: dict[str,Any]) -> dict[str,Any]:
    interval = max(60,int(request.get("interval_seconds") or 300))
    max_cycles = int(request.get("max_cycles") or 0)
    cycle = 0
    last: dict[str,Any] = {}
    while max_cycles <= 0 or cycle < max_cycles:
        cycle += 1
        try:
            last = continuous_cycle(request)
        except Exception as exc:
            last = {"ok":False,"error":type(exc).__name__+":"+str(exc)}
        if last.get("needs_owner_input"):
            return {"schema":SCHEMA,"ok":False,"stopped_for_owner":True,"cycle":cycle,"last":last}
        time.sleep(interval)
    return {"schema":SCHEMA,"ok":True,"cycles":cycle,"last":last}


def self_test() -> dict[str,Any]:
    healthy = _organism_issue_gate({"healthy":True})
    broken = _organism_issue_gate({"failure_evidence":["repro"]})
    overlap = _organism_issue_gate({"failure_evidence":["repro"],"would_create_overlap":True})
    empty_tests_rejected = not _truth_gate(tests=[],review_ok=True,structural={"ok":True},changed=["x"],issue_gate=broken)["ok"]
    return {"schema":SCHEMA,"ok":healthy["decision"]=="CHILL_AND_MOVE_ON" and broken["ok_to_build"] and
            overlap["decision"]=="REJECT_OVERLAP" and empty_tests_rejected,
            "checks":{"healthy_chills":healthy["decision"]=="CHILL_AND_MOVE_ON","broken_builds":broken["ok_to_build"],
                      "overlap_rejected":overlap["decision"]=="REJECT_OVERLAP","empty_tests_rejected":empty_tests_rejected}}


def ask(request: dict[str,Any] | str) -> dict[str,Any]:
    if isinstance(request,str): request=json.loads(request)
    if not isinstance(request,dict): raise TypeError("engineering_worker_request_must_be_dict")
    mode=str(request.get("mode") or "status")
    if mode=="status": return status(request.get("root"))
    if mode=="inspect": return inspect(request)
    if mode in {"build","repair","self_repair"}: return build(request)
    if mode=="continuous_cycle": return continuous_cycle(request)
    if mode=="run_forever": return run_forever(request)
    if mode=="self_test": return self_test()
    raise RuntimeError("unsupported_engineering_worker_mode:"+mode)


def capabilities() -> dict[str,Any]:
    return {"extension_id":EXTENSION_ID,"schema":SCHEMA,
            "modes":["status","inspect","build","repair","self_repair","continuous_cycle","run_forever","self_test"],
            "architecture":"OpenCode personal sandbox -> collaboration journal -> Aider personal sandbox -> tests/structure -> OpenCode review sandbox",
            "discipline":"repair verified defects only; no overlap; preserve working behavior; stop when healthy",
            "live_deployment":"Watcher -> canonical Builder only after machine evidence and truth/honesty qualification"}
'''

if __name__ == "__main__":
    compile(NEW, TARGET, "exec")
    print("EIRA2_ENGINEERING_WORKER_V4_ORGANISM=PASS")
