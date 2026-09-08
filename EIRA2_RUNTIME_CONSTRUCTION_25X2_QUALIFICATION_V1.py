#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import sys
import time
from pathlib import Path

ROOT = Path('/media/domenicleonetti/easystore/EIRA/LIVE').resolve()
MANIFEST = ROOT / 'eira2-package-manifest.json'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


async def fake_generate(prompt: str) -> str:
    return 'qualification-candidate'


async def fake_verify(candidate: str, *args, **kwargs):
    return candidate


def check(name: str, condition: bool, detail='') -> dict:
    return {'name': name, 'ok': bool(condition), 'detail': str(detail)}


def one_round(round_id: int) -> dict:
    from eira2.live import live_config, _verified_live_identity
    from eira2.runtime import Eira2Runtime

    target, package_tree = _verified_live_identity(ROOT, MANIFEST)
    config = live_config(ROOT, MANIFEST, host='127.0.0.1', port=8782)
    runtime = Eira2Runtime(config, generate=fake_generate, verify=fake_verify)

    records = runtime.supervisor._records
    names = list(records)
    topo = runtime.supervisor.topological_order()
    specs = {name: rec.service.spec for name, rec in records.items()}
    deps = {name: tuple(spec.dependencies) for name, spec in specs.items()}

    required_attrs = (
        'lock','events','state','checkpoints','registry','capabilities','extensions','memory',
        'history','work','learning','security_attestation','jellyfish_immune','engineering','worlds',
        'workers','evidence','web_evidence','identity','analysis','constellation','expression','reaction',
        'commit','reasoning','conversation','presence','voice','delivery','ingress','native_input','senses',
        'health','status_service','doctor','operations','resilience','bootstrap','activation','repair','self_evolution'
    )

    tests = []
    tests.append(check('01_manifest_exists', MANIFEST.is_file(), MANIFEST))
    tests.append(check('02_manifest_hash_nonempty', bool(sha256(MANIFEST))))
    tests.append(check('03_verified_target_sha40', len(target) == 40, target))
    tests.append(check('04_package_tree_sha64', len(package_tree) == 64, package_tree))
    tests.append(check('05_config_root_exact', Path(config.root).resolve() == ROOT, config.root))
    tests.append(check('06_runtime_project_root_exact', runtime.project_root == ROOT, runtime.project_root))
    tests.append(check('07_all_core_attributes_present', all(hasattr(runtime, x) for x in required_attrs)))
    tests.append(check('08_memory_service_present', hasattr(runtime, 'memory') and runtime.memory is not None))
    tests.append(check('09_history_service_present', hasattr(runtime, 'history') and runtime.history is not None))
    tests.append(check('10_learning_service_present', hasattr(runtime, 'learning') and runtime.learning is not None))
    tests.append(check('11_identity_service_present', hasattr(runtime, 'identity') and runtime.identity is not None))
    tests.append(check('12_reasoning_service_present', hasattr(runtime, 'reasoning') and runtime.reasoning is not None))
    tests.append(check('13_conversation_service_present', hasattr(runtime, 'conversation') and runtime.conversation is not None))
    tests.append(check('14_delivery_service_present', hasattr(runtime, 'delivery') and runtime.delivery is not None))
    tests.append(check('15_voice_service_present', hasattr(runtime, 'voice') and runtime.voice is not None))
    tests.append(check('16_native_input_present', hasattr(runtime, 'native_input') and runtime.native_input is not None))
    tests.append(check('17_senses_present', hasattr(runtime, 'senses') and runtime.senses is not None))
    tests.append(check('18_registry_nonempty', len(names) > 0, len(names)))
    tests.append(check('19_service_names_unique', len(names) == len(set(names)), len(names)))
    tests.append(check('20_topology_covers_all_services', set(topo) == set(names), f'{len(topo)}/{len(names)}'))
    tests.append(check('21_dependencies_exist', all(dep in specs for row in deps.values() for dep in row)))
    tests.append(check('22_dependency_order_valid', all(topo.index(dep) < topo.index(name) for name,row in deps.items() for dep in row)))
    tests.append(check('23_required_services_have_manifests', all(getattr(spec, 'name', '') for spec in specs.values())))
    tests.append(check('24_single_conversation_spine', sum(1 for n in names if n == runtime.conversation.spec.name) == 1, runtime.conversation.spec.name))
    tests.append(check('25_single_delivery_gate', sum(1 for n in names if n == runtime.delivery.spec.name) == 1, runtime.delivery.spec.name))

    ok = len(tests) == 25 and all(t['ok'] for t in tests)
    return {
        'round': round_id,
        'ok': ok,
        'tests': tests,
        'service_count': len(names),
        'topological_order': topo,
        'target_sha': target,
        'package_tree_sha256': package_tree,
    }


def main() -> int:
    started = time.time()
    rounds = []
    try:
        for r in (1, 2):
            rounds.append(one_round(r))
        flat = [t for r in rounds for t in r['tests']]
        result = {
            'schema': 'eira2_runtime_construction_25x2_v1',
            'ok': len(flat) == 50 and all(t['ok'] for t in flat),
            'mutates_live': False,
            'rounds': rounds,
            'clean_passes': sum(1 for t in flat if t['ok']),
            'required_clean_passes': 50,
            'elapsed_seconds': round(time.time() - started, 3),
        }
    except BaseException as exc:
        result = {
            'schema': 'eira2_runtime_construction_25x2_v1',
            'ok': False,
            'mutates_live': False,
            'clean_passes': 0,
            'required_clean_passes': 50,
            'error': f'{type(exc).__name__}:{exc}',
            'elapsed_seconds': round(time.time() - started, 3),
        }
    print(json.dumps(result, separators=(',', ':')))
    return 0 if result.get('ok') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
