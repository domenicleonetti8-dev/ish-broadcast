from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import apple_ar_v13_base as _base

SCHEMA = "eira2_v13_roomscale_walkthrough_ar_v1"
ROOM_SCALE = 1.8


def write_brain_usda(atlas: Any, path: Path) -> Path:
    _base.write_brain_usda(atlas, path)
    text = path.read_text(encoding="utf-8")

    # Remove the object-style animation timeline entirely.
    text = re.sub(r'^\s*startTimeCode\s*=.*$', '', text, flags=re.M)
    text = re.sub(r'^\s*endTimeCode\s*=.*$', '', text, flags=re.M)
    text = re.sub(r'^\s*timeCodesPerSecond\s*=.*$', '', text, flags=re.M)
    text = re.sub(
        r'\s*float3 xformOp:rotateXYZ\.timeSamples\s*=\s*\{.*?\}\s*',
        '\n',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'\s*uniform token\[\] xformOpOrder\s*=\s*\["xformOp:rotateXYZ"\]\s*',
        '\n',
        text,
        count=1,
    )

    # Turn the canonical V13 organism into a room-scale AR scene.
    marker = 'def Xform "Brain"\n{'
    if marker not in text:
        raise ValueError("v13_walkthrough_brain_root_missing")
    replacement = (
        marker
        + f'\n    float3 xformOp:scale = ({ROOM_SCALE:.6f}, {ROOM_SCALE:.6f}, {ROOM_SCALE:.6f})'
        + '\n    uniform token[] xformOpOrder = ["xformOp:scale"]'
        + '\n    custom string eira:arMode = "room_scale_walkthrough"'
        + '\n    custom string eira:interaction = "physical_device_motion"'
        + '\n    custom string eira:rotation = "disabled"'
    )
    text = text.replace(marker, replacement, 1)
    text = text.replace(
        'eira2_living_neural_organism_v13_apple_ar_safe',
        'eira2_v13_roomscale_walkthrough_ar_v1',
        1,
    )

    if '.timeSamples' in text:
        raise ValueError("v13_walkthrough_animation_not_removed")
    if 'metersPerUnit = 1' not in text:
        raise ValueError("v13_walkthrough_meter_scale_missing")

    path.write_text(text, encoding="utf-8")
    return path


def package_usdz(root_layer: Path, output: Path) -> Path:
    return _base.package_usdz(root_layer, output)


def build_brain_usdz(atlas: Any, output: Path) -> Path:
    usda = output.with_suffix(".usda")
    write_brain_usda(atlas, usda)
    return package_usdz(usda, output)
