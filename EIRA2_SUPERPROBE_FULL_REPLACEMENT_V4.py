#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "eira2_superprobe_forensic_v4"
EVIDENCE_SCHEMA = "eira2_superprobe_evidence_v4"
DEFAULT_REPORT = Path("eira_probe/eira2_superprobe_report.json")
DEFAULT_EVIDENCE = Path("eira_probe/eira2_superprobe_evidence")
SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "node_modules", "dist", "build",
}


def _now() -> float:
    return time.time()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_json(path: Path, value: Any) -> dict[str, Any]:
    data = _json_bytes(value)
    _atomic_write(path, data)
    return {"path": str(path), "bytes": len(data), "sha256": _sha256_bytes(data)}


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _iter_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        base = Path(current)
        for name in files:
            p = base / name
            try:
                if p.is_file():
                    yield p
            except OSError:
                continue


def _python_files(root: Path) -> list[Path]:
    eira2 = root / "eira2"
    if not eira2.is_dir():
        return []
    return sorted(p for p in _iter_files(eira2) if p.suffix == ".py")


def _module_for(path: Path, root: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return None
    if rel.suffix != ".py":
        return None
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else None


def _resolve_relative(source_module: str, level: int, module: str | None) -> str:
    base = source_module.split(".")
    if level:
        trim = max(0, level - 1)
        if trim:
            base = base[:-trim]
        if base:
            base = base[:-1]
    suffix = (module or "").split(".") if module else []
    return ".".join([*base, *suffix])


def physical_truth(root: Path) -> dict[str, Any]:
    files = []
    total_bytes = 0
    python_count = 0
    for p in _iter_files(root):
        rel = _safe_rel(p, root)
        if any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        total_bytes += st.st_size
        if p.suffix == ".py":
            python_count += 1
        if rel.startswith("eira2/") or rel.startswith("tools/") or rel in {"eira2-package-manifest.json", "main.py"}:
            files.append({"path": rel, "size": st.st_size, "mtime_ns": st.st_mtime_ns})
    files.sort(key=lambda r: r["path"])
    return {
        "ok": (root / "eira2").is_dir(),
        "root": str(root),
        "files": len(files),
        "python_files": python_count,
        "bytes": total_bytes,
        "inventory": files,
    }


def package_truth(root: Path) -> dict[str, Any]:
    manifest = root / "eira2-package-manifest.json"
    if not manifest.is_file():
        return {
            "ok": False,
            "status": "manifest_missing",
            "manifest_path": str(manifest),
            "project_root": str(root),
        }
    added = False
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
            added = True
        module = importlib.import_module("eira2.operations.package_identity")
        verifier = getattr(module, "verify_package_manifest", None)
        if not callable(verifier):
            raise RuntimeError("package_identity_verifier_unavailable")
        payload = verifier(root)
        return {
            "ok": True,
            "status": "verified",
            "manifest_path": str(manifest),
            "project_root": str(root),
            "source_commit_sha": payload.get("source_commit_sha"),
            "package_tree_sha256": payload.get("package_tree_sha256"),
            "file_count": payload.get("file_count"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "verification_failed",
            "manifest_path": str(manifest),
            "project_root": str(root),
            "error": f"{type(exc).__name__}:{exc}"[:2000],
        }
    finally:
        if added:
            try:
                sys.path.remove(str(root))
            except ValueError:
                pass


def _atlas_endpoint_stats(atlas: Any) -> tuple[int, int, int]:
    neurons = getattr(atlas, "neurons", {}) or {}
    fibers = list(getattr(atlas, "fibers", ()) or ())
    ids = set(neurons.keys()) if isinstance(neurons, dict) else set()
    unresolved = 0
    duplicates = 0
    seen = set()
    for f in fibers:
        source = str(getattr(f, "source", ""))
        target = str(getattr(f, "target", ""))
        kind = str(getattr(f, "kind", ""))
        if ids and (source not in ids or target not in ids):
            unresolved += 1
        key = (source, target, kind)
        if key in seen:
            duplicates += 1
        seen.add(key)
    return len(fibers), unresolved, duplicates


def organism_truth(root: Path) -> dict[str, Any]:
    added = False
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
            added = True
        module = importlib.import_module("eira2.neural.atlas")
        Atlas = getattr(module, "NeuralAtlas", None)
        if Atlas is None:
            raise RuntimeError("neural_atlas_class_unavailable")
        atlas = Atlas(root).build()
        overview = atlas.overview()
        road_count, unresolved, duplicates = _atlas_endpoint_stats(atlas)
        neurons = getattr(atlas, "neurons", {}) or {}
        conductive = getattr(atlas, "conductive_fibers", None)
        conductive_count = len(tuple(conductive())) if callable(conductive) else 0
        return {
            "ok": unresolved == 0,
            "schema": "eira2_neural_organism_truth_v4",
            "authority": "eira2.neural.atlas.NeuralAtlas",
            "inventory_source": overview.get("inventory_source"),
            "inventory_neuron_count": int(overview.get("inventory_neuron_count") or 0),
            "addressable_node_count": len(neurons) if isinstance(neurons, dict) else int(overview.get("neuron_count") or 0),
            "road_count": road_count,
            "conductive_road_count": conductive_count,
            "unresolved_road_endpoint_count": unresolved,
            "duplicate_road_count": duplicates,
            "overview": overview,
            "layout_identity_verified": False,
            "layout_identity_status": "not_asserted_without_canonical_shared_layout_contract",
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:2000]}
    finally:
        if added:
            try:
                sys.path.remove(str(root))
            except ValueError:
                pass


def semantic_truth(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    py_files = _python_files(root)
    module_paths: dict[str, str] = {}
    for p in py_files:
        m = _module_for(p, root)
        if m:
            module_paths[m] = _safe_rel(p, root)

    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    known = set(module_paths)

    for p in py_files:
        src = _module_for(p, root)
        if not src:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except SyntaxError as exc:
            unresolved.append({
                "source": src, "target": None, "kind": "syntax_error",
                "error": f"{exc.msg}@{exc.lineno}",
            })
            continue

        targets: set[tuple[str, str]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("eira2"):
                        targets.add((alias.name, "import"))
            elif isinstance(node, ast.ImportFrom):
                target = _resolve_relative(src, node.level, node.module) if node.level else (node.module or "")
                if target.startswith("eira2"):
                    targets.add((target, "from"))

        for target, kind in sorted(targets):
            resolved = target if target in known else None
            if resolved is None:
                probe = target
                while "." in probe:
                    probe = probe.rsplit(".", 1)[0]
                    if probe in known:
                        resolved = probe
                        break
            edges.append({
                "source": src,
                "target": target,
                "resolved_target": resolved,
                "kind": kind,
                "resolved": resolved is not None,
            })
            outgoing[src] += 1
            if resolved:
                incoming[resolved] += 1
            else:
                unresolved.append({
                    "source": src,
                    "target": target,
                    "kind": "unresolved_internal_import",
                })

    graph = {
        "schema": "eira2_semantic_graph_v4",
        "module_count": len(module_paths),
        "edge_count": len(edges),
        "modules": module_paths,
        "edges": edges,
    }
    impact_rows = []
    for module, path in module_paths.items():
        impact_rows.append({
            "module": module,
            "path": path,
            "incoming_edges": incoming[module],
            "outgoing_edges": outgoing[module],
            "impact_score": incoming[module] * 2 + outgoing[module],
        })
    impact_rows.sort(key=lambda r: (-r["impact_score"], r["module"]))
    impact = {
        "schema": "eira2_semantic_impact_index_v4",
        "files": len(impact_rows),
        "rows": impact_rows,
    }
    truth = {
        "ok": len(unresolved) == 0,
        "python_files": len(py_files),
        "semantic_edges": len(edges),
        "impact_index_files": len(impact_rows),
        "unresolved_internal_import_count": len(unresolved),
        "unresolved_internal_imports": unresolved,
    }
    return truth, graph, impact


def extension_truth(root: Path) -> dict[str, Any]:
    manifests = root / "eira2" / "extensions" / "manifests"
    rows = []
    invalid = []
    if manifests.is_dir():
        for p in sorted(manifests.glob("*.json")):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                rows.append({
                    "path": _safe_rel(p, root),
                    "name": payload.get("name") or payload.get("id") or p.stem,
                    "kind": payload.get("kind"),
                    "status": payload.get("status"),
                })
            except Exception as exc:
                invalid.append({"path": _safe_rel(p, root), "error": f"{type(exc).__name__}:{exc}"})
    return {
        "ok": len(invalid) == 0,
        "manifest_count": len(rows),
        "invalid_manifest_count": len(invalid),
        "manifests": rows,
        "invalid": invalid,
    }


def _run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=10, check=False)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 127, "", f"{type(exc).__name__}:{exc}"


def execution_truth(root: Path) -> dict[str, Any]:
    rc, out, err = _run(["ps", "-eo", "pid=,ppid=,etimes=,args="])
    processes = []
    if rc == 0:
        for line in out.splitlines():
            low = line.lower()
            if "eira2" in low or "python3 main.py" in low or "/eira/live" in low:
                processes.append(line.strip()[:2000])
    src, sout, serr = _run(["ss", "-ltnp"])
    listeners = []
    if src == 0:
        for line in sout.splitlines():
            low = line.lower()
            if "python" in low or "eira" in low:
                listeners.append(line.strip()[:2000])
    return {
        "ok": rc == 0,
        "process_command_ok": rc == 0,
        "process_error": err[-1000:] if rc else "",
        "runtime_processes": len(processes),
        "processes": processes,
        "listener_command_ok": src == 0,
        "socket_error": serr[-1000:] if src else "",
        "listeners": listeners,
        "listener_count": len(listeners),
        "hostname": socket.gethostname(),
    }


def forensic_map(root: Path, physical: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "eira2_forensic_map_v4",
        "root": str(root),
        "generated_unix": _now(),
        "physical_inventory": physical.get("inventory", []),
        "semantic_summary": {
            "python_files": semantic.get("python_files", 0),
            "semantic_edges": semantic.get("semantic_edges", 0),
            "unresolved_internal_import_count": semantic.get("unresolved_internal_import_count", 0),
        },
    }


def shared_evidence(artifacts: dict[str, Any], root: Path) -> dict[str, Any]:
    rows = []
    for name, meta in sorted(artifacts.items()):
        rows.append({"name": name, "path": meta["path"], "sha256": meta["sha256"], "bytes": meta["bytes"]})
    fingerprint = _sha256_bytes(_json_bytes(rows))
    bus_manifest = {
        "schema": "eira2_shared_evidence_manifest_v4",
        "fingerprint": fingerprint,
        "generated_unix": _now(),
        "artifacts": rows,
    }
    bus = root / "eira_probe" / "shared_evidence_bus" / "objects" / fingerprint / "manifest.json"
    bus_meta = _write_json(bus, bus_manifest)
    return {
        "ok": True,
        "fingerprint": fingerprint,
        "manifest_sha256": bus_meta["sha256"],
        "manifest_path": str(bus),
        "artifact_count": len(rows),
    }


def discrepancies(package: dict[str, Any], organism: dict[str, Any], semantic: dict[str, Any], extensions: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    if not package.get("ok"):
        out.append({"kind": "package_identity_not_verified", "status": package.get("status"), "error": package.get("error")})
    if not organism.get("ok"):
        out.append({"kind": "canonical_organism_not_verified", "error": organism.get("error") or f"unresolved_road_endpoints:{organism.get('unresolved_road_endpoint_count')}"})
    count = int(semantic.get("unresolved_internal_import_count") or 0)
    if count:
        out.append({"kind": "unresolved_internal_imports", "count": count})
    if not extensions.get("ok"):
        out.append({"kind": "extension_manifest_errors", "count": extensions.get("invalid_manifest_count", 0)})
    return out


def run(root: Path, report_path: Path, evidence_dir: Path) -> dict[str, Any]:
    started = _now()
    root = root.expanduser().resolve()
    report_path = report_path if report_path.is_absolute() else root / report_path
    evidence_dir = evidence_dir if evidence_dir.is_absolute() else root / evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)

    physical = physical_truth(root)
    package = package_truth(root)
    organism = organism_truth(root)
    semantic, graph, impact = semantic_truth(root)
    extensions = extension_truth(root)
    execution = execution_truth(root)
    fmap = forensic_map(root, physical, semantic)

    artifacts: dict[str, Any] = {}
    artifacts["execution_truth"] = _write_json(evidence_dir / "execution_truth.json", execution)
    artifacts["extension_truth"] = _write_json(evidence_dir / "extension_truth.json", extensions)
    artifacts["forensic_map"] = _write_json(evidence_dir / "forensic_map.json", fmap)
    artifacts["organism_truth"] = _write_json(evidence_dir / "organism_truth.json", organism)
    artifacts["package_truth"] = _write_json(evidence_dir / "package_truth.json", package)
    artifacts["semantic_graph"] = _write_json(evidence_dir / "semantic_graph.json", graph)
    artifacts["semantic_impact_index"] = _write_json(evidence_dir / "semantic_impact_index.json", impact)

    shared = shared_evidence(artifacts, root)
    findings = discrepancies(package, organism, semantic, extensions)
    ok = not findings

    report = {
        "schema": SCHEMA,
        "evidence_schema": EVIDENCE_SCHEMA,
        "authority": "eira2_superprobe_read_only_forensic_authority",
        "mode": "read_only_forensic",
        "mutates_live": False,
        "privacy": "local_only",
        "eira2_only": True,
        "root": str(root),
        "base": str(root),
        "generated_unix": _now(),
        "elapsed_seconds": round(_now() - started, 6),
        "ok": ok,
        "artifacts": artifacts,
        "physical_truth": physical,
        "package_identity": package,
        "organism_truth": organism,
        "semantic_truth": semantic,
        "extension_truth": extensions,
        "execution_truth": execution,
        "declared_vs_observed_discrepancies": findings,
        "shared_evidence": shared,
        "evidence_bundle_fingerprint_sha256": shared["fingerprint"],
    }
    _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="EIRA2 canonical read-only forensic Superprobe v4")
    parser.add_argument("--root", default=".", help="EIRA LIVE project root")
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run(Path(args.root), Path(args.output), Path(args.evidence_dir))
    summary = {
        "artifact_count": len(report["artifacts"]),
        "bytes": report["physical_truth"].get("bytes", 0),
        "discrepancy_count": len(report["declared_vs_observed_discrepancies"]),
        "evidence_fingerprint": report["evidence_bundle_fingerprint_sha256"],
        "files": report["physical_truth"].get("files", 0),
        "impact_index_files": report["semantic_truth"].get("impact_index_files", 0),
        "listeners": report["execution_truth"].get("listener_count", 0),
        "ok": report["ok"],
        "organism_ok": report["organism_truth"].get("ok") is True,
        "output": str((Path(args.root).expanduser().resolve() / args.output) if not Path(args.output).is_absolute() else Path(args.output)),
        "package_identity_ok": report["package_identity"].get("ok") is True,
        "python_files": report["semantic_truth"].get("python_files", 0),
        "runtime_processes": report["execution_truth"].get("runtime_processes", 0),
        "schema": report["schema"],
        "semantic_edges": report["semantic_truth"].get("semantic_edges", 0),
        "shared_evidence_fingerprint": report["shared_evidence"].get("fingerprint"),
        "unresolved_internal_imports": report["semantic_truth"].get("unresolved_internal_import_count", 0),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("EIRA2_SUPERPROBE=" + ("PASS" if report["ok"] else "FAIL"))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
