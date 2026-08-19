from __future__ import annotations
import hashlib
import re
from pathlib import PurePosixPath

_TOKEN = re.compile(r"[a-z0-9]+")


def norm(value: object) -> str:
    return " ".join(_TOKEN.findall(str(value or "").lower()))


def tokens(value: object) -> set[str]:
    return set(_TOKEN.findall(str(value or "").lower()))


def stable_id(kind: str, key: str) -> str:
    raw = f"{kind}\0{key}".encode("utf-8", "surrogatepass")
    return f"{kind}:{hashlib.sha256(raw).hexdigest()[:24]}"


def edge_id(source: str, target: str, relation: str) -> str:
    raw = f"{source}\0{target}\0{relation}".encode()
    return f"edge:{hashlib.sha256(raw).hexdigest()[:24]}"


def clean_rel(path: str) -> str:
    p = PurePosixPath(path)
    parts = [x for x in p.parts if x not in ("", ".")]
    if p.is_absolute() or ".." in parts:
        raise ValueError("unsafe relative path")
    return "/".join(parts)
