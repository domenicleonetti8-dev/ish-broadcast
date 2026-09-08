#!/usr/bin/env python3
from __future__ import annotations

import base64, hashlib, json, lzma, re, subprocess
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "eira2_blueprint_payload_manifest_v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_rel(value: str) -> str:
    p = Path(str(value or ""))
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise RuntimeError("unsafe_relative_path:" + value)
    return p.as_posix()


def _git_blob(repo: Path, commit: str, repo_path: str) -> bytes:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", str(commit or "")):
        raise RuntimeError("source_commit_invalid")
    rel = _safe_rel(repo_path)
    p = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{rel}"],
        capture_output=True, timeout=180, check=False,
    )
    if p.returncode:
        raise RuntimeError("source_blob_missing:" + p.stderr[-1200:].decode(errors="replace"))
    return p.stdout


def _decode_chunk(text: bytes, encoding: str) -> bytes:
    raw = b"".join(text.split())
    if encoding == "base64":
        return base64.b64decode(raw, validate=True)
    if encoding == "base64_lzma":
        return lzma.decompress(base64.b64decode(raw, validate=True))
    raise RuntimeError("unsupported_chunk_encoding:" + encoding)


def materialize_source(repo: Path, source: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Return source bytes while preserving every legacy source contract.

    Legacy source: {commit,path,sha256?} -> exact git blob, unchanged behavior.
    Manifest source: {manifest:{commit,path}} -> verified reconstruction from chunk files.
    """
    manifest_ref = source.get("manifest")
    if not manifest_ref:
        raw = _git_blob(repo, str(source.get("commit") or ""), str(source.get("path") or ""))
        expected = str(source.get("sha256") or "").lower()
        actual = _sha256(raw)
        if expected and actual != expected:
            raise RuntimeError("source_sha256_mismatch")
        return raw, {
            "mode": "legacy_git_blob",
            "sha256": actual,
            "bytes": len(raw),
            "backward_compatible": True,
        }

    if not isinstance(manifest_ref, dict):
        raise RuntimeError("manifest_reference_invalid")
    manifest_raw = _git_blob(repo, str(manifest_ref.get("commit") or ""), str(manifest_ref.get("path") or ""))
    manifest = json.loads(manifest_raw.decode("utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeError("payload_manifest_schema_invalid")

    chunks = manifest.get("chunks") or []
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("payload_manifest_chunks_missing")

    out = bytearray()
    verified = []
    for index, row in enumerate(chunks):
        if not isinstance(row, dict):
            raise RuntimeError(f"payload_chunk_invalid:{index}")
        commit = str(row.get("commit") or manifest_ref.get("commit") or "")
        path = str(row.get("path") or "")
        encoded = _git_blob(repo, commit, path)
        encoded_expected = str(row.get("encoded_sha256") or "").lower()
        if encoded_expected and _sha256(encoded) != encoded_expected:
            raise RuntimeError(f"payload_chunk_encoded_sha256_mismatch:{index}")
        decoded = _decode_chunk(encoded, str(row.get("encoding") or "base64"))
        decoded_expected = str(row.get("sha256") or "").lower()
        decoded_actual = _sha256(decoded)
        if decoded_expected and decoded_actual != decoded_expected:
            raise RuntimeError(f"payload_chunk_sha256_mismatch:{index}")
        expected_bytes = row.get("bytes")
        if expected_bytes is not None and len(decoded) != int(expected_bytes):
            raise RuntimeError(f"payload_chunk_size_mismatch:{index}")
        out.extend(decoded)
        verified.append({"index": index, "path": path, "sha256": decoded_actual, "bytes": len(decoded)})

    payload = bytes(out)
    expected = str(manifest.get("sha256") or source.get("sha256") or "").lower()
    actual = _sha256(payload)
    if expected and actual != expected:
        raise RuntimeError("payload_manifest_sha256_mismatch")
    expected_bytes = manifest.get("bytes")
    if expected_bytes is not None and len(payload) != int(expected_bytes):
        raise RuntimeError("payload_manifest_size_mismatch")

    return payload, {
        "mode": "chunk_manifest",
        "schema": MANIFEST_SCHEMA,
        "sha256": actual,
        "bytes": len(payload),
        "chunks": verified,
        "backward_compatible": True,
    }
