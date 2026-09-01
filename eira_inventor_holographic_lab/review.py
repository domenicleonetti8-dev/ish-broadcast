from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path
from typing import Mapping, Sequence

from .vision_contract import response_schema


class VisualReviewError(RuntimeError):
    pass


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _chat_images(prompt: str, image_paths: Sequence[str], schema: Mapping, *, model: str, timeout: int):
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt, "images": [_b64(p) for p in image_paths]}],
        "format": schema,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception as exc:
        raise VisualReviewError(f"visual_review_transport:{type(exc).__name__}:{exc}") from exc
    raw = data.get("message", {}).get("content", "")
    try:
        return json.loads(raw)
    except Exception as exc:
        raise VisualReviewError(f"visual_review_json:{exc}") from exc


def review_schema():
    issue = {
        "type": "object",
        "required": ["code", "severity", "description", "evidence", "recommended_change"],
        "properties": {
            "code": {"type": "string"},
            "severity": {"type": "string"},
            "part_ids": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
            "evidence": {"type": "string"},
            "recommended_change": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "required": ["pass", "scores", "issues", "summary"],
        "properties": {
            "pass": {"type": "boolean"},
            "scores": {
                "type": "object",
                "required": ["source_fidelity", "structural_coherence", "system_completeness", "clearance_cleanliness", "material_color_fidelity", "living_architecture_quality"],
                "properties": {
                    "source_fidelity": {"type": "number"},
                    "structural_coherence": {"type": "number"},
                    "system_completeness": {"type": "number"},
                    "clearance_cleanliness": {"type": "number"},
                    "material_color_fidelity": {"type": "number"},
                    "living_architecture_quality": {"type": "number"},
                },
            },
            "issues": {"type": "array", "items": issue},
            "summary": {"type": "string"},
        },
    }


def review_render(
    source_image: str,
    preview_images: Sequence[str],
    assembly: Mapping,
    *,
    model: str = "gemma3:4b",
    timeout: int = 900,
    threshold: float = 0.82,
):
    ir = json.dumps(assembly, separators=(",", ":"))
    prompt = f'''
You are the visual engineering QA critic for a GENERAL image-to-3D invention renderer.
The FIRST image is the user's source/reference. The remaining images are deterministic multi-angle renders of the generated 3D assembly.

Evaluate the actual rendered geometry, not the intended description. Do not reward parts merely because the JSON claims they exist. If a solar panel floats, a pipe clips through another object, a turbine is malformed, plants look generic/repetitive, or a dense service base was simplified, mark it as a visible failure.

Score each category from 0.0 to 1.0:
- source_fidelity: does the 3D object preserve the visible design language, component placement and major forms?
- structural_coherence: do supports, mounts, frames and physical relationships look buildable rather than floating?
- system_completeness: are visually important systems from the source actually represented with comparable density?
- clearance_cleanliness: are there obvious overlaps, bleed-through, clipping, floating panels/pipes/equipment or impossible routing?
- material_color_fidelity: are colors/material families distinct and useful for engineering inspection?
- living_architecture_quality: when biological systems are present, do they look varied, organized and structurally plausible rather than repeated generic primitives?

PASS RULE
Set pass=true only if every score is >= {float(threshold):.3f} AND there are no severity=error issues. Do not relax this rule.

For every visible defect, give a concrete recommended geometry/layout change. Reference part IDs only when the IR makes them identifiable. Do not invent measurements that are not visible.

Engineering IR for part-name context only:
{ir}
'''
    result = _chat_images(prompt, [source_image, *preview_images], review_schema(), model=model, timeout=timeout)
    # Re-apply the threshold deterministically in code so a model cannot self-pass below it.
    scores = result.get("scores") or {}
    numeric = []
    for key in ("source_fidelity", "structural_coherence", "system_completeness", "clearance_cleanliness", "material_color_fidelity", "living_architecture_quality"):
        try:
            numeric.append(float(scores.get(key, 0.0)))
        except Exception:
            numeric.append(0.0)
    has_error = any(str(x.get("severity", "")).lower() == "error" for x in result.get("issues", []))
    result["pass"] = bool(numeric and min(numeric) >= float(threshold) and not has_error)
    result["deterministic_threshold"] = float(threshold)
    result["minimum_score"] = min(numeric) if numeric else 0.0
    return result


def repair_assembly(
    source_image: str,
    preview_images: Sequence[str],
    assembly: Mapping,
    review: Mapping,
    deterministic_quality: Mapping | None = None,
    *,
    model: str = "gemma3:4b",
    timeout: int = 900,
):
    prompt = f'''
You are repairing an engineering IR for a GENERAL invention-to-3D renderer.
The FIRST image is the source/reference. Remaining images are the failed multi-angle renders.

Return a COMPLETE replacement engineering IR matching the required schema. Preserve the inventor's objective and every supported observed/stated fact. Keep provenance truthful. Do not fix visible problems by deleting important systems or replacing complex geometry with anonymous boxes.

Repair priorities:
1. Remove visible interpenetration, floating parts and unsupported geometry by changing geometry/transform/mount relationships.
2. Keep solar and wind systems in distinct clearance envelopes unless the source explicitly shows a designed shared interface.
3. Restore missing source-visible subsystem density, especially bases, underfloor service equipment, piping, tanks, pumps, manifolds, controls and mounting structure.
4. Preserve meaningful curvature and topology with sweep/loft/surface/curve/mesh geometry instead of primitive fallback.
5. Improve biological geometry with distinct plant families, hanging/suspended relationships and non-repetitive forms when the source contains living architecture.
6. Keep dimensions/engineering values marked observed, calculated, inferred, assumed, hypothesized or unresolved. Never turn an estimate into a measurement.

FAILED IR:
{json.dumps(assembly, separators=(",", ":"))}

VISUAL REVIEW:
{json.dumps(review, separators=(",", ":"))}

DETERMINISTIC GEOMETRY QA:
{json.dumps(deterministic_quality or {}, separators=(",", ":"))}
'''
    return _chat_images(prompt, [source_image, *preview_images], response_schema(), model=model, timeout=timeout)
