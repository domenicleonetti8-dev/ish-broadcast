from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .evidence.deterministic import verify_response
from .live import run_live
from .runtime import Eira2Runtime, default_config


async def shadow_smoke(root: Path) -> dict:
    delivered: list[str] = []

    async def candidate(text: str) -> str:
        return "shadow candidate for " + text

    async def sink(text: str) -> None:
        delivered.append(text)

    runtime = Eira2Runtime(default_config(root), generate=candidate, verify=verify_response, sinks=[sink])
    await runtime.start()
    result = await runtime.process("EIRA 2.0 isolated verification")
    health = await runtime.health.snapshot()
    await runtime.stop()
    return {
        "schema": "eira2_shadow_smoke_v1",
        "ok": result.verified and not health["required_failures"],
        "shadow_mode": True,
        "outward_deliveries": len(delivered),
        "required_failures": health["required_failures"],
        "service_count": len(health["services"]),
        "response_characters": len(result.response),
        "privacy": {"conversation_text": False, "source_code": False, "audio": False, "secrets": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--shadow-smoke", action="store_true")
    modes.add_argument("--live", action="store_true")
    parser.add_argument("--package-manifest", type=Path)
    parser.add_argument("--model", default="")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8782)
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if args.shadow_smoke:
        result = asyncio.run(shadow_smoke(root))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["ok"] and result["outward_deliveries"] == 0 else 1

    manifest = (
        args.package_manifest.expanduser().resolve()
        if args.package_manifest is not None
        else root / "eira2-package-manifest.json"
    )
    asyncio.run(run_live(root, manifest, model=args.model, host=args.host, port=args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
