import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import eira_inventor_holographic_lab.review as review
from eira_inventor_holographic_lab.preview import generate_preview_script, preview_paths


def test_review_threshold_cannot_be_self_overridden(monkeypatch):
    fake = {
        "pass": True,
        "scores": {
            "source_fidelity": 0.95,
            "structural_coherence": 0.95,
            "system_completeness": 0.95,
            "clearance_cleanliness": 0.95,
            "material_color_fidelity": 0.95,
            "living_architecture_quality": 0.70,
        },
        "issues": [],
        "summary": "model tried to self-pass",
    }
    monkeypatch.setattr(review, "_chat_images", lambda *a, **k: fake.copy())
    result = review.review_render("source.png", ["preview.png"], {"parts": []}, threshold=0.82)
    assert result["pass"] is False
    assert result["minimum_score"] == 0.70


def test_review_error_issue_blocks_pass(monkeypatch):
    fake = {
        "pass": True,
        "scores": {
            "source_fidelity": 0.95,
            "structural_coherence": 0.95,
            "system_completeness": 0.95,
            "clearance_cleanliness": 0.95,
            "material_color_fidelity": 0.95,
            "living_architecture_quality": 0.95,
        },
        "issues": [{"severity": "error", "code": "collision"}],
        "summary": "visible collision",
    }
    monkeypatch.setattr(review, "_chat_images", lambda *a, **k: fake.copy())
    result = review.review_render("source.png", ["preview.png"], {"parts": []}, threshold=0.82)
    assert result["pass"] is False


def test_preview_script_has_required_diagnostic_views():
    script = generate_preview_script("model.glb", "/tmp/previews", resolution=512)
    for name in ("front_three_quarter", "rear_three_quarter", "side_cutaway", "roof_systems", "underside_service"):
        assert name in script
    paths = preview_paths("/tmp/previews")
    assert len(paths) == 5
    assert all(p.endswith(".png") for p in paths)
