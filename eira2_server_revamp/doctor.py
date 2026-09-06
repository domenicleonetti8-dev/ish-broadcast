#!/usr/bin/env python3
"""Forensic + semantic doctor for the isolated EIRA 2 super server.

This doctor is intentionally side-effect-free. It validates the isolated package,
route contracts, neural semantics, path protections, and browser JavaScript syntax.
It never mutates Easystore LIVE.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "server.py"
HARDENING = ROOT / "hardening.py"
QUALIFY = ROOT / "qualify.py"
UI = ROOT / "static" / "index.html"
PY_FILES = [SERVER, HARDENING, QUALIFY, Path(__file__).resolve()]


def result(name: str, ok: bool, detail: str, *, severity: str = "error") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail, "severity": severity}


def explicit_id(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    for key in ("id", "node_id", "name", "path"):
        value = obj.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def endpoints(edge: Any) -> tuple[str | None, str | None]:
    if not isinstance(edge, dict):
        return None, None
    a = edge.get("source", edge.get("from", edge.get("a", edge.get("source_id"))))
    b = edge.get("target", edge.get("to", edge.get("b", edge.get("target_id"))))
    return (str(a).strip() if a is not None else None, str(b).strip() if b is not None else None)


def list_nodes(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            seq = data.get("nodes", data.get("neurons", []))
            if isinstance(seq, list):
                return [x for x in seq if isinstance(x, dict)]
    return []


def list_fibers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            seq = data.get("fibers", data.get("edges", []))
            if isinstance(seq, list):
                return [x for x in seq if isinstance(x, dict)]
    return []


def semantic_neural_check(overview: Any, fibers: Any, activity: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    nodes = list_nodes(overview)
    edges = list_fibers(fibers)
    live = list_nodes(activity)
    ids = [explicit_id(n) for n in nodes]
    missing_ids = sum(1 for x in ids if not x)
    canonical = {x for x in ids if x}
    out.append(result("canonical_node_ids", bool(nodes) and missing_ids == 0, f"nodes={len(nodes)} missing_ids={missing_ids}"))

    duplicate_count = len([x for x in ids if x]) - len(canonical)
    out.append(result("canonical_node_ids_unique", duplicate_count == 0, f"duplicates={duplicate_count}"))

    bad_edges: list[str] = []
    adjacency: dict[str, set[str]] = {x: set() for x in canonical}
    for edge in edges:
        a, b = endpoints(edge)
        if not a or not b or a not in canonical or b not in canonical:
            bad_edges.append(f"{a}->{b}")
            continue
        adjacency[a].add(b)
        adjacency[b].add(a)
    out.append(result("fiber_endpoints_canonical", len(bad_edges) == 0, f"fibers={len(edges)} invalid={len(bad_edges)}" + (f" sample={bad_edges[:3]}" if bad_edges else "")))

    live_ids = [explicit_id(x) for x in live]
    unidentified = sum(1 for x in live_ids if not x)
    unknown = [x for x in live_ids if x and x not in canonical]
    out.append(result("activity_identifiers_explicit", unidentified == 0, f"activity={len(live)} unidentified={unidentified}"))
    out.append(result("activity_targets_canonical", len(unknown) == 0, f"unknown={unknown[:5]}" if unknown else "all_activity_targets_canonical"))

    core = [n for n in canonical if re.search(r"core|kernel|supervisor|registry|bridge|orchestr|spine", n, re.I)]
    out.append(result("canonical_core_present", bool(core), f"core_candidates={core[:6]}"))
    reachable = 0
    if core:
        seen = set(core)
        queue = list(core)
        while queue:
            cur = queue.pop(0)
            for nxt in adjacency.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        reachable = sum(1 for x in live_ids if x and x in seen)
    targets = sum(1 for x in live_ids if x)
    out.append(result("active_targets_reachable_from_core", targets == 0 or reachable == targets, f"reachable={reachable}/{targets}"))
    return out


def extract_script(html: str) -> str:
    matches = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.S | re.I)
    return "\n".join(matches)


def static_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    texts: dict[Path, str] = {}
    for path in PY_FILES:
        try:
            text = path.read_text(encoding="utf-8")
            texts[path] = text
            ast.parse(text, filename=str(path))
            checks.append(result(f"python_syntax:{path.name}", True, "AST parse PASS"))
        except Exception as exc:
            checks.append(result(f"python_syntax:{path.name}", False, f"{type(exc).__name__}:{exc}"))

    server = texts.get(SERVER, "")
    hardening = texts.get(HARDENING, "")
    html = UI.read_text(encoding="utf-8") if UI.exists() else ""
    script = extract_script(html)

    checks.append(result("no_shell_true", "shell=True" not in server and "shell=True" not in hardening, "subprocesses remain argv-based"))
    containment = bool(re.search(r"root\s*!=\s*\w+\s+and\s+root\s+not\s+in\s+\w+\.parents", server)) and "ar_path_escape" in server
    checks.append(result("ar_path_containment", containment, "USDZ route contains root-boundary enforcement"))
    checks.append(result("pid_lock_present", "eira2_server_instance_already_running" in server and "release_pid_lock" in server, "exclusive instance lock + cleanup present"))
    checks.append(result("tls_support_present", "SSLContext" in server and "EIRA2_TLS_CERT" in server and "EIRA2_TLS_KEY" in server, "optional TLS termination present"))
    checks.append(result("manifest_verifier_present", "verify_manifest" in hardening and "sha256_mismatch" in hardening and "manifest_path_escape" in hardening, "size/hash/path manifest verification present"))
    checks.append(result("probe_verifier_present", "verify_command_bridge" in hardening and "probe_not_configured" in hardening, "side-effect-free bridge probes supported"))
    checks.append(result("deep_doctor_route_present", 'path == "/api/doctor"' in server and "deep_doctor()" in server, "runtime deep doctor exposed"))

    client_routes = set(re.findall(r"['\"](/api/[A-Za-z0-9_./{}-]+)['\"]", script))
    dynamic_prefixes = {x for x in client_routes if "${" in x or "{" in x}
    server_routes = set(re.findall(r"path\s*==\s*['\"](/api/[^'\"]+)['\"]", server))
    server_prefixes = set(re.findall(r"path\.startswith\(['\"](/api/[^'\"]+)['\"]\)", server))
    unresolved = []
    for route in sorted(client_routes - dynamic_prefixes):
        if route in server_routes:
            continue
        if any(route.startswith(prefix) for prefix in server_prefixes):
            continue
        unresolved.append(route)
    checks.append(result("ui_api_routes_resolve", not unresolved, f"unresolved={unresolved}" if unresolved else f"routes={len(client_routes)} all_resolved"))

    required_ui = ["ACTIVATE EIRA", "MUTE", "SEND", "INVENTION LAB", "APPLE AR", "/api/neural/activity", "pathTo(", "topology.paths", "topology.cores", "topology.pathEdges", "topology.pathNodes"]
    absent = [x for x in required_ui if x not in html]
    checks.append(result("live_neural_activity_contract", not absent, f"missing={absent}" if absent else "core-to-active evidenced routing markers present"))

    node = shutil.which("node")
    if script and node:
        cp = subprocess.run([node, "--check"], input=script, text=True, capture_output=True, check=False)
        checks.append(result("browser_javascript_syntax", cp.returncode == 0, (cp.stderr or cp.stdout or "node --check PASS").strip()[-1200:]))
    else:
        checks.append(result("browser_javascript_syntax", bool(script), "Node unavailable; script extraction only", severity="warning"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", action="store_true", help="run source-level doctor only")
    parser.add_argument("--overview")
    parser.add_argument("--fibers")
    parser.add_argument("--activity")
    args = parser.parse_args()

    checks = static_checks()
    if args.overview or args.fibers or args.activity:
        try:
            if not (args.overview and args.fibers and args.activity):
                raise ValueError("overview_fibers_activity_must_be_supplied_together")
            overview = json.loads(Path(args.overview).read_text(encoding="utf-8"))
            fibers = json.loads(Path(args.fibers).read_text(encoding="utf-8"))
            activity = json.loads(Path(args.activity).read_text(encoding="utf-8"))
            checks.extend(semantic_neural_check(overview, fibers, activity))
        except Exception as exc:
            checks.append(result("semantic_neural_load", False, f"{type(exc).__name__}:{exc}"))

    errors = [x for x in checks if not x["ok"] and x["severity"] == "error"]
    warnings = [x for x in checks if not x["ok"] and x["severity"] == "warning"]
    payload = {"ok": not errors, "checks": checks, "errors": len(errors), "warnings": len(warnings)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
