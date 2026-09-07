#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_full_brain_reconstruction_v1"
ROOT_DEFAULT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
OUT_REL = Path("eira_probe/full_brain_reconstruction")
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "node_modules", "dist", "build"}
AR_WORDS = ("ar", "hologram", "neural", "neuron", "brain", "atlas", "viewer", "webxr", "usdz", "three", "scene", "organism")
BRIDGE_WORDS = ("bridge", "router", "gateway", "transport", "probe", "watcher", "registry", "supervisor", "delivery", "ingress", "outward", "executor")


def jbytes(v: Any) -> bytes:
    return (json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = jbytes(value)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def iter_files(root: Path, out_root: Path):
    for current, dirs, files in os.walk(root):
        base = Path(current)
        dirs[:] = [d for d in dirs if d not in SKIP_PARTS and not (base / d).resolve().is_relative_to(out_root.resolve())]
        for name in files:
            p = base / name
            try:
                if p.is_file() and not p.is_symlink() and not p.resolve().is_relative_to(out_root.resolve()):
                    yield p
            except Exception:
                continue


def classify(path: str) -> list[str]:
    s = path.casefold()
    tags = []
    for word in BRIDGE_WORDS:
        if word in s:
            tags.append(word)
    if any(w in s for w in AR_WORDS):
        tags.append("ar_hologram_related")
    if s.startswith("eira2/extensions/"):
        tags.append("extension")
    if "manifest" in s:
        tags.append("manifest")
    if s.endswith("main.py") or s.endswith("__main__.py"):
        tags.append("entrypoint")
    return sorted(set(tags))


def inventory(root: Path, out_root: Path) -> dict[str, Any]:
    rows = []
    cursor = 0
    errors = []
    for p in sorted(iter_files(root, out_root), key=lambda x: rel(x, root)):
        rp = rel(p, root)
        try:
            st = p.stat()
            size = st.st_size
            digest = sha256_file(p)
            rows.append({
                "path": rp,
                "absolute_path": str(p.resolve()),
                "bytes": size,
                "sha256": digest,
                "virtual_byte_start": cursor,
                "virtual_byte_end_exclusive": cursor + size,
                "suffix": p.suffix.casefold(),
                "tags": classify(rp),
            })
            cursor += size
        except Exception as exc:
            errors.append({"path": rp, "error": f"{type(exc).__name__}:{exc}"})
    return {"schema": "eira2_byte_ledger_v1", "file_count": len(rows), "total_bytes": cursor, "files": rows, "errors": errors}


def module_for(path: Path, root: Path) -> str | None:
    try:
        rp = path.resolve().relative_to(root.resolve())
    except Exception:
        return None
    if rp.suffix != ".py":
        return None
    parts = list(rp.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else None


def semantic_graph(root: Path, ledger: dict[str, Any]) -> dict[str, Any]:
    py_paths = [root / row["path"] for row in ledger["files"] if row["suffix"] == ".py"]
    modules = {m: rel(p, root) for p in py_paths if (m := module_for(p, root))}
    known = set(modules)
    edges = []
    unresolved = []
    calls = []
    defs = []
    for p in py_paths:
        src = module_for(p, root)
        if not src:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=str(p))
        except Exception as exc:
            unresolved.append({"source": src, "kind": "parse_error", "error": f"{type(exc).__name__}:{exc}"})
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defs.append({"module": src, "name": node.name, "kind": type(node).__name__, "line": getattr(node, "lineno", None)})
            elif isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    parts = []
                    cur = node.func
                    while isinstance(cur, ast.Attribute):
                        parts.append(cur.attr)
                        cur = cur.value
                    if isinstance(cur, ast.Name):
                        parts.append(cur.id)
                    if parts:
                        name = ".".join(reversed(parts))
                if name:
                    calls.append({"module": src, "call": name, "line": getattr(node, "lineno", None)})
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("eira2"):
                        target = a.name
                        resolved = target in known
                        edges.append({"source": src, "target": target, "kind": "import", "resolved": resolved})
                        if not resolved:
                            unresolved.append({"source": src, "target": target, "kind": "unresolved_import"})
            elif isinstance(node, ast.ImportFrom):
                target = node.module or ""
                if node.level:
                    base = src.split(".")[:-1]
                    if node.level > 1:
                        base = base[:-(node.level - 1)] if len(base) >= node.level - 1 else []
                    target = ".".join([*base, *target.split(".")]) if target else ".".join(base)
                if target.startswith("eira2"):
                    resolved = target in known or any(k.startswith(target + ".") for k in known)
                    edges.append({"source": src, "target": target, "kind": "from", "resolved": resolved})
                    if not resolved:
                        unresolved.append({"source": src, "target": target, "kind": "unresolved_import"})
    return {
        "schema": "eira2_full_semantic_graph_v1",
        "module_count": len(modules),
        "modules": modules,
        "edge_count": len(edges),
        "edges": edges,
        "definitions": defs,
        "calls": calls,
        "unresolved": unresolved,
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def superprobe_truth(root: Path) -> dict[str, Any]:
    base = root / "eira_probe"
    report = load_json(base / "eira2_superprobe_report.json") or {}
    ev = base / "eira2_superprobe_evidence"
    evidence = {}
    if ev.is_dir():
        for p in sorted(ev.glob("*.json")):
            evidence[p.name] = load_json(p)
    return {"report": report, "evidence": evidence}


def runtime_graph(sp: dict[str, Any]) -> dict[str, Any]:
    execution = sp.get("evidence", {}).get("execution_truth.json") or {}
    return {
        "schema": "eira2_runtime_graph_v1",
        "source": "superprobe_execution_truth",
        "runtime_processes": execution.get("runtime_processes"),
        "processes": execution.get("processes", []),
        "listeners": execution.get("listeners", []),
        "listener_count": execution.get("listener_count"),
        "truth_label": "runtime_observed" if execution else "unknown",
    }


def ar_sources(ledger: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    out = []
    for row in ledger["files"]:
        p = row["path"]
        if "ar_hologram_related" not in row["tags"]:
            continue
        entry = {k: row[k] for k in ("path", "bytes", "sha256", "tags")}
        if Path(p).suffix.casefold() in {".py", ".js", ".mjs", ".html", ".json", ".css"} and row["bytes"] <= 5_000_000:
            try:
                text = (root / p).read_text(encoding="utf-8", errors="replace")
                ids = sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_.:-]{2,80}", text)))
                entry["sample_identifiers"] = ids[:200]
            except Exception:
                pass
        out.append(entry)
    return out


def bridge_map(ledger: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    files = [r for r in ledger["files"] if any(t in r["tags"] for t in BRIDGE_WORDS)]
    modules = {m: p for m, p in semantic.get("modules", {}).items() if any(w in p.casefold() for w in BRIDGE_WORDS)}
    edges = [e for e in semantic.get("edges", []) if e.get("source") in modules or e.get("target") in modules]
    return {"schema": "eira2_bridge_map_v1", "files": files, "modules": modules, "semantic_edges": edges, "truth_label": "static_evidence"}


def orchestration(root: Path, sp: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for module, path in semantic.get("modules", {}).items():
        s = path.casefold()
        score = sum(1 for w in ("ingress", "router", "history", "analysis", "capabil", "constellation", "reason", "verif", "identity", "delivery", "outward", "response", "supervisor") if w in s)
        if score:
            candidates.append({"module": module, "path": path, "score": score})
    candidates.sort(key=lambda r: (-r["score"], r["path"]))
    return {
        "schema": "eira2_canonical_orchestration_v1",
        "truth_policy": "Only explicitly evidenced relationships are canonical. Candidate ordering is a reconstruction aid, not invented authority.",
        "superprobe_schema": sp.get("report", {}).get("schema"),
        "superprobe_ok": sp.get("report", {}).get("ok"),
        "candidate_orchestration_components": candidates,
        "semantic_edges": semantic.get("edges", []),
        "truth_label": "mixed_superprobe_and_static_evidence",
    }


def node_map(ledger: dict[str, Any], semantic: dict[str, Any], sp: dict[str, Any]) -> dict[str, Any]:
    organism = sp.get("evidence", {}).get("organism_truth.json") or {}
    nodes = []
    for module, path in semantic.get("modules", {}).items():
        nodes.append({"id": module, "kind": "python_module", "physical_path": path, "truth_label": "static_evidence"})
    return {
        "schema": "eira2_node_map_v1",
        "nodes": nodes,
        "organism_truth": organism,
        "addressable_node_count": organism.get("addressable_node_count"),
        "road_count": organism.get("road_count"),
        "truth_label": "superprobe_plus_static_evidence",
    }


def neural_ar_fusion(ledger: dict[str, Any], sp: dict[str, Any], root: Path) -> dict[str, Any]:
    organism = sp.get("evidence", {}).get("organism_truth.json") or {}
    sources = ar_sources(ledger, root)
    return {
        "schema": "eira2_neural_ar_fusion_map_v1",
        "canonical_neural_authority": organism.get("authority"),
        "canonical_neural_overview": organism.get("overview"),
        "ar_hologram_source_files": sources,
        "layout_identity_verified": organism.get("layout_identity_verified", False),
        "layout_identity_status": organism.get("layout_identity_status", "unknown"),
        "correlation_policy": "AR/hologram identifiers are evidence candidates only until matched to canonical neural node ids.",
    }


def brain_map(ledger: dict[str, Any], semantic: dict[str, Any], bridges: dict[str, Any], nodes: dict[str, Any], runtime: dict[str, Any], fusion: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "eira2_brain_map_v1",
        "physical": {"file_count": ledger["file_count"], "total_bytes": ledger["total_bytes"]},
        "semantic": {"module_count": semantic["module_count"], "edge_count": semantic["edge_count"], "unresolved_count": len(semantic["unresolved"])},
        "bridges": {"file_count": len(bridges["files"]), "module_count": len(bridges["modules"])},
        "nodes": {"module_nodes": len(nodes["nodes"]), "addressable_neural_nodes": nodes.get("addressable_node_count"), "neural_roads": nodes.get("road_count")},
        "runtime": {"processes": runtime.get("runtime_processes"), "listeners": runtime.get("listener_count")},
        "ar_hologram": {"source_files": len(fusion.get("ar_hologram_source_files", [])), "layout_identity_verified": fusion.get("layout_identity_verified")},
        "truth_policy": "verified/observed/static/inferred/unknown/unresolved remain distinct",
    }


def manifest(out: Path, artifacts: dict[str, dict[str, Any]], root: Path, sp: dict[str, Any]) -> dict[str, Any]:
    rows = [{"name": k, **v} for k, v in sorted(artifacts.items())]
    fp = hashlib.sha256(jbytes(rows)).hexdigest()
    return {
        "schema": SCHEMA,
        "root": str(root),
        "generated_unix": time.time(),
        "superprobe_evidence_fingerprint": sp.get("report", {}).get("evidence_fingerprint"),
        "artifact_count": len(rows),
        "artifacts": rows,
        "reconstruction_fingerprint": fp,
        "sandbox": str(out),
        "live_modified": False,
        "code_executed_from_reconstruction": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    ap.add_argument("--request", type=Path)
    args = ap.parse_args()
    root = args.root.expanduser().resolve()
    if not (root / "eira2").is_dir():
        raise SystemExit("EIRA2_ROOT_MISSING")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = root / OUT_REL / stamp
    out.mkdir(parents=True, exist_ok=True)

    probe = root / "tools/eira2_superprobe_engine.py"
    if probe.is_file():
        subprocess.run([sys.executable, str(probe), "--root", str(root)], cwd=root, check=False)

    sp = superprobe_truth(root)
    ledger = inventory(root, root / OUT_REL)
    sem = semantic_graph(root, ledger)
    runtime = runtime_graph(sp)
    bridges = bridge_map(ledger, sem)
    nodes = node_map(ledger, sem, sp)
    fusion = neural_ar_fusion(ledger, sp, root)
    orch = orchestration(root, sp, sem)
    brain = brain_map(ledger, sem, bridges, nodes, runtime, fusion)

    artifacts = {}
    artifacts["byte_ledger.json"] = write_json(out / "byte_ledger.json", ledger)
    artifacts["semantic_graph.json"] = write_json(out / "semantic_graph.json", sem)
    artifacts["runtime_graph.json"] = write_json(out / "runtime_graph.json", runtime)
    artifacts["bridge_map.json"] = write_json(out / "bridge_map.json", bridges)
    artifacts["node_map.json"] = write_json(out / "node_map.json", nodes)
    artifacts["neural_ar_fusion_map.json"] = write_json(out / "neural_ar_fusion_map.json", fusion)
    artifacts["canonical_orchestration.json"] = write_json(out / "canonical_orchestration.json", orch)
    artifacts["brain_map.json"] = write_json(out / "brain_map.json", brain)

    request_info = None
    if args.request and args.request.is_file():
        request_info = {"path": str(args.request), "sha256": sha256_file(args.request), "bytes": args.request.stat().st_size}
    reconstruction_manifest = manifest(out, artifacts, root, sp)
    reconstruction_manifest["request"] = request_info
    artifacts["sandbox_reconstruction_manifest.json"] = write_json(out / "sandbox_reconstruction_manifest.json", reconstruction_manifest)

    receipt = {
        "schema": "eira2_full_brain_forensic_receipt_v1",
        "ok": bool(sp.get("report", {}).get("ok")),
        "superprobe_schema": sp.get("report", {}).get("schema"),
        "superprobe_ok": sp.get("report", {}).get("ok"),
        "package_identity_ok": sp.get("report", {}).get("package_identity_ok"),
        "organism_ok": sp.get("report", {}).get("organism_ok"),
        "unresolved_internal_imports": sp.get("report", {}).get("unresolved_internal_imports"),
        "sandbox": str(out),
        "file_count": ledger["file_count"],
        "total_bytes": ledger["total_bytes"],
        "semantic_modules": sem["module_count"],
        "semantic_edges": sem["edge_count"],
        "semantic_unresolved": len(sem["unresolved"]),
        "ar_hologram_sources": len(fusion.get("ar_hologram_source_files", [])),
        "live_modified": False,
    }
    artifacts["forensic_receipt.json"] = write_json(out / "forensic_receipt.json", receipt)

    final_manifest = manifest(out, artifacts, root, sp)
    final_manifest["request"] = request_info
    write_json(out / "sandbox_reconstruction_manifest.json", final_manifest)

    print(json.dumps({
        "EIRA2_FULL_BRAIN_RECONSTRUCTION": "PASS",
        "sandbox": str(out),
        "file_count": ledger["file_count"],
        "total_bytes": ledger["total_bytes"],
        "semantic_modules": sem["module_count"],
        "semantic_edges": sem["edge_count"],
        "semantic_unresolved": len(sem["unresolved"]),
        "ar_hologram_sources": len(fusion.get("ar_hologram_source_files", [])),
        "superprobe_ok": sp.get("report", {}).get("ok"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
