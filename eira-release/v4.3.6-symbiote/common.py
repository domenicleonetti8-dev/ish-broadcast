from __future__ import annotations
import hashlib, inspect, json, re
from pathlib import Path
from typing import Any, Callable, Dict, List

VERSION = "4.3.6"
ROLE = "eira_full_symbiote_ai"
BASE = Path(__file__).resolve().parent
_CONTROL = re.compile(r"^\s*(?:exit|quit|shutdown|close)\s*$", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]{2,}")
_BACKWARD = re.compile(
    r"\b(?:continue|resume|pick up|keep going|earlier|before|last time|we just|you just|what we|what you|"
    r"that one|same one|same thing|as discussed|we talked|you said|i said|it|them|those)\b", re.I,
)
_GENERIC_DRIFT = re.compile(
    r"\b(?:how may i assist you|how can i (?:assist|help) you(?: today)?|i(?:'m| am) here to (?:assist|help)|"
    r"let me know if you need (?:more|any) details|please feel free to (?:ask|reach out)|"
    r"i understand that you(?:'re| are) looking to|here'?s a high[- ]level overview|"
    r"as an ai(?: language model)?|i don'?t have personal (?:feelings|emotions)|"
    r"is there anything else i can (?:assist|help) you with|what would you like (?:to discuss|help with)|"
    r"below is a simplified example|security considerations should be taken into account)\b", re.I,
)
_STOP = {
    "the","and","that","this","with","from","have","what","when","where","which","would","could","should",
    "your","youre","about","there","their","then","than","into","just","like","want","need","please","really",
    "assistant","user","message","response","today","right","current","thing","things","doing","feeling","friend",
    "continue","resume","earlier","before","same","them","those","it","one",
    "build","make","create","explain","tell","show","write","help","system","project","thing","stuff",
}
_ALIAS_STOP = {
    "eira","extensions","extension","unified","brain","plugin","core","engine","module","provider","service",
    "runtime","system","the","and","for","with","from","into","ai",
}
_STANDARD_CALLS = ("ask", "execute", "handle", "run", "process")
def _config_path() -> Path:
    p = Path(__file__).resolve().parents[1] / "unified_brain_ai" / "live_config.json"
    if p.is_file():
        return p
    return Path(__file__).resolve().parents[1] / "unified_brain_ai" / "config.example.json"


def _config() -> Dict[str, Any]:
    try:
        raw = json.loads(_config_path().read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _live_root() -> Path:
    cfg = _config()
    sym = cfg.get("symbiote") or {}
    raw = str(sym.get("live_root") or cfg.get("engineering", {}).get("live_root") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _terms(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(str(text or "")) if t.lower() not in _STOP and len(t) >= 3}


def _stable_id(kind: str, path: str, symbol: str = "") -> str:
    raw = f"{kind}\0{path}\0{symbol}".encode("utf-8", "replace")
    return f"{kind}:{hashlib.sha1(raw).hexdigest()[:20]}"


def _alias_tokens(value: str) -> set[str]:
    raw = str(value or "").replace("-", "_").replace(".", "_")
    return {p.lower() for p in raw.split("_") if len(p) >= 4 and p.lower() not in _ALIAS_STOP and not p.isdigit()}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("response", "reply", "text", "message", "answer", "output"):
            if isinstance(value.get(key), (str, int, float)):
                return str(value[key])
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _safe_json(value: Any, limit: int) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:limit]
    except Exception:
        return str(value)[:limit]


def _invoke(fn: Callable[..., Any], prompt: str, args=(), kwargs=None):
    kwargs = dict(kwargs or {})
    try:
        sig = inspect.signature(fn)
        params = [p for p in sig.parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if not params:
            return fn()
    except (TypeError, ValueError):
        pass
    try:
        return fn(prompt, *args, **kwargs)
    except TypeError:
        if args or kwargs:
            raise
        return fn({"message": prompt, "text": prompt, "input": prompt})


def _normalize_message(value: Any, source: str) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    role = str(value.get("role") or value.get("speaker") or "").strip().lower()
    if role in {"dom", "human"}:
        role = "user"
    elif role in {"eira", "ai", "assistant"}:
        role = "assistant"
    if role not in {"user", "assistant", "system", "tool"}:
        return None
    content = value.get("content")
    if content is None:
        content = value.get("message", value.get("text", value.get("response", "")))
    content = str(content or "").strip()
    if not content:
        return None
    return {"role": role, "content": content[:12000], "source": source}


def _select_relevant(history: List[Dict[str, Any]], current_text: str, limit: int = 12) -> List[Dict[str, Any]]:
    if not history:
        return []
    limit = max(2, min(24, int(limit)))
    q = _terms(current_text)
    explicit = bool(_BACKWARD.search(str(current_text or "")))
    if not q:
        return history[-min(limit, 6):] if explicit else []
    scored: List[tuple[float, int]] = []
    total = len(history)
    for idx, msg in enumerate(history):
        terms = _terms(msg.get("content", ""))
        if not terms:
            continue
        overlap = len(q & terms) / max(1, len(q))
        if overlap <= 0:
            continue
        recency = (idx + 1) / max(1, total)
        score = overlap * 0.88 + recency * 0.12
        if score >= 0.16:
            scored.append((score, idx))
    if not scored:
        return history[-min(limit, 6):] if explicit else []
    chosen: set[int] = set()
    for _, idx in sorted(scored, reverse=True)[: max(2, limit // 2)]:
        chosen.add(idx)
        if idx > 0:
            chosen.add(idx - 1)
        if idx + 1 < total:
            chosen.add(idx + 1)
    return [history[i] for i in sorted(chosen)][-limit:]
