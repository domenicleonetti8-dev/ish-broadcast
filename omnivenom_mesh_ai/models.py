from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Node:
    node_id: str
    kind: str
    name: str
    path: str = ""
    state: str = "active"
    aliases: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    content_sha256: str = ""
    semantic_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    edge_id: str
    source: str
    target: str
    relation: str
    confidence: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrainEndpoint:
    name: str
    role: str
    callable_name: str = ""
    node_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
