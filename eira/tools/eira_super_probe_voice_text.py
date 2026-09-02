#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "EIRA_SUPER_PROBE_V3_FULL_SYSTEM_VOICE_TEXT"

DEFAULT_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "eira_probe",
}

SOURCE_SUFFIXES = {
    ".py", ".html", ".htm", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".sh", ".bash", ".zsh", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".service", ".socket", ".md", ".txt", ".env",
}
SOURCE_NAMES = {"Dockerfile", "Makefile", "Procfile"}
MAX_SOURCE_BYTES = 4_000_000

SCAN_PATTERNS = {
    "voice_to_text_frontend": [r"Voice send error", r"SpeechRecognition", r"webkitSpeechRecognition", r"onresult", r"transcript", r"start Eira Mic", r"stop Eira Mic"],
    "browser_request_construction": [r"fetch\s*\(", r"new\s+URL\s*\(", r"WebSocket\s*\(", r"EventSource\s*\(", r"XMLHttpRequest", r"addFromString\s*\("],
    "typed_input_frontend": [r"chatInput", r"textInput", r"messageInput", r"submit", r"sendMessage", r"sendText", r"/api/chat"],
    "voice_transport_contract": [r"/api/voice", r"/api/input", r"/api/message", r"/api/chat", r"Content-Type", r"application/json", r"location\.origin", r"tailscale", r"ts\.net"],
    "runtime_activation": [r"python3\s+main\.py", r"serve_forever", r"HTTPServer", r"ThreadingHTTPServer", r"uvicorn", r"systemctl", r"ExecStart", r"eira\.tails"],
    "ollama_or_model_calls": [r"\bollama\b", r"\bchat\s*\(", r"\bgenerate\s*\(", r"\bprovider\s*\(", r"\bexecute\s*\("],
    "outward_voice": [r"_speak\s*\(", r"\bunified_response\b", r"\bfinal_response\b", r"\brendered\b", r"\boutward\b"],
    "candidate_leaks": [r"\bcandidate\b", r"UNTRUSTED LLM", r"_extract_candidate", r"untrusted_candidate_material"],
    "fallbacks": [r"\bfallback\b", r"if not response", r"could not produce", r"return task_text", r"return .*candidate"],
    "stage_flow": [r"_stage_payload", r"_stage_text", r"stage_reports", r"NODE_INPUT_MODE", r"response_stage"],
    "context_state": [r"update_context", r"get_context", r"working_notes", r"current_context", r"state\.json"],
    "intent_routing": [r"resolve_intent", r"\bintent\b", r"open_conversation", r"weather", r"provenance"],
    "identity": [r"unified_identity", r"identity_grounding", r"sole final conversational voice", r"I'm just a computer program"],
    "sanitizer_bridge": [r"response_sanitizer", r"response_bridge", r"clean verified response", r"sanitize"],
    "conversation_entry": [r"Dom >", r"Thinking\.\.\.", r"LOCAL_BRAIN_CONVERSATION_ROUTE", r"\binput\s*\("],
}

SUSPICIOUS_FLOW_RULES = [
    {"id": "VOICE_TRANSCRIPT_NOT_REUSING_TEXT_SEND", "severity": "high", "regex": r"(?:onresult|transcript)[\s\S]{0,1200}fetch\s*\(", "why": "Voice-to-text appears to construct its own request instead of reusing the typed-text send function."},
    {"id": "SAFARI_PATTERN_ERROR_SURFACE", "severity": "high", "regex": r"(?:Voice send error|SpeechRecognition)[\s\S]{0,1800}(?:new\s+URL|WebSocket|EventSource|addFromString|fetch)\s*\(", "why": "Safari pattern-sensitive API is present in the voice-to-text path; inspect the reported context."},
    {"id": "MODEL_TEXT_EMBEDDED_IN_TASK", "severity": "critical", "regex": r"(candidate|ollama).*?(task|prompt)|(?:task|prompt).*?(candidate|ollama)", "why": "Model prose may be blended into authoritative user intent."},
    {"id": "CANDIDATE_FALLBACK_TO_OUTWARD", "severity": "critical", "regex": r"if\s+not\s+response[\s\S]{0,250}(candidate|_extract_candidate)", "why": "Untrusted candidate may become outward fallback text."},
    {"id": "SANITIZER_CAN_BECOME_SOURCE", "severity": "high", "regex": r"response_sanitizer_ai[\s\S]{0,250}(or|fallback|settled)", "why": "A sanitizer diagnostic may outrank valid synthesis."},
    {"id": "TASK_MUTATION_BETWEEN_STAGES", "severity": "high", "regex": r"(task_text|task)\s*=\s*.*(response|rendered|summary|candidate)", "why": "The immutable current-turn task may be replaced by intermediate text."},
]

@dataclass
class Finding:
    category: str
    file: str
    line: int
    text: str
    severity: str = "info"
    rule_id: str | None = None
    why: str | None = None

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def run(cmd: list[str], cwd: Path) -> dict[str, Any]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=120)
        return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-12000:]}
    except Exception as e:
        return {"cmd": cmd, "error": f"{type(e).__name__}: {e}"}

def iter_source(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in DEFAULT_SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in SOURCE_SUFFIXES and p.name not in SOURCE_NAMES:
            continue
        try:
            if p.stat().st_size > MAX_SOURCE_BYTES:
                continue
        except OSError:
            continue
        yield p

def line_hits(text: str, pattern: str):
    rx = re.compile(pattern, re.I)
    for i, line in enumerate(text.splitlines(), 1):
        if rx.search(line):
            yield i, line.strip()

def scan_file(root: Path, path: Path):
    rel = str(path.relative_to(root))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], [], []
    findings, funcs, imports = [], [], []
    for category, patterns in SCAN_PATTERNS.items():
        for pat in patterns:
            for line, snippet in line_hits(text, pat):
                findings.append(Finding(category, rel, line, snippet[:300]))
    for rule in SUSPICIOUS_FLOW_RULES:
        rx = re.compile(rule["regex"], re.I | re.S)
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            findings.append(Finding("architecture_risk", rel, line, " ".join(m.group(0).split())[:400], rule["severity"], rule["id"], rule["why"]))
    if path.suffix.lower() != ".py":
        return findings, funcs, imports
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append({"file": rel, "line": node.lineno, "function": node.name, "args": [a.arg for a in node.args.args]})
            elif isinstance(node, ast.Import):
                for n in node.names:
                    imports.append({"file": rel, "module": n.name})
            elif isinstance(node, ast.ImportFrom):
                imports.append({"file": rel, "module": node.module or ""})
    except SyntaxError as e:
        findings.append(Finding("syntax_error", rel, e.lineno or 0, str(e), "critical", "PYTHON_SYNTAX_ERROR", "Python source cannot be parsed."))
    return findings, funcs, imports

def compile_check(root: Path, files: list[Path]):
    results = []
    for p in files:
        r = run([sys.executable, "-m", "py_compile", str(p.relative_to(root))], root)
        if r.get("returncode", 1) != 0:
            results.append({"file": str(p.relative_to(root)), "returncode": r.get("returncode"), "stderr": r.get("stderr"), "error": r.get("error")})
    return results

def snapshot_files(root: Path, findings: list[Finding], outdir: Path):
    affected = sorted({f.file for f in findings if f.severity in {"critical", "high"}})
    snap = outdir / "snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    copied = []
    for rel in affected:
        src = root / rel
        if src.is_file():
            dst = snap / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(rel)
    return copied

def main():
    ap = argparse.ArgumentParser(description="EIRA Sherlock/Ironman/Banner/Hulk forensic probe")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="eira_probe")
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--snapshot", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    outdir = (root / args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    files = list(iter_source(root))
    findings, funcs, imports = [], [], []
    for p in files:
        f, fn, im = scan_file(root, p)
        findings.extend(f); funcs.extend(fn); imports.extend(im)
    py_files = [p for p in files if p.suffix.lower() == ".py"]
    compile_failures = compile_check(root, py_files) if args.compile else []
    copied = snapshot_files(root, findings, outdir) if args.snapshot else []
    summary = {
        "categories": {k: sum(1 for f in findings if f.category == k) for k in sorted({f.category for f in findings})},
        "severity": {k: sum(1 for f in findings if f.severity == k) for k in sorted({f.severity for f in findings})},
        "compile_failures": len(compile_failures),
        "critical_architecture_risks": sum(1 for f in findings if f.category == "architecture_risk" and f.severity == "critical"),
    }
    report = {
        "probe": VERSION,
        "timestamp": now_iso(),
        "root": str(root),
        "git": {
            "status": run(["git", "status", "--short", "--branch"], root),
            "remote": run(["git", "remote", "-v"], root),
            "branch": run(["git", "branch", "--show-current"], root),
            "head": run(["git", "rev-parse", "HEAD"], root),
        },
        "summary": summary,
        "findings": [f.__dict__ for f in findings],
        "functions": funcs,
        "imports": imports,
        "compile_failures": compile_failures,
        "voice_frontend_context": [f.__dict__ for f in findings if f.category in {"voice_to_text_frontend", "browser_request_construction", "typed_input_frontend", "voice_transport_contract", "runtime_activation"}],
        "snapshots": copied,
        "invariants": [
            "Current user turn must remain immutable as intent authority.",
            "Ollama/model output may be internal evidence only.",
            "No candidate may become outward fallback prose.",
            "Synthesis must receive the current user turn, not sanitizer/bridge output.",
            "Diagnostics/provenance must only speak when explicitly requested.",
            "Eira remains sole outward conversational voice.",
            "Speech is optional input only: spoken words become text.",
            "Typed text remains independently optional.",
            "Voice transcript must reuse the same submission function and endpoint as typed text.",
        ],
    }
    report_path = outdir / "eira_super_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    compact = outdir / "eira_super_probe_compact.txt"
    voice_hits = [x for x in findings if x.category in {"voice_to_text_frontend", "browser_request_construction", "typed_input_frontend", "voice_transport_contract", "runtime_activation"}]
    voice_hits.sort(key=lambda x: (0 if "Voice send error" in x.text else 1, 0 if x.category == "voice_to_text_frontend" else 1, x.file, x.line))
    lines = [VERSION, f"ROOT={root}", f"SOURCE_FILES={len(files)}", f"VOICE_FRONTEND_HITS={len(voice_hits)}", f"CRITICAL_ARCH_RISKS={summary['critical_architecture_risks']}", f"COMPILE_FAILURES={summary['compile_failures']}", "", "VOICE/TEXT SEND EVIDENCE:"]
    for f in voice_hits[:120]:
        lines.append(f"[{f.category}] {f.file}:{f.line} :: {f.text}")
    lines.append("")
    lines.append("TOP HIGH/CRITICAL FINDINGS:")
    for f in [x for x in findings if x.severity in {"critical", "high"}][:80]:
        lines.append(f"[{f.severity.upper()}] {f.rule_id or f.category} {f.file}:{f.line} :: {f.text}")
    compact.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("EIRA_SUPER_PROBE=PASS")
    print("REPORT=", report_path)
    print("COMPACT=", compact)
    print("SOURCE_FILES=", len(files))
    print("VOICE_FRONTEND_HITS=", len(voice_hits))
    print("CRITICAL_ARCH_RISKS=", summary["critical_architecture_risks"])
    print("COMPILE_FAILURES=", summary["compile_failures"])

if __name__ == "__main__":
    main()
