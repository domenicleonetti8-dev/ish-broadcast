from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class OmniVenomBridge:
    """Read-only bridge into the already-installed OmniVenom mesh."""

    def __init__(self, live_root: str | Path):
        self.live = Path(live_root).expanduser().resolve()
        self.state = self.live / "data" / "omnivenom" / "mesh.sqlite3"
        self._mesh = None
        self._lock = threading.RLock()
        self._refresh_started = False
        self._last_error = ""

    def _build(self):
        if self._mesh is not None:
            return self._mesh
        with self._lock:
            if self._mesh is not None:
                return self._mesh
            try:
                from extensions.omnivenom_mesh_ai.runtime import Omnivenom
            except Exception:
                from omnivenom_mesh_ai.runtime import Omnivenom
            self._mesh = Omnivenom(self.live, self.state)
            return self._mesh

    def status(self) -> dict[str, Any]:
        try:
            return {"ok": True, **self._build().status(), "state_path": str(self.state)}
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}:{str(exc)[:240]}"
            return {"ok": False, "error": self._last_error, "state_path": str(self.state)}

    def ensure_index_async(self) -> None:
        with self._lock:
            if self._refresh_started:
                return
            self._refresh_started = True
        def worker():
            try:
                mesh = self._build()
                status = mesh.status()
                if int(status.get("nodes") or 0) == 0:
                    mesh.refresh()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}:{str(exc)[:240]}"
        threading.Thread(target=worker, name="omnivenom-index", daemon=True).start()

    def context(self, query: str, *, depth: int = 1, limit: int = 80) -> dict[str, Any]:
        query = str(query or "").strip()
        if not query:
            return {"ok": True, "roots": [], "nodes": [], "edges": []}
        try:
            raw = self._build().context(query, depth=max(0, min(int(depth), 2)), limit=max(1, min(int(limit), 160)))
            nodes = [{"node_id": n.get("node_id"), "kind": n.get("kind"), "name": n.get("name"), "path": n.get("path"), "state": n.get("state"), "capabilities": n.get("capabilities", [])} for n in list(raw.get("nodes") or [])[:48]]
            edges = [{"source": e.get("source"), "target": e.get("target"), "relation": e.get("relation"), "confidence": e.get("confidence")} for e in list(raw.get("edges") or [])[:80]]
            return {"ok": True, "roots": list(raw.get("roots") or [])[:12], "nodes": nodes, "edges": edges}
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}:{str(exc)[:240]}"
            return {"ok": False, "error": self._last_error, "roots": [], "nodes": [], "edges": []}

    def compact_context(self, query: str, *, max_chars: int = 12000) -> str:
        obj = self.context(query)
        if not obj.get("ok"):
            return "OmniVenom context unavailable for this turn."
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)[: max(1000, int(max_chars))]
