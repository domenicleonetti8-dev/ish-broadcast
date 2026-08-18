from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Dict, List
from .common import _normalize_message, _select_relevant

class ConversationSource:
    def __init__(self, path: Path, source: str, max_messages: int = 240):
        self.path = path
        self.source = source
        self.max_messages = max_messages

    def load(self) -> List[Dict[str, Any]]:
        if not self.path.is_file() or self.path.is_symlink():
            return []
        try:
            if self.path.suffix == ".jsonl":
                raw = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
            else:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(raw, dict):
            for key in ("messages", "history", "conversation", "items"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw[-self.max_messages:]:
            msg = _normalize_message(item, self.source)
            if msg:
                out.append(msg)
        return out

    def relevant_for(self, current_text: str, limit: int = 12) -> List[Dict[str, Any]]:
        return _select_relevant(self.load(), current_text, limit)


class SymbioteJournal(ConversationSource):
    def __init__(self, live_root: Path):
        path = live_root / "data" / "full_symbiote" / "conversation.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(path, "symbiote_journal", 320)

    def append_exchange(self, user_text: str, eira_text: str, *, fallback: bool = False) -> None:
        records = [
            {"role": "user", "content": str(user_text), "source": "symbiote_journal", "ts": time.time()},
            {"role": "assistant", "content": str(eira_text), "source": "symbiote_journal", "ts": time.time(), "fallback": bool(fallback)},
        ]
        with self.path.open("a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
