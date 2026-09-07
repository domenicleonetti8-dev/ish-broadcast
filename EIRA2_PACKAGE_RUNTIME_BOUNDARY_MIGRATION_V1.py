#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import py_compile
import re
import shutil
import sys
import time
from pathlib import Path

RUNTIME_NAMESPACE = "eira_probe"
RECEIPT = Path("eira_probe/eira2_package_runtime_boundary_receipt.json")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    root = Path.cwd().resolve()
    package_file = root / "eira2" / "operations" / "package_identity.py"
    manifest_file = root / "eira2-package-manifest.json"
    if not (root / "eira2" / "__main__.py").is_file():
        raise RuntimeError("not_eira2_project_root")
    if not package_file.is_file():
        raise RuntimeError("package_identity_missing")
    if not manifest_file.is_file():
        raise RuntimeError("package_manifest_missing")

    old_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    source_commit_sha = str(old_manifest.get("source_commit_sha") or "").strip()
    if not source_commit_sha:
        raise RuntimeError("source_commit_sha_missing_from_existing_manifest")

    original = package_file.read_text(encoding="utf-8")
    if '"eira_probe"' in original or "'eira_probe'" in original:
        changed = False
        migrated = original
    else:
        pattern = re.compile(r"(_EXCLUDED_PARTS\s*=\s*\{)(.*?)(\}\s*)", re.S)
        match = pattern.search(original)
        if not match:
            raise RuntimeError("excluded_parts_definition_not_found")
        body = match.group(2).rstrip()
        if body and not body.rstrip().endswith(","):
            body += ","
        body += '\n    "eira_probe",'
        migrated = original[:match.start()] + match.group(1) + body + match.group(3) + original[match.end():]
        changed = True

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = package_file.with_name(package_file.name + f".retired_pre_runtime_boundary_{stamp}")
    manifest_backup = manifest_file.with_name(manifest_file.name + f".retired_pre_runtime_boundary_{stamp}")

    if changed:
        temp = Path("/tmp/eira2_package_identity_runtime_boundary.py")
        temp.write_text(migrated, encoding="utf-8")
        py_compile.compile(str(temp), doraise=True)
        shutil.copy2(package_file, backup)
        shutil.copy2(manifest_file, manifest_backup)
        atomic_write(package_file, migrated)

    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "eira2.operations.package_identity":
            del sys.modules[name]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    module = importlib.import_module("eira2.operations.package_identity")
    write_manifest = getattr(module, "write_package_manifest", None)
    verify_manifest = getattr(module, "verify_package_manifest", None)
    if not callable(write_manifest) or not callable(verify_manifest):
        raise RuntimeError("package_identity_contract_unavailable")

    manifest = write_manifest(root, source_commit_sha=source_commit_sha)
    verified = verify_manifest(root)

    receipt = {
        "schema": "eira2_package_runtime_boundary_migration_v1",
        "ok": True,
        "runtime_namespace_excluded": RUNTIME_NAMESPACE,
        "package_identity_changed": changed,
        "package_identity_path": str(package_file),
        "package_identity_backup": str(backup) if changed else None,
        "manifest_backup": str(manifest_backup) if changed else None,
        "manifest_path": str(manifest_file),
        "source_commit_sha": verified.get("source_commit_sha"),
        "package_tree_sha256": verified.get("package_tree_sha256"),
        "file_count": verified.get("file_count"),
        "unsealed_immutable_files_allowed": verified.get("unsealed_immutable_files_allowed"),
    }
    atomic_write(root / RECEIPT, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("EIRA2_RUNTIME_PACKAGE_BOUNDARY=PASS")
    print("EIRA2_PACKAGE_IDENTITY=VERIFIED")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
