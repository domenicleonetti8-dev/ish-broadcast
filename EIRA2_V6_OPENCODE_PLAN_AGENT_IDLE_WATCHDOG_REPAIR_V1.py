#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib
import shutil

TARGET = Path("extensions/engineering_worker_ai/plugin.py")
BACKUP = Path("/tmp/plugin.py.pre-v6-opencode-plan-watchdog")

OLD_TIMEOUTS = 'STAGE_TIMEOUTS = {"inspect": 300, "plan": 300, "aider": 600, "review": 300, "test": 300}\n'
NEW_TIMEOUTS = OLD_TIMEOUTS + 'INSPECT_IDLE_TIMEOUT = 60\n'

OLD_SIG = '''    capture_limit: int = MAX_CAPTURE_BYTES,
) -> dict[str, Any]:
    timeout = max(1, min(int(timeout), 3600))
    started = time.monotonic()
'''
NEW_SIG = '''    capture_limit: int = MAX_CAPTURE_BYTES,
    idle_timeout: int | None = None,
) -> dict[str, Any]:
    timeout = max(1, min(int(timeout), 3600))
    idle_timeout = None if idle_timeout is None else max(1, min(int(idle_timeout), timeout))
    started = time.monotonic()
    last_progress = started
    last_out_size = 0
    last_err_size = 0
'''

OLD_FLAGS = '''    timed_out = False
    overflow = False
    rc = 1
'''
NEW_FLAGS = '''    timed_out = False
    idle_timed_out = False
    overflow = False
    rc = 1
'''

OLD_LOOP = '''                if time.monotonic() - started > timeout:
                    timed_out = True
                    rc = 124
                    _kill_group(proc.pid)
                    break
                if out.stat().st_size > capture_limit or err.stat().st_size > capture_limit:
                    overflow = True
                    rc = 125
                    _kill_group(proc.pid)
                    break
                time.sleep(0.05)
'''
NEW_LOOP = '''                now = time.monotonic()
                if now - started > timeout:
                    timed_out = True
                    rc = 124
                    _kill_group(proc.pid)
                    break
                out_size = out.stat().st_size
                err_size = err.stat().st_size
                if out_size != last_out_size or err_size != last_err_size:
                    last_progress = now
                    last_out_size = out_size
                    last_err_size = err_size
                if idle_timeout is not None and now - last_progress > idle_timeout:
                    idle_timed_out = True
                    rc = 126
                    _kill_group(proc.pid)
                    break
                if out_size > capture_limit or err_size > capture_limit:
                    overflow = True
                    rc = 125
                    _kill_group(proc.pid)
                    break
                time.sleep(0.05)
'''

OLD_RETURN = '''            "returncode": 124 if timed_out else (125 if overflow else rc),
            "timed_out": timed_out,
            "output_overflow": overflow,
'''
NEW_RETURN = '''            "returncode": 124 if timed_out else (126 if idle_timed_out else (125 if overflow else rc)),
            "timed_out": timed_out,
            "idle_timed_out": idle_timed_out,
            "output_overflow": overflow,
'''

OLD_INVOKE = '''            r = _run([_binary("opencode"), "run", "--model", OPENCODE_MODEL, prompt], box, STAGE_TIMEOUTS["inspect"], network=True)
'''
NEW_INVOKE = '''            r = _run(
                [_binary("opencode"), "run", "--agent", "plan", "--model", OPENCODE_MODEL, prompt],
                box,
                STAGE_TIMEOUTS["inspect"],
                network=True,
                idle_timeout=INSPECT_IDLE_TIMEOUT,
            )
'''

OLD_PROMPT_LINE = '''                "Do not emit tool-call JSON, markdown, prose outside JSON, or placeholder paths. "
'''
NEW_PROMPT_LINE = '''                "Use only read-only inspection capabilities; do not use bash, edit, write, task, or question workflows. "
                "Do not emit tool-call JSON, markdown, prose outside JSON, or placeholder paths. "
'''

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}_anchor_count:{count}")
    return text.replace(old, new, 1)

def main() -> int:
    if not TARGET.is_file():
        raise RuntimeError("target_missing")
    text = TARGET.read_text(encoding="utf-8")

    if '"--agent", "plan"' in text:
        raise RuntimeError("plan_agent_already_present")
    if "idle_timed_out" in text:
        raise RuntimeError("idle_watchdog_already_present")

    updated = text
    updated = replace_once(updated, OLD_TIMEOUTS, NEW_TIMEOUTS, "timeouts")
    updated = replace_once(updated, OLD_SIG, NEW_SIG, "run_signature")
    updated = replace_once(updated, OLD_FLAGS, NEW_FLAGS, "run_flags")
    updated = replace_once(updated, OLD_LOOP, NEW_LOOP, "run_loop")
    updated = replace_once(updated, OLD_RETURN, NEW_RETURN, "run_return")
    updated = replace_once(updated, OLD_INVOKE, NEW_INVOKE, "inspect_invocation")
    updated = replace_once(updated, OLD_PROMPT_LINE, NEW_PROMPT_LINE, "inspect_prompt")

    required = (
        'INSPECT_IDLE_TIMEOUT = 60',
        '"--agent", "plan"',
        'idle_timeout=INSPECT_IDLE_TIMEOUT',
        '"idle_timed_out": idle_timed_out',
        'rc = 126',
        'do not use bash, edit, write, task, or question workflows',
        'def _parse_inspection_contract(',
        'semantic_contract_ok=contract is not None',
    )
    for token in required:
        if token not in updated:
            raise RuntimeError("required_contract_missing:" + token)

    if 'ok = r["returncode"] == 0 and not mutations and contract is not None' not in updated:
        raise RuntimeError("semantic_acceptance_gate_missing")

    compile(updated, str(TARGET), "exec")
    shutil.copy2(TARGET, BACKUP)
    tmp = TARGET.with_name(TARGET.name + ".plan-watchdog.tmp")
    tmp.write_text(updated, encoding="utf-8")
    compile(tmp.read_text(encoding="utf-8"), str(TARGET), "exec")
    tmp.replace(TARGET)

    print("V6_OPENCODE_PLAN_AGENT_IDLE_WATCHDOG_REPAIR=PASS")
    print("BACKUP=" + str(BACKUP))
    print("SHA256=" + sha(TARGET))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
