#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib
import shutil

TARGET = Path("extensions/engineering_worker_ai/plugin.py")
BACKUP = Path("/tmp/plugin.py.pre-v6-opencode-semantic-gate")
HELPER = '\ndef _parse_inspection_contract(stdout: str) -> dict[str, Any]:\n    text = str(stdout or "").strip()\n    if not text or len(text.encode("utf-8")) > MAX_CAPTURE_BYTES:\n        raise RuntimeError("opencode_inspection_contract_missing")\n    if text.startswith("```") or text.endswith("```"):\n        raise RuntimeError("opencode_inspection_contract_markdown_rejected")\n    try:\n        obj = json.loads(text)\n    except Exception as exc:\n        raise RuntimeError("opencode_inspection_contract_invalid_json") from exc\n    if not isinstance(obj, dict):\n        raise RuntimeError("opencode_inspection_contract_not_object")\n    if set(obj) != {"status", "summary", "defect_candidates"}:\n        raise RuntimeError("opencode_inspection_contract_keys_invalid")\n    status = obj.get("status")\n    if status not in {"DEFECTS_FOUND", "INSUFFICIENT_EVIDENCE"}:\n        raise RuntimeError("opencode_inspection_contract_status_invalid")\n    summary = str(obj.get("summary") or "").strip()\n    if not summary or len(summary.encode("utf-8")) > 16000:\n        raise RuntimeError("opencode_inspection_contract_summary_invalid")\n    rows = obj.get("defect_candidates")\n    if not isinstance(rows, list) or len(rows) > MAX_CHANGED_FILES:\n        raise RuntimeError("opencode_inspection_contract_candidates_invalid")\n    if status == "DEFECTS_FOUND" and not rows:\n        raise RuntimeError("opencode_inspection_contract_candidates_required")\n    if status == "INSUFFICIENT_EVIDENCE" and rows:\n        raise RuntimeError("opencode_inspection_contract_insufficient_must_be_empty")\n    clean = []\n    for row in rows:\n        if not isinstance(row, dict) or set(row) != {"defect", "canonical_owner", "reproduction_path", "file_scope", "evidence"}:\n            raise RuntimeError("opencode_inspection_candidate_keys_invalid")\n        defect = str(row.get("defect") or "").strip()\n        owner = str(row.get("canonical_owner") or "").strip()\n        reproduction = str(row.get("reproduction_path") or "").strip()\n        evidence = str(row.get("evidence") or "").strip()\n        scope = row.get("file_scope")\n        if not all((defect, owner, reproduction, evidence)):\n            raise RuntimeError("opencode_inspection_candidate_field_missing")\n        if not isinstance(scope, list) or not scope or len(scope) > MAX_ALLOWED_PATHS:\n            raise RuntimeError("opencode_inspection_candidate_scope_invalid")\n        safe_scope = [_safe_rel(str(x)) for x in scope]\n        if len(set(safe_scope)) != len(safe_scope):\n            raise RuntimeError("opencode_inspection_candidate_scope_duplicate")\n        clean.append({\n            "defect": defect,\n            "canonical_owner": owner,\n            "reproduction_path": reproduction,\n            "file_scope": safe_scope,\n            "evidence": evidence,\n        })\n    return {"status": status, "summary": summary, "defect_candidates": clean}\n'
OLD_PROMPT = '                "Inspect this frozen canonical EIRA package snapshot. Do not edit. "\n                "Use snapshot evidence only; do not invent LIVE runtime truth. "\n                "Identify exact defect candidates, canonical owner, reproduction path, and bounded file scope. "\n                "If insufficient evidence, say so. OBJECTIVE: " + objective\n'
NEW_PROMPT = '                "Inspect this frozen canonical EIRA package snapshot. Do not edit. "\n                "Use snapshot evidence only; do not invent LIVE runtime truth. "\n                "Do not emit tool-call JSON, markdown, prose outside JSON, or placeholder paths. "\n                "Return EXACTLY one JSON object with keys status, summary, defect_candidates. "\n                "status must be DEFECTS_FOUND or INSUFFICIENT_EVIDENCE. "\n                "For DEFECTS_FOUND, defect_candidates must be a nonempty array of objects with exact keys "\n                "defect, canonical_owner, reproduction_path, file_scope, evidence. file_scope must contain only relative snapshot paths. "\n                "For INSUFFICIENT_EVIDENCE, defect_candidates must be an empty array. "\n                "Identify exact defect candidates, canonical owner, reproduction path, bounded file scope, and evidence. "\n                "OBJECTIVE: " + objective\n'
OLD_LOGIC = '            ok = r["returncode"] == 0 and not mutations\n            _append_receipt(job_dir, ledger, "opencode_inspect", "PASS" if ok else "FAIL", mutations=mutations, returncode=r["returncode"])\n            result = {\n                "schema": SCHEMA, "mode": "inspect", "job_id": job_id, "ok": ok,\n                "source_fingerprint": ws["source_fingerprint"], "opencode": r,\n'
NEW_LOGIC = '            contract = None\n            semantic_error = None\n            if r["returncode"] == 0 and not mutations:\n                try:\n                    contract = _parse_inspection_contract(r.get("stdout", ""))\n                except Exception as exc:\n                    semantic_error = str(exc)\n            ok = r["returncode"] == 0 and not mutations and contract is not None\n            _append_receipt(\n                job_dir, ledger, "opencode_inspect", "PASS" if ok else "FAIL",\n                mutations=mutations, returncode=r["returncode"],\n                semantic_contract_ok=contract is not None,\n                semantic_error=semantic_error,\n            )\n            result = {\n                "schema": SCHEMA, "mode": "inspect", "job_id": job_id, "ok": ok,\n                "source_fingerprint": ws["source_fingerprint"], "inspection_contract": contract,\n                "opencode": r,\n'

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    if not TARGET.is_file():
        raise RuntimeError("target_missing")
    src = TARGET.read_text(encoding="utf-8")
    if src.count("def _parse_inspection_contract("):
        raise RuntimeError("semantic_gate_already_present")
    if src.count(OLD_PROMPT) != 1:
        raise RuntimeError("prompt_anchor_not_exactly_once")
    if src.count(OLD_LOGIC) != 1:
        raise RuntimeError("logic_anchor_not_exactly_once")

    insert_at = src.find("def inspect(request: dict[str, Any])")
    if insert_at < 0:
        raise RuntimeError("inspect_anchor_missing")
    updated = src[:insert_at] + HELPER + "\n" + src[insert_at:]
    updated = updated.replace(OLD_PROMPT, NEW_PROMPT, 1)
    updated = updated.replace(OLD_LOGIC, NEW_LOGIC, 1)

    required = (
        "def _parse_inspection_contract(",
        "opencode_inspection_contract_invalid_json",
        "semantic_contract_ok=contract is not None",
        '"inspection_contract": contract',
        "Do not emit tool-call JSON",
    )
    for token in required:
        if token not in updated:
            raise RuntimeError("required_semantic_gate_missing:" + token)

    compile(updated, str(TARGET), "exec")
    shutil.copy2(TARGET, BACKUP)
    tmp = TARGET.with_name(TARGET.name + ".semantic-gate.tmp")
    tmp.write_text(updated, encoding="utf-8")
    compile(tmp.read_text(encoding="utf-8"), str(TARGET), "exec")
    tmp.replace(TARGET)
    print("V6_OPENCODE_SEMANTIC_GATE_REPAIR=PASS")
    print("BACKUP=" + str(BACKUP))
    print("SHA256=" + sha(TARGET))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
