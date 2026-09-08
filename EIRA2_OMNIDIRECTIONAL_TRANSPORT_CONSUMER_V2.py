#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

_V3_PATH = Path(__file__).resolve().with_name("EIRA2_OMNIDIRECTIONAL_TRANSPORT_CONSUMER_V3.py")
_spec = importlib.util.spec_from_file_location("eira2_transport_v3_hot_entry", _V3_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("eira2_transport_v3_import_failed")
_v3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v3)

for _name in dir(_v3):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_v3, _name)
