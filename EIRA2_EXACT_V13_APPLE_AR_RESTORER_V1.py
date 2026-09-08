from __future__ import annotations
import base64
import hashlib
import lzma
import zipfile
from pathlib import Path
from typing import Any

SCHEMA = "eira2_exact_v13_apple_ar_restorer_v1"
EXPECTED_USDA_SHA256 = "227947e5da16d3d1607d55c358568851ffe6dc402fdd47635072d079920571fa"
EXPECTED_USDZ_SHA256 = "5c1c639a4d7b5888cedee455471ea1126309fc27ccc2de32720ba685746a0cbc"
ROOT_LAYER_NAME = "EIRA2_LIVING_NEURAL_ORGANISM_V13_APPLE_AR_SAFE.usda"
ROOT_LAYER_DATE_TIME = (2026, 9, 8, 7, 9, 32)
ROOT_LAYER_EXTERNAL_ATTR = 27525120
ROOT_LAYER_CREATE_SYSTEM = 3
_V13_LZMA_B64 = """"+b64+""""

def _v13_usda_bytes() -> bytes:
    data = lzma.decompress(base64.b64decode(_V13_LZMA_B64.encode("ascii")))
    if hashlib.sha256(data).hexdigest() != EXPECTED_USDA_SHA256:
        raise ValueError("v13_usda_sha256_mismatch")
    return data

def write_brain_usda(atlas: Any, path: Path) -> Path:
    del atlas
    data = _v13_usda_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path

def package_usdz(root_layer: Path, output: Path) -> Path:
    data = root_layer.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED_USDA_SHA256:
        raise ValueError("v13_root_layer_sha256_mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    zi = zipfile.ZipInfo(ROOT_LAYER_NAME, ROOT_LAYER_DATE_TIME)
    zi.compress_type = zipfile.ZIP_STORED
    zi.external_attr = ROOT_LAYER_EXTERNAL_ATTR
    zi.create_system = ROOT_LAYER_CREATE_SYSTEM
    zi.flag_bits = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.writestr(zi, data)
    with zipfile.ZipFile(output, "r") as archive:
        if archive.testzip() is not None:
            raise ValueError("v13_usdz_zip_integrity_failed")
        rows = archive.infolist()
        if len(rows) != 1 or rows[0].filename != ROOT_LAYER_NAME or rows[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("v13_usdz_package_contract_failed")
    actual = hashlib.sha256(output.read_bytes()).hexdigest()
    if actual != EXPECTED_USDZ_SHA256:
        raise ValueError(f"v13_usdz_sha256_mismatch:{actual}")
    return output

def build_brain_usdz(atlas: Any, output: Path) -> Path:
    usda = output.with_suffix(".usda")
    write_brain_usda(atlas, usda)
    return package_usdz(usda, output)
