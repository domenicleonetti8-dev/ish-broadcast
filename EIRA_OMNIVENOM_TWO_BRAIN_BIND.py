#!/usr/bin/env python3
from __future__ import annotations
import ast, hashlib, shutil, sys, time
from pathlib import Path

LIVE=Path(sys.argv[1] if len(sys.argv)>1 else '/media/domenicleonetti/easystore/EIRA/LIVE').expanduser().resolve()
MAIN=LIVE/'main.py'
BRIDGE=LIVE/'extensions'/'omnivenom_mesh_ai'/'eira_bridge.py'
BRIDGE_TEXT='from __future__ import annotations\n\nimport os\nimport time\nimport uuid\nfrom pathlib import Path\nfrom threading import RLock\n\nfrom .runtime import Omnivenom\n\n_LOCK = RLock()\n_MESH = None\n_LAST_REFRESH = 0.0\n_REFRESH_SECONDS = 60.0\n_SYSTEM_WORDS = (\n    "eira", " live", "file", "folder", "directory", "memory", "system",\n    "extension", "artifact", "node", "omnivenom", "venom", "recent",\n    "added", "changed", "project", "code", "router", "brain",\n)\n\n\ndef _live_root() -> Path:\n    return Path(__file__).resolve().parents[2]\n\n\ndef _mesh() -> Omnivenom:\n    global _MESH\n    with _LOCK:\n        if _MESH is None:\n            _MESH = Omnivenom(_live_root())\n        return _MESH\n\n\ndef _needs_evidence(text: str) -> bool:\n    low = " " + str(text or "").lower()\n    return any(word in low for word in _SYSTEM_WORDS)\n\n\ndef _recent_files(limit: int = 18):\n    root = _live_root()\n    rows = []\n    skip = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules"}\n    for current, dirs, files in os.walk(root, followlinks=False):\n        dirs[:] = [d for d in dirs if d not in skip]\n        cur = Path(current)\n        for name in files:\n            p = cur / name\n            try:\n                st = p.stat()\n                rel = p.relative_to(root).as_posix()\n            except OSError:\n                continue\n            rows.append((st.st_mtime_ns, {"path": rel, "size": st.st_size, "mtime": st.st_mtime}))\n    rows.sort(key=lambda x: x[0], reverse=True)\n    return [item for _, item in rows[:max(1, min(int(limit), 50))]]\n\n\ndef _evidence(text: str):\n    global _LAST_REFRESH\n    if not _needs_evidence(text):\n        return None\n    mesh = _mesh()\n    now = time.monotonic()\n    with _LOCK:\n        status = mesh.status()\n        if int(status.get("nodes", 0) or 0) == 0 or now - _LAST_REFRESH >= _REFRESH_SECONDS:\n            mesh.refresh()\n            _LAST_REFRESH = now\n    return {\n        "omnivenom": mesh.context(str(text), depth=1, limit=80),\n        "recent_files": _recent_files(),\n        "live_root": str(_live_root()),\n        "evidence_mode": "read_only",\n    }\n\n\ndef chat(prompt, timeout=600, persist_history=True, **kwargs):\n    """Two-brain Eira bridge: OmniVenom evidence -> Unified Brain dominant -> legacy/local brain tandem via Unified Brain host."""\n    text = str(prompt or "").strip()\n    if not text:\n        return {"status": "unresolved", "model": None, "response": "", "errors": ["empty_prompt"]}\n\n    evidence = None\n    evidence_error = None\n    try:\n        evidence = _evidence(text)\n    except Exception as exc:\n        evidence_error = f"{type(exc).__name__}:{str(exc)[:160]}"\n\n    try:\n        from extensions.unified_brain_ai import plugin as unified\n        options = {\n            "persist_history": bool(persist_history),\n            "dominant_reasoning_owner": "unified_brain_ai",\n            "legacy_brain_role": "tandem_provider",\n            "one_output_plane": True,\n        }\n        if evidence is not None:\n            options["venom_mesh_context"] = evidence\n            options["omnivenom_context"] = evidence\n        result = unified.ask({\n            "turn_id": "main_" + uuid.uuid4().hex[:12],\n            "message": text,\n            "options": options,\n        })\n        response = str(result.get("response") or "").strip() if isinstance(result, dict) else ""\n        if isinstance(result, dict) and result.get("ok") and response:\n            errors = []\n            if evidence_error:\n                errors.append({"node": "omnivenom", "error": evidence_error})\n            return {\n                "status": "answered",\n                "model": "unified_brain_ai",\n                "response": response,\n                "errors": errors,\n                "source": result.get("source"),\n                "capability": result.get("capability"),\n                "metadata": result.get("metadata") or {},\n            }\n        unified_error = (result or {}).get("error") if isinstance(result, dict) else "unified_result_invalid"\n    except Exception as exc:\n        unified_error = f"{type(exc).__name__}:{str(exc)[:160]}"\n\n    # Safe continuity fallback: use the already-existing local/conversation brain.\n    try:\n        from extensions.local_brain.router import chat as legacy_chat\n        legacy = legacy_chat(text, timeout=timeout, persist_history=persist_history)\n        if isinstance(legacy, dict):\n            legacy.setdefault("errors", [])\n            legacy["errors"].append({"node": "unified_brain_ai", "error": unified_error})\n            if evidence_error:\n                legacy["errors"].append({"node": "omnivenom", "error": evidence_error})\n            return legacy\n    except Exception as exc:\n        legacy_error = f"{type(exc).__name__}:{str(exc)[:160]}"\n        return {\n            "status": "unresolved",\n            "model": None,\n            "response": "I couldn\\'t complete that conversation turn.",\n            "errors": [\n                {"node": "unified_brain_ai", "error": unified_error},\n                {"node": "local_brain", "error": legacy_error},\n            ],\n        }\n\n    return {"status": "unresolved", "model": None, "response": "I couldn\\'t complete that conversation turn.", "errors": [{"node": "unified_brain_ai", "error": unified_error}]}\n\n\ndef status():\n    return {\n        "ok": True,\n        "brain_count": 2,\n        "dominant": "unified_brain_ai",\n        "tandem": "local_brain",\n        "omnivenom_role": "connective_evidence_fabric",\n        "outward_response_planes": 1,\n        "voice_owner": "main.py:_speak",\n    }\n'
MARK='# EIRA_OMNIVENOM_TWO_BRAIN_BIND_V1'

def die(msg): raise SystemExit('EIRA TWO-BRAIN BIND: '+msg)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

for p,label in [
    (MAIN,'main.py'),
    (LIVE/'extensions'/'omnivenom_mesh_ai'/'runtime.py','OmniVenom runtime'),
    (LIVE/'extensions'/'unified_brain_ai'/'plugin.py','Unified Brain'),
    (LIVE/'extensions'/'local_brain'/'router.py','local brain'),
]:
    if not p.is_file(): die(label+' missing: '+str(p))

before=sha(MAIN)
stamp=time.strftime('%Y%m%d_%H%M%S')
backup=LIVE/f'main.py.bak_omnivenom_two_brain_{stamp}'
shutil.copy2(MAIN,backup)
BRIDGE.write_text(BRIDGE_TEXT,encoding='utf-8')

text=MAIN.read_text(encoding='utf-8')
if MARK not in text:
    candidates=[
        'from extensions.local_brain.router import chat, should_route',
        'from extensions.local_brain.router import should_route, chat',
    ]
    old=next((x for x in candidates if x in text),None)
    if old is None:
        die('expected local_brain import not found; main.py left untouched except backup/bridge')
    new=(MARK+'\n'
         'from extensions.local_brain.router import should_route\n'
         'from extensions.omnivenom_mesh_ai.eira_bridge import chat')
    text=text.replace(old,new,1)

# Remove the temporary diagnostic line added during troubleshooting.
lines=[line for line in text.splitlines() if 'ROUTER_DEBUG:' not in line]
text='\n'.join(lines)+'\n'
MAIN.write_text(text,encoding='utf-8')

try:
    ast.parse(MAIN.read_text(encoding='utf-8'),filename=str(MAIN))
    ast.parse(BRIDGE.read_text(encoding='utf-8'),filename=str(BRIDGE))
except Exception as exc:
    shutil.copy2(backup,MAIN)
    die('syntax verification failed; main.py rolled back: '+repr(exc))

if '_speak(eira_response)' not in MAIN.read_text(encoding='utf-8'):
    shutil.copy2(backup,MAIN)
    die('voice handoff _speak(eira_response) not found; main.py rolled back')

sys.path.insert(0,str(LIVE))
try:
    from extensions.omnivenom_mesh_ai.eira_bridge import status
    s=status()
    from extensions.unified_brain_ai import plugin as unified
    u=unified.status()
except Exception as exc:
    shutil.copy2(backup,MAIN)
    die('import verification failed; main.py rolled back: '+repr(exc))

print('EIRA_TWO_BRAIN_BIND=PASS')
print('MAIN_BEFORE_SHA256='+before)
print('MAIN_AFTER_SHA256='+sha(MAIN))
print('BACKUP='+str(backup))
print('OMNIVENOM_ROLE='+str(s.get('omnivenom_role')))
print('DOMINANT='+str(s.get('dominant')))
print('TANDEM='+str(s.get('tandem')))
print('BRAINS='+str(s.get('brain_count')))
print('VOICE_HANDOFF=main.py:_speak')
print('UNIFIED_VERSION='+str(u.get('version')))
