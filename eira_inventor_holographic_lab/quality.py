from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import trimesh


@dataclass
class QualityIssue:
    code: str
    severity: str
    part_id: str | None
    message: str
    evidence: dict

    def to_dict(self):
        return asdict(self)


def _bounds(mesh: trimesh.Trimesh) -> np.ndarray:
    b = np.asarray(mesh.bounds, dtype=float)
    if b.shape != (2, 3) or not np.isfinite(b).all():
        raise ValueError("mesh bounds invalid")
    return b


def _aabb_overlap(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.minimum(a[1], b[1]) - np.maximum(a[0], b[0])


def _overlap_volume(a: np.ndarray, b: np.ndarray, epsilon: float = 1e-6) -> float:
    d = _aabb_overlap(a, b)
    if np.any(d <= epsilon):
        return 0.0
    return float(np.prod(d))


def _gap(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two axis-aligned bounding boxes."""
    delta = np.maximum(np.maximum(a[0] - b[1], b[0] - a[1]), 0.0)
    return float(np.linalg.norm(delta))


def _role(part: Mapping) -> str:
    visual = part.get("visual") or {}
    engineering = part.get("engineering") or {}
    return str(
        visual.get("role")
        or engineering.get("role")
        or part.get("subsystem")
        or part.get("system")
        or ""
    ).strip().lower()


def _support_required(part: Mapping) -> bool:
    visual = part.get("visual") or {}
    engineering = part.get("engineering") or {}
    if "support_required" in visual:
        return bool(visual["support_required"])
    if "support_required" in engineering:
        return bool(engineering["support_required"])
    role = _role(part)
    suspended = any(k in role for k in ("hanging", "suspended", "cable", "wire", "vine"))
    intentionally_free = any(k in role for k in ("airflow", "flow_arrow", "annotation", "diagram"))
    return not suspended and not intentionally_free


def _clearance_group(part: Mapping) -> str:
    visual = part.get("visual") or {}
    engineering = part.get("engineering") or {}
    value = visual.get("clearance_group") or engineering.get("clearance_group") or ""
    if value:
        return str(value).strip().lower()
    role = _role(part)
    if "solar" in role:
        return "solar"
    if "turbine" in role or "wind" in role or "duct" in role:
        return "wind"
    return ""


def _allowed_overlap(part: Mapping) -> set[str]:
    visual = part.get("visual") or {}
    engineering = part.get("engineering") or {}
    raw = visual.get("allowed_overlap_with") or engineering.get("allowed_overlap_with") or []
    return {str(x) for x in raw}


def inspect_scene(
    assembly: Mapping,
    scene: trimesh.Scene,
    *,
    support_gap_m: float = 0.035,
    forbidden_overlap_m3: float = 1e-6,
    tiny_part_ratio: float = 1e-5,
) -> dict:
    """Deterministic geometry QA.

    This is intentionally conservative. It detects obvious structural failures before a
    GLB/USDZ is delivered: floating supported parts, solar/wind envelope collisions,
    non-finite geometry, collapsed parts, and grossly tiny accidental fragments.
    It is not FEA or exact collision detection.
    """
    parts = {str(p["part_id"]): p for p in assembly.get("parts", [])}
    meshes: Dict[str, trimesh.Trimesh] = {}
    issues: List[QualityIssue] = []

    for name, geom in scene.geometry.items():
        pid = str(name)
        if not isinstance(geom, trimesh.Trimesh):
            continue
        meshes[pid] = geom
        try:
            b = _bounds(geom)
            ext = b[1] - b[0]
            if np.any(ext <= 1e-8):
                issues.append(QualityIssue(
                    "collapsed_geometry", "error", pid,
                    "Part has a near-zero spatial extent.",
                    {"extents_m": ext.tolist()},
                ))
            if not np.isfinite(np.asarray(geom.vertices, dtype=float)).all():
                issues.append(QualityIssue(
                    "non_finite_geometry", "error", pid,
                    "Part contains non-finite vertex coordinates.", {},
                ))
        except Exception as exc:
            issues.append(QualityIssue(
                "bounds_failure", "error", pid,
                "Part bounds could not be evaluated.", {"error": str(exc)},
            ))

    if meshes:
        all_bounds = np.vstack([_bounds(m) for m in meshes.values()])
        scene_min = all_bounds.min(axis=0)
        scene_max = all_bounds.max(axis=0)
        scene_diag = float(np.linalg.norm(scene_max - scene_min))
    else:
        scene_diag = 0.0

    # Tiny-fragment guard: catches spikes, accidental slivers and disconnected crumbs.
    if scene_diag > 0:
        min_diag = max(scene_diag * tiny_part_ratio, 1e-7)
        for pid, mesh in meshes.items():
            ext = _bounds(mesh)[1] - _bounds(mesh)[0]
            if float(np.linalg.norm(ext)) < min_diag:
                issues.append(QualityIssue(
                    "tiny_fragment", "warning", pid,
                    "Part is extremely small relative to the complete assembly.",
                    {"part_diagonal_m": float(np.linalg.norm(ext)), "scene_diagonal_m": scene_diag},
                ))

    # Explicit forbidden clearance groups. This directly blocks solar/wind bleed-through.
    ids = list(meshes)
    for i, a_id in enumerate(ids):
        pa = parts.get(a_id, {})
        ga = _clearance_group(pa)
        if not ga:
            continue
        ba = _bounds(meshes[a_id])
        allow_a = _allowed_overlap(pa)
        for b_id in ids[i + 1:]:
            pb = parts.get(b_id, {})
            gb = _clearance_group(pb)
            if not gb or ga == gb:
                continue
            if b_id in allow_a or a_id in _allowed_overlap(pb):
                continue
            # Solar and wind envelopes are mutually exclusive unless declared otherwise.
            if {ga, gb} != {"solar", "wind"}:
                continue
            bb = _bounds(meshes[b_id])
            vol = _overlap_volume(ba, bb)
            if vol > forbidden_overlap_m3:
                issues.append(QualityIssue(
                    "solar_wind_overlap", "error", a_id,
                    "Solar and wind-system geometry occupy the same clearance envelope.",
                    {"other_part_id": b_id, "overlap_aabb_volume_m3": vol},
                ))

    # Support/floating check. A part that requires support must touch another part or the
    # declared ground/deck plane within the tolerance. Suspended roles are exempt.
    ground_z = float((assembly.get("quality") or {}).get("ground_z_m", 0.0))
    for pid, mesh in meshes.items():
        part = parts.get(pid, {})
        if not _support_required(part):
            continue
        b = _bounds(mesh)
        grounded = abs(float(b[0, 2]) - ground_z) <= support_gap_m or b[0, 2] < ground_z + support_gap_m
        touching = False
        if not grounded:
            for other_id, other in meshes.items():
                if other_id == pid:
                    continue
                if other_id in _allowed_overlap(part):
                    continue
                if _gap(b, _bounds(other)) <= support_gap_m:
                    touching = True
                    break
        if not grounded and not touching:
            issues.append(QualityIssue(
                "floating_part", "error", pid,
                "Part requiring physical support is floating beyond the configured support tolerance.",
                {"minimum_z_m": float(b[0, 2]), "ground_z_m": ground_z, "support_gap_m": support_gap_m},
            ))

    counts = {
        "errors": sum(1 for x in issues if x.severity == "error"),
        "warnings": sum(1 for x in issues if x.severity == "warning"),
        "parts_checked": len(meshes),
    }
    return {
        "ok": counts["errors"] == 0,
        "counts": counts,
        "issues": [x.to_dict() for x in issues],
        "truth_boundary": "Deterministic mesh/AABB QA only; not exact CAD interference analysis, FEA, CFD, or certification.",
    }


def require_quality(report: Mapping) -> None:
    if not report.get("ok"):
        errors = [x for x in report.get("issues", []) if x.get("severity") == "error"]
        summary = "; ".join(f"{x.get('code')}:{x.get('part_id')}" for x in errors[:12])
        raise ValueError(f"geometry_quality_gate_failed:{summary}")
