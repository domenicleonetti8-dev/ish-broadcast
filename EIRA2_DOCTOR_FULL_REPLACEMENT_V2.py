TARGET = "eira2/operations/doctor.py"
NEW = '''from __future__ import annotations

import argparse
import ast
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..contracts import Health, RuntimeContext, ServiceSpec, ServiceState
from ..registry.graph import NodeRegistryService
from ..registry.manifests import Manifest, discover

_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "var", "eira_probe"}

@dataclass(slots=True)
class DoctorReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, int | str | bool] = field(default_factory=dict)
    started_at_unix: float = 0.0
    finished_at_unix: float = 0.0
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

def _iter_files(root: Path, suffix: str) -> Iterable[Path]:
    for path in root.rglob(f"*{suffix}"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in _EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.is_file():
            yield path

def _module_file(project_root: Path, module: str) -> Path | None:
    parts = module.split(".")
    direct = project_root.joinpath(*parts).with_suffix(".py")
    package = project_root.joinpath(*parts) / "__init__.py"
    if direct.is_file(): return direct
    if package.is_file(): return package
    return None

def _declared_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

def _validate_manifest_graph(manifests: list[Manifest]) -> list[str]:
    errors = []
    by_name = {manifest.name: manifest for manifest in manifests}
    for manifest in manifests:
        for dependency in manifest.dependencies:
            if dependency == manifest.name:
                errors.append(f"manifest_self_dependency:{manifest.name}")
            elif dependency not in by_name:
                errors.append(f"manifest_dependency_missing:{manifest.name}:{dependency}")
    visiting=set(); visited=set()
    def visit(name: str) -> None:
        if name in visited: return
        if name in visiting:
            errors.append(f"manifest_dependency_cycle:{name}"); return
        visiting.add(name)
        manifest=by_name.get(name)
        if manifest is not None:
            for dependency in manifest.dependencies:
                if dependency in by_name: visit(dependency)
        visiting.remove(name); visited.add(name)
    for name in sorted(by_name): visit(name)
    return errors

def audit_project(project_root: Path, *, state_path: Path|None=None, registry_snapshot: dict[str,Any]|None=None, neural_overview: dict[str,Any]|None=None, neural_fibers: Iterable[dict[str,Any]]|None=None, run_external_checks: bool=False) -> DoctorReport:
    root=project_root.expanduser().resolve()
    report=DoctorReport(ok=False, started_at_unix=time.time())
    errors=report.errors; warnings=report.warnings
    if not (root/"pyproject.toml").is_file(): errors.append("project_pyproject_missing")
    python_files=sorted(_iter_files(root,".py")); compiled=0
    for path in python_files:
        try:
            source=path.read_text(encoding="utf-8",errors="strict")
            compile(source,str(path),"exec",dont_inherit=True); ast.parse(source,filename=str(path)); compiled+=1
        except (OSError,UnicodeError,SyntaxError) as error:
            errors.append(f"python_syntax:{path.relative_to(root)}:{type(error).__name__}:{error}")
    report.checks["python_files"]=len(python_files); report.checks["python_compiled"]=compiled
    json_files=sorted(_iter_files(root,".json")); parsed_json=0
    for path in json_files:
        try: json.loads(path.read_text(encoding="utf-8",errors="strict")); parsed_json+=1
        except (OSError,UnicodeError,json.JSONDecodeError) as error:
            errors.append(f"json_invalid:{path.relative_to(root)}:{type(error).__name__}:{error}")
    report.checks["json_files"]=len(json_files); report.checks["json_parsed"]=parsed_json
    manifest_dir=root/"manifests"; manifests=[]
    if not manifest_dir.is_dir(): errors.append("manifest_directory_missing")
    else:
        try: manifests=discover(manifest_dir)
        except Exception as error: errors.append(f"manifest_discovery_failed:{type(error).__name__}:{error}")
        else:
            errors.extend(_validate_manifest_graph(manifests))
            for manifest in manifests:
                module_path=_module_file(root,manifest.module)
                if module_path is None:
                    errors.append(f"manifest_module_missing:{manifest.name}:{manifest.module}"); continue
                try: symbols=_declared_symbols(module_path)
                except Exception as error:
                    errors.append(f"manifest_module_unreadable:{manifest.name}:{type(error).__name__}:{error}"); continue
                if manifest.factory not in symbols:
                    errors.append(f"manifest_factory_missing:{manifest.name}:{manifest.module}:{manifest.factory}")
    report.checks["manifests"]=len(manifests)
    preservation=root/"preservation_contract.json"
    if not preservation.is_file(): errors.append("preservation_contract_missing")
    else:
        try:
            contract=json.loads(preservation.read_text(encoding="utf-8"))
            if contract.get("schema")!="eira2_functional_preservation_contract_v1": errors.append("preservation_contract_schema_invalid")
            if int(contract.get("inventory_entries") or 0)!=76056: errors.append("preservation_inventory_baseline_invalid")
        except Exception as error: errors.append(f"preservation_contract_invalid:{type(error).__name__}:{error}")
    if state_path is not None:
        state=state_path.expanduser().resolve()
        if state.exists():
            try:
                db=sqlite3.connect(f"file:{state}?mode=ro",uri=True,timeout=3.0)
                try:
                    integrity=db.execute("PRAGMA integrity_check").fetchone()
                    if not integrity or str(integrity[0]).casefold()!="ok": errors.append(f"sqlite_integrity_failed:{integrity}")
                    foreign=db.execute("PRAGMA foreign_key_check").fetchall()
                    if foreign: errors.append(f"sqlite_foreign_key_failures:{len(foreign)}")
                    versions=db.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
                    if not versions: errors.append("sqlite_schema_version_missing")
                    report.checks["sqlite_schema_version"]=int(versions[-1][0]) if versions else 0
                finally: db.close()
            except (sqlite3.Error,OSError) as error: errors.append(f"sqlite_check_failed:{type(error).__name__}:{error}")
        else: warnings.append("sqlite_state_not_created_yet")
    if registry_snapshot is not None:
        nodes={str(row.get("name")) for row in registry_snapshot.get("nodes",[]) if isinstance(row,dict)}
        bridges=[row for row in registry_snapshot.get("bridges",[]) if isinstance(row,dict)]
        for bridge in bridges:
            source=str(bridge.get("source") or ""); target=str(bridge.get("target") or "")
            if source not in nodes or target not in nodes: errors.append(f"registry_orphan_bridge:{source}:{target}")
            if bridge.get("kind")=="anatomical_membership" and bridge.get("conductive") is True: errors.append(f"registry_false_conductivity:{source}:{target}")
        report.checks["registry_nodes"]=len(nodes); report.checks["registry_bridges"]=len(bridges)
    if neural_overview is not None:
        if neural_overview.get("all_inventory_entries_have_neurons") is not True: errors.append("neural_inventory_coverage_false")
        if neural_overview.get("structural_fibers_are_conductive") is not False: errors.append("neural_structural_fiber_truth_violation")
        if neural_overview.get("conductive_fibers_require_evidence") is not True: errors.append("neural_conductive_evidence_rule_missing")
        count=int(neural_overview.get("inventory_neuron_count") or 0); source=str(neural_overview.get("inventory_source") or "")
        authoritative=bool(source and source!="filesystem_scan_fallback")
        if authoritative and count<76056: errors.append(f"neural_inventory_below_canonical_baseline:{count}")
        report.checks["neural_inventory_neurons"]=count; report.checks["neural_inventory_source"]=source; report.checks["neural_inventory_authoritative"]=authoritative
    if neural_fibers is not None:
        fiber_count=0; conductive=0
        for fiber in neural_fibers:
            fiber_count+=1
            if fiber.get("conductive"):
                conductive+=1
                if not str(fiber.get("evidence") or "").strip(): errors.append("neural_conductive_fiber_without_evidence")
                if fiber.get("kind")=="anatomical_membership": errors.append("neural_membership_fiber_conductive")
        report.checks["neural_fibers_checked"]=fiber_count; report.checks["neural_conductive_fibers_checked"]=conductive
    if run_external_checks:
        node=shutil.which("node"); js=root/"eira2"/"neural"/"web"/"app.js"
        if js.is_file():
            if node:
                completed=subprocess.run([node,"--check",str(js)],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30,check=False)
                if completed.returncode!=0: errors.append("javascript_syntax_failed:"+completed.stdout[-1200:].replace("\\n"," | "))
                report.checks["javascript_syntax"]=completed.returncode==0
            else:
                warnings.append("node_not_available_for_javascript_syntax"); report.checks["javascript_syntax"]="not_available"
    report.finished_at_unix=time.time(); report.ok=not errors; report.checks["errors"]=len(errors); report.checks["warnings"]=len(warnings)
    return report

class DoctorService:
    spec=ServiceSpec("operations.doctor",required=True,dependencies=("operations.health","registry.graph"),start_timeout_seconds=90.0,stop_timeout_seconds=10.0)
    def __init__(self, project_root: Path, state_path: Path) -> None:
        self.project_root=project_root.expanduser().resolve(); self.state_path=state_path.expanduser().resolve()
        self._state=ServiceState.DECLARED; self._last:DoctorReport|None=None; self._context:RuntimeContext|None=None
    async def start(self, context: RuntimeContext) -> None:
        self._context=context; report=self.evaluate(); self._last=report
        if not report.ok:
            self._state=ServiceState.FAILED; raise RuntimeError("doctor_startup_failed:"+";".join(report.errors[:8]))
        self._state=ServiceState.READY
    async def stop(self)->None:
        self._context=None; self._state=ServiceState.STOPPED
    async def health(self)->Health:
        detail="not_run"
        if self._last is not None: detail=f"ok={self._last.ok} errors={len(self._last.errors)} warnings={len(self._last.warnings)}"
        return Health(self._state,detail)
    def evaluate(self, *, project_root:Path|None=None, state_path:Path|None=None)->DoctorReport:
        registry_snapshot=None; neural_overview=None; neural_fibers=None
        if self._context is not None:
            try:
                registry=self._context.get_service("registry.graph")
                if isinstance(registry,NodeRegistryService): registry_snapshot=registry.snapshot()
            except Exception: registry_snapshot=None
            try:
                neural=self._context.get_service("interfaces.neural_ui"); surface=getattr(neural,"surface",None); atlas=getattr(surface,"atlas",None)
                if atlas is not None:
                    neural_overview=atlas.overview(); neural_fibers=[row.as_dict() for row in atlas.fibers]
            except Exception:
                neural_overview=None; neural_fibers=None
        report=audit_project(project_root or self.project_root,state_path=state_path if state_path is not None else self.state_path,registry_snapshot=registry_snapshot,neural_overview=neural_overview,neural_fibers=neural_fibers,run_external_checks=False)
        self._last=report; return report
    def last_report(self)->dict[str,Any]:
        return self._last.as_dict() if self._last is not None else {"ok":False,"error":"doctor_not_run"}

def main()->int:
    parser=argparse.ArgumentParser(description="EIRA 2.0 structural Doctor")
    parser.add_argument("--project-root",type=Path,default=Path.cwd()); parser.add_argument("--state",type=Path,default=None); parser.add_argument("--no-state",action="store_true"); parser.add_argument("--external",action="store_true"); parser.add_argument("--strict",action="store_true")
    args=parser.parse_args(); state=None if args.no_state else args.state
    report=audit_project(args.project_root,state_path=state,run_external_checks=args.external)
    print(json.dumps(report.as_dict(),indent=2,sort_keys=True))
    if not report.ok: return 1
    if args.strict and report.warnings: return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
'''
