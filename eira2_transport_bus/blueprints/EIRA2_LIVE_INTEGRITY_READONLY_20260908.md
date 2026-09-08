# EIRA2 LIVE Integrity Read-Only Inspection

Request: eira_live_integrity_after_storage_reconnect_20260908

This blueprint is strictly observational. Inspect `/media/domenicleonetti/easystore/EIRA/LIVE` and return exact observed integrity evidence only. Do not mutate LIVE, do not restart processes, do not mount/unmount, and do not invoke Builder.

Report: LIVE root existence; `main.py`; compact file count; Python file count; presence of `eira2/`, `extensions/`, `eira_probe/`, `eira_probe/transport_runtime_v10/`; critical entrypoints; zero-byte Python files; and any filesystem read errors encountered during the census. Compare the observed compact count to the prior 406-file reconstruction only as a reference, not as an assumption.
