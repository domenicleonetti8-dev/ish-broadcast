#!/usr/bin/env python3
from __future__ import annotations

import importlib.util, json
from pathlib import Path

_V3_PATH = Path(__file__).resolve().with_name("EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py")
_spec = importlib.util.spec_from_file_location("eira2_transport_v3_hot_entry", _V3_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("eira2_transport_v3_import_failed")
_v3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v3)

_original_qualification = _v3._execute_read_only_qualification

def _qualification_json_compat(root, spec):
    q = _original_qualification(root, spec)
    if q.get("result") is None and q.get("returncode") == 0:
        text = str(q.get("stdout_tail") or "").strip()
        parsed = None
        if text:
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    parsed = obj
            except Exception:
                parsed = None
        if parsed is not None:
            q["result"] = parsed
            ok, contract = _v3._qualification_success(parsed, 0)
            q["ok"] = ok
            q["accepted_success_contract"] = contract
            q["whole_stdout_json_compat"] = True
    return q

_v3._execute_read_only_qualification = _qualification_json_compat

for _name in dir(_v3):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_v3, _name)
