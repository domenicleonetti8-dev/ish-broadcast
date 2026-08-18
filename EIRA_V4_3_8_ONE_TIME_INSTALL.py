#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

REPO = "domenicleonetti8-dev/ish-broadcast"
SOURCE_COMMIT = "de586975f22d2198b57f33eef67fafd803fddb47"
OUTER_URL = f"https://codeload.github.com/{REPO}/tar.gz/{SOURCE_COMMIT}"
EXPECTED_ARCHIVES = {
    "tar.xz": "5cbe3f7062a071c514fbdbfed97c94f06d115dba101d7261198545432d006ce5",
    "zip": "8faaca2086719ac318c2373e5e502c9ff163d82324a86f07af70a5d0d204dac9",
}
EXPECTED_MANIFEST_SHA256 = "b93d6875aca6eed48a5263352e22fcd9a0d59e0b558784c91c08e47b0b25373d"
EXPECTED_CANONICAL_HASHES = 300
ROOT_NAME = "eira_unified_brain_v4_3_8"


def die(message: str) -> "None":
    raise SystemExit("EIRA v4.3.8 INSTALL BLOCKED: " + message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if p.is_absolute() or not p.parts or any(x in {"", ".", ".."} for x in p.parts):
        die("unsafe archive path: " + name)
    return p


def natural_key(value: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", value)]


def recover_canonical_archive(repo_tar_gz: bytes) -> tuple[str, bytes]:
    direct: list[tuple[str, bytes]] = []
    groups: dict[str, list[tuple[str, bytes]]] = {}
    with tarfile.open(fileobj=io.BytesIO(repo_tar_gz), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            leaf = PurePosixPath(member.name).name
            if leaf.endswith((".tar.xz", ".zip")):
                data = extracted.read()
                if sha256_bytes(data) in EXPECTED_ARCHIVES.values():
                    direct.append((leaf, data))
                continue
            marker = ".b64.part"
            if marker not in leaf:
                continue
            prefix, suffix = leaf.split(marker, 1)
            if not suffix:
                continue
            parent = str(PurePosixPath(member.name).parent)
            key = parent + "/" + prefix + marker
            groups.setdefault(key, []).append((suffix, extracted.read()))
    for name, data in direct:
        digest = sha256_bytes(data)
        for kind, expected in EXPECTED_ARCHIVES.items():
            if digest == expected:
                return kind, data
    for key, pieces in groups.items():
        pieces.sort(key=lambda item: natural_key(item[0]))
        encoded = b"".join(b"".join(chunk.split()) for _, chunk in pieces)
        try:
            data = base64.b64decode(encoded, validate=True)
        except Exception:
            continue
        digest = sha256_bytes(data)
        for kind, expected in EXPECTED_ARCHIVES.items():
            if digest == expected:
                print(f"EIRA v4.3.8: recovered canonical source from Git group {key} parts={len(pieces)}")
                return kind, data
    die("pinned Git commit does not contain the verified v4.3.8 canonical source payload")


def safe_extract_tar_xz(data: bytes, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tf:
        members = tf.getmembers()
        if len(members) > 5000:
            die("canonical tar contains too many entries")
        for member in members:
            rel = safe_rel(member.name)
            target = (destination / Path(*rel.parts)).resolve()
            if target != destination and destination not in target.parents:
                die("canonical tar path escape")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, 0o755)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                if src is None:
                    die("canonical tar regular file unreadable")
                with target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(target, 0o755 if (member.mode & 0o111) else 0o644)
            else:
                die("canonical tar contains link/special entry: " + member.name)


def safe_extract_zip(data: bytes, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > 5000:
            die("canonical zip contains too many entries")
        for info in infos:
            rel = safe_rel(info.filename.rstrip("/")) if info.filename.rstrip("/") else None
            if rel is None:
                continue
            target = (destination / Path(*rel.parts)).resolve()
            if target != destination and destination not in target.parents:
                die("canonical zip path escape")
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode and (unix_mode & 0o170000) == 0o120000:
                die("canonical zip symlink forbidden: " + info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, 0o755)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(target, 0o755 if (unix_mode & 0o111) else 0o644)


def find_root(extracted: Path) -> Path:
    hits = [p for p in extracted.rglob(ROOT_NAME) if p.is_dir() and not p.is_symlink()]
    unique = []
    seen = set()
    for p in hits:
        rp = p.resolve()
        if rp not in seen:
            unique.append(rp)
            seen.add(rp)
    if len(unique) != 1:
        die(f"canonical source root ambiguity count={len(unique)}")
    return unique[0]


def verify_canonical(root: Path) -> None:
    manifest = root / "SHA256SUMS.txt"
    verifier = root / "scripts/verify_internal_hashes.py"
    if not manifest.is_file() or not verifier.is_file():
        die("canonical source verifier/manifest missing")
    got_manifest = sha256_file(manifest)
    if got_manifest != EXPECTED_MANIFEST_SHA256:
        die(f"canonical manifest SHA mismatch got={got_manifest}")
    lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != EXPECTED_CANONICAL_HASHES:
        die(f"canonical manifest count mismatch got={len(lines)}")
    cp = subprocess.run([sys.executable, str(verifier)], cwd=str(root), text=True, capture_output=True)
    sys.stdout.write(cp.stdout)
    sys.stderr.write(cp.stderr)
    if cp.returncode != 0:
        die("canonical internal hash verifier failed")
    required = [
        "INTERNAL_HASH_OK=true",
        "EXPECTED_FILES=300",
        "ACTUAL_FILES=300",
    ]
    if not all(token in cp.stdout for token in required):
        die("canonical verifier did not prove exact 300/300 inventory")
    print("EIRA v4.3.8: CANONICAL_SOURCE_HASHES=300/300 PASS")


def main() -> int:
    if len(sys.argv) != 2:
        die("usage: EIRA_V4_3_8_ONE_TIME_INSTALL.py /media/domenicleonetti/easystore/EIRA/LIVE")
    live = Path(sys.argv[1]).expanduser().resolve()
    if not live.is_dir() or not (live / "main.py").is_file():
        die("LIVE root/main.py missing: " + str(live))
    router = live / "extensions/local_brain/router.py"
    if not router.is_file() or router.is_symlink():
        die("required LIVE local_brain router missing or unsafe")
    print("EIRA v4.3.8: downloading immutable Git source commit " + SOURCE_COMMIT)
    request = urllib.request.Request(OUTER_URL, headers={"User-Agent": "Eira-v4.3.8-one-time-installer"})
    with urllib.request.urlopen(request, timeout=90) as response:
        outer = response.read(20 * 1024 * 1024 + 1)
    if len(outer) > 20 * 1024 * 1024:
        die("Git source archive unexpectedly large")
    kind, canonical = recover_canonical_archive(outer)
    digest = sha256_bytes(canonical)
    if digest != EXPECTED_ARCHIVES[kind]:
        die("recovered canonical payload digest mismatch")
    print(f"EIRA v4.3.8: canonical payload verified kind={kind} sha256={digest}")
    with tempfile.TemporaryDirectory(prefix="eira-v438-omnivenom-") as td:
        extracted = Path(td) / "source"
        extracted.mkdir()
        if kind == "tar.xz":
            safe_extract_tar_xz(canonical, extracted)
        else:
            safe_extract_zip(canonical, extracted)
        root = find_root(extracted)
        verify_canonical(root)
        installer = root / "deploy/install_pi_extension.sh"
        discover = root / "deploy/discover_live_integration.py"
        if not installer.is_file() or not discover.is_file():
            die("canonical deploy path missing")
        print("EIRA v4.3.8: starting transactional OmniVenom LIVE bind")
        cp = subprocess.run(["bash", str(installer), str(live)], cwd=str(root))
        if cp.returncode != 0:
            die(f"transactional LIVE install failed rc={cp.returncode}")
        cp = subprocess.run([sys.executable, str(discover), str(live)], cwd=str(root))
        if cp.returncode != 0:
            die(f"post-install LIVE discovery failed rc={cp.returncode}")
    print("EIRA_V4_3_8_OMNIVENOM_INSTALL=PASS")
    print("CANONICAL_SOURCE_HASHES=300/300")
    print("NEXT=python3 main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
