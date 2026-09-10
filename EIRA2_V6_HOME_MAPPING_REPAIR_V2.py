#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib
import shutil

TARGET = Path("extensions/engineering_worker_ai/plugin.py")
BACKUP = Path("/tmp/plugin.py.pre-v6-home-map-fix")

OLD = '    home = Path.home()\n    # Tool trees are read-only. The host HOME itself is never exposed as HOME.\n    for p in (home / ".opencode", home / ".local"):\n        if p.exists():\n            argv += ["--ro-bind", str(p), str(p)]\n    ocfg = home / ".config/opencode"\n    if ocfg.exists():\n        argv += ["--ro-bind", str(ocfg), str(ocfg)]\n'
NEW = '    home = Path.home()\n    # Keep absolute tool paths readable, but give OpenCode a coherent private HOME.\n    opencode_home = home / ".opencode"\n    if opencode_home.exists():\n        argv += ["--ro-bind", str(opencode_home), str(opencode_home)]\n        argv += ["--ro-bind", str(opencode_home), "/home/eira/.opencode"]\n\n    local_home = home / ".local"\n    if local_home.exists():\n        argv += ["--ro-bind", str(local_home), str(local_home)]\n\n    ocfg = home / ".config/opencode"\n    if ocfg.exists():\n        argv += ["--dir", "/home/eira/.config"]\n        argv += ["--ro-bind", str(ocfg), "/home/eira/.config/opencode"]\n\n    # Writable private HOME state/cache; never mapped back to the host HOME.\n    argv += [\n        "--dir", "/home/eira/.cache",\n        "--dir", "/home/eira/.local",\n        "--dir", "/home/eira/.local/state",\n        "--dir", "/home/eira/.local/share",\n    ]\n'

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    if not TARGET.is_file():
        raise RuntimeError("target_missing")

    source = TARGET.read_text(encoding="utf-8")
    if source.count(OLD) != 1:
        raise RuntimeError("home_mapping_anchor_not_exactly_once")
    if '"HOME": "/home/eira"' not in source:
        raise RuntimeError("private_home_contract_missing")

    updated = source.replace(OLD, NEW, 1)

    required = (
        'str(opencode_home), str(opencode_home)',
        'str(opencode_home), "/home/eira/.opencode"',
        'str(local_home), str(local_home)',
        '"/home/eira/.config/opencode"',
        '"/home/eira/.cache"',
        '"/home/eira/.local/state"',
        '"/home/eira/.local/share"',
    )
    if OLD in updated:
        raise RuntimeError("legacy_mapping_survived")
    for token in required:
        if token not in updated:
            raise RuntimeError("required_mapping_missing:" + token)

    compile(updated, str(TARGET), "exec")
    shutil.copy2(TARGET, BACKUP)

    tmp = TARGET.with_name(TARGET.name + ".v6-home-map.tmp")
    tmp.write_text(updated, encoding="utf-8")
    compile(tmp.read_text(encoding="utf-8"), str(TARGET), "exec")
    tmp.replace(TARGET)

    print("V6_HOME_MAPPING_REPAIR=PASS")
    print("BACKUP=" + str(BACKUP))
    print("SHA256=" + sha(TARGET))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
