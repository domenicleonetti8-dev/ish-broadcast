import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eira_inventor_holographic_lab.geometry import mesh_from_geometry


def test_extrude_follows_arbitrary_vector():
    g = {
        "kind": "extrude",
        "profile": [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]],
        "vector": [2.0, 0.0, 0.0],
    }
    m = mesh_from_geometry(g)
    ext = np.asarray(m.extents)
    assert ext[0] > 1.9
    assert ext[2] < 1.1


def test_parallel_transport_sweep_stays_finite_and_connected():
    profile = []
    for a in np.linspace(0, 2 * math.pi, 16, endpoint=False):
        profile.append([0.08 * math.cos(a), 0.08 * math.sin(a)])
    path = []
    for t in np.linspace(0, 2 * math.pi, 60):
        path.append([1.2 * math.cos(t), 1.2 * math.sin(t), 0.25 * t])
    m = mesh_from_geometry({"kind": "sweep", "profile": profile, "path": path})
    assert np.isfinite(m.vertices).all()
    assert len(m.faces) == (len(path) - 1) * len(profile) * 2
    assert np.linalg.norm(m.extents) > 2.0


def test_loft_aligns_reversed_and_shifted_sections():
    a = [[-1,-1,0], [1,-1,0], [1,1,0], [-1,1,0]]
    b = [[1,1,1], [1,-1,1], [-1,-1,1], [-1,1,1]]
    c = [[-1,1,2], [-1,-1,2], [1,-1,2], [1,1,2]]
    m = mesh_from_geometry({"kind": "loft", "sections": [a,b,c]})
    assert np.isfinite(m.vertices).all()
    assert len(m.faces) == 16
