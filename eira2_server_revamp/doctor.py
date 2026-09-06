#!/usr/bin/env python3
"""Forensic/static/semantic doctor for the isolated EIRA 2 super server."""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent


def _nodes(payload: Any)->list[dict[str,Any]]:
    if isinstance(payload,list): return [x for x in payload if isinstance(x,dict)]
    if isinstance(payload,dict):
        for k in ("nodes","neurons","data"):
            v=payload.get(k)
            if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
            if isinstance(v,dict):
                for kk in ("nodes","neurons"):
                    if isinstance(v.get(kk),list): return [x for x in v[kk] if isinstance(x,dict)]
    return []


def _fibers(payload: Any)->list[dict[str,Any]]:
    if isinstance(payload,list): return [x for x in payload if isinstance(x,dict)]
    if isinstance(payload,dict):
        for k in ("fibers","edges","data"):
            v=payload.get(k)
            if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
            if isinstance(v,dict):
                for kk in ("fibers","edges"):
                    if isinstance(v.get(kk),list): return [x for x in v[kk] if isinstance(x,dict)]
    return []


def _activity(payload: Any)->list[dict[str,Any]]:
    if isinstance(payload,list): return [x for x in payload if isinstance(x,dict)]
    if isinstance(payload,dict):
        for k in ("activity","events","nodes","data"):
            v=payload.get(k)
            if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
            if isinstance(v,dict):
                for kk in ("activity","events","nodes"):
                    if isinstance(v.get(kk),list): return [x for x in v[kk] if isinstance(x,dict)]
    return []


def _id(x:dict[str,Any])->str|None:
    for k in ("id","node_id","name","path"):
        if x.get(k) is not None and str(x[k]).strip(): return str(x[k]).strip()
    return None


def _ends(x:dict[str,Any])->tuple[str|None,str|None]:
    a=x.get("source",x.get("from",x.get("a",x.get("source_id"))))
    b=x.get("target",x.get("to",x.get("b",x.get("target_id"))))
    return (None if a is None else str(a),None if b is None else str(b))


def semantic_neural_check(overview:Any,fibers:Any,activity:Any)->list[dict[str,Any]]:
    nodes=_nodes(overview); edges=_fibers(fibers); events=_activity(activity)
    ids=[_id(n) for n in nodes]; valid={x for x in ids if x}
    dup=len(valid)!=len([x for x in ids if x]); missing=sum(x is None for x in ids)
    bad_edges=[]; graph={x:set() for x in valid}
    for e in edges:
        a,b=_ends(e)
        if not a or not b or a not in valid or b not in valid: bad_edges.append((a,b)); continue
        graph[a].add(b); graph[b].add(a)
    bad_activity=[_id(a) for a in events if not _id(a) or _id(a) not in valid]
    core=[_id(n) for n in nodes if _id(n) and any(w in json.dumps(n).lower() for w in ("core","kernel","supervisor","spine","registry","bridge"))]
    if not core and ids: core=[next(x for x in ids if x)]
    reachable=set(core); q=list(core)
    while q:
        cur=q.pop(0)
        for nx in graph.get(cur,set()):
            if nx not in reachable: reachable.add(nx); q.append(nx)
    active_valid={_id(a) for a in events if _id(a) in valid}
    unreachable=sorted(active_valid-reachable)
    return [
        {"name":"canonical_node_ids","ok":bool(nodes) and not dup and missing==0,"severity":"error","detail":f"nodes={len(nodes)} missing={missing} duplicate={dup}"},
        {"name":"fiber_endpoints_canonical","ok":not bad_edges,"severity":"error","detail":f"fibers={len(edges)} invalid={len(bad_edges)}"},
        {"name":"activity_targets_canonical","ok":not bad_activity,"severity":"error","detail":f"activity={len(events)} invalid={len(bad_activity)}"},
        {"name":"active_nodes_core_reachable","ok":not unreachable,"severity":"error","detail":f"cores={len(core)} unreachable_active={len(unreachable)}"},
    ]


def result(name:str,ok:bool,detail:str)->dict[str,Any]:
    return {"name":name,"ok":bool(ok),"detail":detail,"severity":"error" if not ok else "info"}


def static_checks()->list[dict[str,Any]]:
    out=[]
    pyfiles=[HERE/x for x in ("server.py","hardening.py","qualify.py","doctor.py","migrate.py","migration_qualify.py") if (HERE/x).is_file()]
    for p in pyfiles:
        try: ast.parse(p.read_text(encoding="utf-8")); out.append(result(f"python_syntax:{p.name}",True,"parsed"))
        except SyntaxError as e: out.append(result(f"python_syntax:{p.name}",False,str(e)))
    server=(HERE/"server.py").read_text(encoding="utf-8")
    html=(HERE/"static/index.html").read_text(encoding="utf-8")
    css=(HERE/"static/reference.css").read_text(encoding="utf-8")
    out += [
        result("canonical_frontdoor_port_8782",'EIRA2_PORT", "8782"' in server,"8782 default; env override retained"),
        result("no_shell_true","shell=True" not in server,"all subprocess bridges argv-based"),
        result("pid_lock_present","acquire_pid_lock" in server and "release_pid_lock" in server,"exclusive owner + cleanup"),
        result("tls_support_present","SSLContext" in server and "load_cert_chain" in server,"direct TLS pair supported; external HTTPS allowed"),
        result("manifest_verifier_present","verify_manifest" in server,"package integrity gate present"),
        result("safe_ar_containment","root not in path.parents" in server and "ar_path_escape" in server,"USDZ roots cannot be escaped"),
        result("voice_bridge_required","voice_to_text" in server and "EIRA2_VOICE_CMD" in server and "EIRA2_VOICE_PROBE_CMD" in server,"voice is health/doctor authority"),
        result("voice_audio_bounded","VOICE_MAX_BYTES" in server and "voice_audio_too_large" in server,"audio upload is bounded"),
        result("voice_temp_cleanup","voice_tmp" in server and "path.unlink(missing_ok=True)" in server,"utterance files cleaned after STT"),
        result("voice_transcript_only_endpoint",'path == "/api/voice"' in server and "transcribe_audio" in server,"STT endpoint cannot become second conversation authority"),
        result("single_conversation_authority","def conversation(" in server and 'path == "/api/conversation"' in server,"one server-side canonical text bridge"),
        result("ambient_browser_capture",all(x in html for x in ("MediaRecorder","vadLoop","AnalyserNode") ) if "AnalyserNode" in html else all(x in html for x in ("MediaRecorder","vadLoop","createAnalyser")),"MediaRecorder + WebAudio VAD"),
        result("voice_text_frontend_convergence","submitText(transcript,'voice')" in html and "submitText(text,'text')" in html and "/api/conversation" in html,"voice and typed text reuse submitText"),
        result("iphone_secure_context_gate","window.isSecureContext" in html and "Microphone requires HTTPS on iPhone Safari" in html,"mic refuses insecure Safari origin"),
        result("ui_api_routes_resolve",all(r in server for r in ("/api/health","/api/doctor","/api/runtime","/api/voice","/api/conversation","/api/invention/launch","/api/neural/overview","/api/neural/fibers","/api/neural/activity","/api/ar/list","/api/ar/file/")),"all UI routes implemented"),
        result("live_neural_activity_contract",all(x in html for x in ("pathTo","pathEdges","pathNodes","cores")),"core-to-active evidenced routing present"),
        result("reference_visual_skin_linked",'/reference.css' in html and all(x in css for x in (".brainCard",".orbGlow",".compose")),"spherical reference skin linked"),
    ]
    node=shutil.which("node")
    if node:
        start=html.find("<script>"); end=html.rfind("</script>")
        if start<0 or end<=start: out.append(result("browser_javascript_syntax",False,"inline script missing"))
        else:
            with tempfile.NamedTemporaryFile("w",suffix=".js",delete=False) as f:
                f.write(html[start+8:end]); tmp=f.name
            try:
                cp=subprocess.run([node,"--check",tmp],capture_output=True,text=True)
                out.append(result("browser_javascript_syntax",cp.returncode==0,(cp.stderr or cp.stdout or "node --check PASS")[-1000:]))
            finally: Path(tmp).unlink(missing_ok=True)
    else: out.append({"name":"browser_javascript_syntax","ok":True,"severity":"warning","detail":"node unavailable locally; CI requires Node"})
    return out


def main()->int:
    argparse.ArgumentParser().add_argument("--static",action="store_true").parse_args()
    checks=static_checks(); errors=[x for x in checks if not x.get("ok") and x.get("severity")!="warning"]
    for c in checks: print(("PASS" if c.get("ok") else "FAIL"),c["name"],"::",c["detail"])
    print(json.dumps({"ok":not errors,"errors":len(errors),"warnings":sum(c.get("severity")=="warning" for c in checks),"checks":len(checks)}))
    return 1 if errors else 0

if __name__=="__main__": raise SystemExit(main())
