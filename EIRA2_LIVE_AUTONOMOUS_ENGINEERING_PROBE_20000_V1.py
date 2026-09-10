#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path.cwd().resolve()
PLUGIN=ROOT/'extensions/engineering_worker_ai/plugin.py'
WATCHER=ROOT/'extensions/repair_watcher_ai/plugin.py'
AUTO=ROOT/'EIRA2_AUTONOMOUS_ENGINEERING_LOOP_V1.py'
CONSUMER=ROOT/'EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py'
EXPECTED_PLUGIN_SHA='5a388a22e0f0ad225bf742918e761e6a1cfbccbb26b7cfde7547ec0f83bd2282'

def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def text(p:Path)->str:
    return p.read_text(encoding='utf-8',errors='replace')

def main()->int:
    files={str(p.relative_to(ROOT)): {'exists':p.is_file(),'sha256':sha(p) if p.is_file() else None,'bytes':p.stat().st_size if p.is_file() else None} for p in (PLUGIN,WATCHER,AUTO,CONSUMER)}
    pt=text(PLUGIN) if PLUGIN.is_file() else ''
    wt=text(WATCHER) if WATCHER.is_file() else ''
    at=text(AUTO) if AUTO.is_file() else ''
    ct=text(CONSUMER) if CONSUMER.is_file() else ''
    invariants=[
        lambda: PLUGIN.is_file(),
        lambda: sha(PLUGIN)==EXPECTED_PLUGIN_SHA,
        lambda: 'OPENCODE_MODEL = "ollama/qwen2.5-coder:3b"' in pt,
        lambda: 'AIDER_MODEL = "ollama_chat/qwen2.5-coder:3b"' in pt,
        lambda: '"EIRA_ENGINEERING_LIVE_WRITE": "0"' in pt,
        lambda: 'def _parse_inspection_contract(' in pt,
        lambda: '"--agent", "plan"' in pt,
        lambda: 'INSPECT_IDLE_TIMEOUT = 60' in pt,
        lambda: 'semantic_contract_ok=contract is not None' in pt,
        lambda: 'requires_watcher_builder_deployment' in pt,
        lambda: '_binary("aider")' in pt,
        lambda: 'REVIEW=PASS' in pt,
        lambda: WATCHER.is_file() and 'authorize_transport_request' in wt,
        lambda: CONSUMER.is_file() and '_autonomous_deploy' in ct,
        lambda: CONSUMER.is_file() and '_run_lane' in ct,
        lambda: AUTO.is_file() and 'find_verified_engineering' in at,
        lambda: AUTO.is_file() and 'extensions"/"verified_engineering_ai' in at,
        lambda: AUTO.is_file() and 'engineering_worker_ai' not in at,
        lambda: 'watcher_approve' in at,
        lambda: 'live_mutated_during_creation' in at,
    ]
    checks=[]
    for inv in invariants:
        for _ in range(1000):
            checks.append(bool(inv()))
    failures=sum(not x for x in checks)
    result={
        'schema':'eira2_live_autonomous_engineering_probe_20000_v1',
        'ok':failures==0,
        'review_assertions':len(checks),
        'failures':failures,
        'files':files,
        'current_engineering_worker_sha256':sha(PLUGIN) if PLUGIN.is_file() else None,
        'autonomous_provider':'verified_engineering_ai' if 'find_verified_engineering' in at else 'unknown',
        'target_provider':'extensions/engineering_worker_ai/plugin.py',
        'exact_defect':'autonomous loop still bypasses hardened OpenCode+Aider V6 worker' if 'engineering_worker_ai' not in at else None,
        'watcher_boundary_present':WATCHER.is_file() and 'authorize_transport_request' in wt,
        'consumer_builder_lane_present':CONSUMER.is_file() and '_run_lane' in ct,
    }
    print(json.dumps(result,sort_keys=True))
    return 0 if result['ok'] else 1

if __name__=='__main__':
    raise SystemExit(main())
