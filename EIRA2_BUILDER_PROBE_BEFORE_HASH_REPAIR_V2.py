#!/usr/bin/env python3
from pathlib import Path
import hashlib
import shutil
import tempfile

TARGET = Path("tools/eira2_builder_probe.py")
BACKUP = Path("/tmp/eira2_builder_probe.py.pre-before-hash-gate")

OLD_VERIFY = r'''
            target = (root / target_rel).resolve()
            target.relative_to(root)
            if target.exists() and not target.is_file():
                raise RuntimeError("target_not_regular_file:" + target_rel)

            verified.append((src, target, target_rel, actual))
'''

NEW_VERIFY = r'''
            target = (root / target_rel).resolve()
            target.relative_to(root)
            if target.exists() and not target.is_file():
                raise RuntimeError("target_not_regular_file:" + target_rel)

            expected_before = str(row.get("before_sha256") or "").lower()
            existed_before = target.is_file()
            if existed_before:
                if len(expected_before) != 64 or any(c not in "0123456789abcdef" for c in expected_before):
                    raise RuntimeError("before_sha256_required:" + target_rel)
            elif expected_before:
                raise RuntimeError("before_sha256_for_missing_target:" + target_rel)

            verified.append((src, target, target_rel, actual, expected_before, existed_before))
'''

OLD_BACKUP = r'''
        # Backup the state that exists at write time. There is deliberately no
        # expected-before hash gate: legitimate LIVE changes do not block transport.
        for _, target, target_rel, _ in verified:
            backup = backups / target_rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            existed = target.is_file()
            if existed:
                shutil.copy2(target, backup)
            backup_rows.append((target, backup, existed))
'''

NEW_BACKUP = r'''
        # Revalidate the approved LIVE state immediately before backup/write.
        file_hashes = []
        for _, target, target_rel, _, expected_before, existed_before in verified:
            exists_now = target.is_file()
            if exists_now != existed_before:
                raise RuntimeError("live_before_presence_mismatch:" + target_rel)
            before_actual = sha(target) if exists_now else None
            if exists_now and before_actual != expected_before:
                raise RuntimeError("live_before_hash_mismatch:" + target_rel)

            backup = backups / target_rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            if exists_now:
                shutil.copy2(target, backup)
            backup_rows.append((target, backup, exists_now))
            file_hashes.append({
                "path": target_rel,
                "expected_before_sha256": expected_before or None,
                "before_sha256": before_actual,
                "after_sha256": None,
            })
'''

OLD_WRITE = r'''
        for src, target, target_rel, payload_sha in verified:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + f".eira2tmp.{os.getpid()}")
            shutil.copy2(src, tmp)
            os.replace(tmp, target)
            actual_after = sha(target)
            if actual_after != payload_sha:
                raise RuntimeError("post_write_hash_mismatch:" + target_rel)
            applied.append(target_rel)
'''

NEW_WRITE = r'''
        for src, target, target_rel, payload_sha, expected_before, existed_before in verified:
            # Second gate closes the window between backup and replacement.
            exists_now = target.is_file()
            if exists_now != existed_before:
                raise RuntimeError("live_before_presence_mismatch_prewrite:" + target_rel)
            if exists_now and sha(target) != expected_before:
                raise RuntimeError("live_before_hash_mismatch_prewrite:" + target_rel)

            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + f".eira2tmp.{os.getpid()}")
            shutil.copy2(src, tmp)
            os.replace(tmp, target)
            actual_after = sha(target)
            if actual_after != payload_sha:
                raise RuntimeError("post_write_hash_mismatch:" + target_rel)
            applied.append(target_rel)
            for item in file_hashes:
                if item["path"] == target_rel:
                    item["after_sha256"] = actual_after
                    break
'''

OLD_RECEIPT = r'''
            "live_before_hash_gate": False,
            "payload_integrity_verified": True,
'''

NEW_RECEIPT = r'''
            "live_before_hash_gate": True,
            "file_hashes": file_hashes,
            "payload_integrity_verified": True,
'''

def replace_once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f"{label}_anchor_count:{n}")
    return src.replace(old, new, 1)

def main() -> int:
    if not TARGET.is_file():
        raise RuntimeError("target_missing:" + str(TARGET))

    original = TARGET.read_text(encoding="utf-8")
    compile(original, str(TARGET), "exec")

    updated = original
    updated = replace_once(updated, OLD_VERIFY, NEW_VERIFY, "verify")
    updated = replace_once(updated, OLD_BACKUP, NEW_BACKUP, "backup")
    updated = replace_once(updated, OLD_WRITE, NEW_WRITE, "write")
    updated = replace_once(updated, OLD_RECEIPT, NEW_RECEIPT, "receipt")
    compile(updated, str(TARGET), "exec")

    # Only the exact legacy SUCCESS receipt anchor must disappear.
    # Other failure/rollback receipts may legitimately report a false gate.
    if OLD_RECEIPT in updated:
        raise RuntimeError("legacy_success_receipt_survived")
    if NEW_RECEIPT not in updated:
        raise RuntimeError("hardened_success_receipt_missing")
    for required in (
        "before_sha256_required:",
        "live_before_hash_mismatch:",
        "live_before_hash_mismatch_prewrite:",
        '"file_hashes": file_hashes',
    ):
        if required not in updated:
            raise RuntimeError("required_guard_missing:" + required)

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(TARGET.parent),
        prefix=TARGET.name + ".repair.",
        delete=False,
    ) as f:
        f.write(updated)
        f.flush()
        temp = Path(f.name)

    temp.replace(TARGET)

    data = TARGET.read_bytes()
    compile(data.decode("utf-8"), str(TARGET), "exec")
    print("EIRA2_BUILDER_PROBE_BEFORE_HASH_REPAIR=PASS")
    print("BACKUP=" + str(BACKUP))
    print("SHA256=" + hashlib.sha256(data).hexdigest())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
