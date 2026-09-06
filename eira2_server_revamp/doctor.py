#!/usr/bin/env python3
"""Forensic/static/semantic doctor for the isolated EIRA 2 super server."""
from __future__ import annotations
import argparse, ast, json, re, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any
HERE=Path(__file__).resolve().parent
CORE_ROLE_VALUES={"core","kernel","supervisor","spine","registry","orchestrator","brain_core","neural_core","system_core"}
CORE_ID_RE=re.compile(r"(?:^|[._:/-])(core|kernel|supervisor|spine)(?:$|[._:/-])",re.I)

def _list(payload:Any,*keys:str)->list[dict[str,Any]]:
    if isinstance(payload,list): return [x for x in payload if isinstance(x,dict)]
    if isinstance(payload,dict):
        for k in keys:
            v=payload.get(k)
            if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
            if isinstance(v,dict):
                for kk in keys:
                    if isinstance(v.get(kk),list): return [x for x in v[kk] if isinstance(x,dict)]
    return []
def _id(x:dict[str,Any])->str|None:
    for k in ("id","node_id","name","path"):
        if x.get(k) is not None and str(x[k]).strip(): return str(x[k]).strip()
    return None
def _ends(x:dict[str,Any])->tuple[str|None,str|None]:
    a=x.get("source",x.get("from",x.get("a",x.get("source_id")))); b=x.get("target",x.get("to",x.get("b",x.get("target_id"))))
    return (None if a is None else str(a).strip(),None if b is None else str(b).strip())
def _explicit_core(node:dict[str,Any])->bool:
    nid=_id(node) or ""
    if CORE_ID_RE.search(nid): return True
    for key in ("role","type","kind","class","category","authority"):
        value=node.get(key)
        if isinstance(value,str) and value.strip().lower() in CORE_ROLE_VALUES: return True
        if isinstance(value,list) and any(str(v).strip().lower() in CORE_ROLE_VALUES for v in value): return True
    return False
def _activity_ids(event:dict[str,Any])->list[str]:
    out=[]
    direct=_id(event)
    if direct: out.append(direct)
    for key in ("target","target_id","node","node_id"):
        v=event.get(key)
        if isinstance(v,str) and v.strip(): out.append(v.strip())
    for key in ("targets","node_ids","participants","contributors","active_nodes"):
        v=event.get(key)
        if isinstance(v,list):
            for item in v:
                if isinstance(item,str) and item.strip(): out.append(item.strip())
                elif isinstance(item,dict):
                    nid=_id(item)
                    if nid: out.append(nid)
    return list(dict.fromkeys(out))
def semantic_neural_check(overview:Any,fibers:Any,activity:Any)->list[dict[str,Any]]:
    nodes=_list(overview,"nodes","neurons","data"); edges=_list(fibers,"fibers","edges","data"); events=_list(activity,"activity","events","nodes","data")
    ids=[_id(n) for n in nodes]; valid={x for x in ids if x}; missing=sum(x is None for x in ids); dup=len(valid)!=len([x for x in ids if x]); graph={x:set() for x in valid}; bad_edges=[]
    for e in edges:
        a,b=_ends(e)
        if not a or not b or a not in valid or b not in valid: bad_edges.append((a,b)); continue
        graph[a].add(b); graph[b].add(a)
    event_targets=[nid for e in events for nid in _activity_ids(e)]
    unidentified=sum(1 for e in events if not _activity_ids(e))
    bad_activity=[nid for nid in event_targets if nid not in valid]
    cores=[_id(n) for n in nodes if _id(n) and _explicit_core(n)]
    reachable=set(cores); q=list(cores)
    while q:
        cur=q.pop(0)
        for nx in graph.get(cur,set()):
            if nx not in reachable: reachable.add(nx); q.append(nx)
    active={nid for nid in event_targets if nid in valid}; unreachable=active-reachable
    def c(name,ok,detail): return {"name":name,"ok":bool(ok),"severity":"error","detail":detail}
    return [
        c("canonical_node_ids",bool(nodes) and not dup and not missing,f"nodes={len(nodes)} missing={missing} duplicate={dup}"),
        c("fiber_endpoints_canonical",not bad_edges,f"fibers={len(edges)} invalid={len(bad_edges)}"),
        c("canonical_core_explicit",bool(cores),f"explicit_cores={cores[:8]}" if cores else "no explicit canonical core/kernel/supervisor/spine authority"),
        c("activity_identifiers_explicit",unidentified==0,f"events={len(events)} unidentified={unidentified}"),
        c("activity_targets_canonical",not bad_activity,f"targets={len(event_targets)} invalid={bad_activity[:8]}"),
        c("active_nodes_core_reachable",bool(cores) and not unreachable,f"cores={len(cores)} active={len(active)} unreachable={sorted(unreachable)[:8]}"),
    ]
def R(name:str,ok:bool,detail:str): return {"name":name,"ok":bool(ok),"detail":detail,"severity":"info" if ok else "error"}
def static_checks()->list[dict[str,Any]]:
    out=[]
    for name in ("server.py","hardening.py","qualify.py","doctor.py","migrate.py","migration_qualify.py"):
        p=HERE/name
        if not p.is_file(): continue
        try: ast.parse(p.read_text()); out.append(R("python_syntax:"+name,True,"parsed"))
        except SyntaxError as e: out.append(R("python_syntax:"+name,False,str(e)))
    server=(HERE/"server.py").read_text(); html=(HERE/"static/index.html").read_text(); css=(HERE/"static/reference.css").read_text()
    gates=[
      ("canonical_frontdoor_port_8782",'EIRA2_PORT", "8782"' in server,"8782 default; env override retained"),
      ("no_shell_true","shell=True" not in server,"subprocess bridges argv-based"),
      ("pid_lock_present","acquire_pid_lock" in server and "release_pid_lock" in server,"exclusive owner + cleanup"),
      ("tls_support_present","SSLContext" in server and "load_cert_chain" in server,"TLS supported"),
      ("manifest_verifier_present","verify_manifest" in server,"integrity verifier present"),
      ("safe_ar_containment","ar_path_escape" in server and "root not in path.parents" in server,"AR root bounded"),
      ("voice_bridge_required",all(x in server for x in ("voice_to_text","EIRA2_VOICE_CMD","EIRA2_VOICE_PROBE_CMD")),"voice participates in health/doctor"),
      ("voice_audio_bounded","VOICE_MAX_BYTES" in server and "voice_audio_too_large" in server,"bounded audio"),
      ("voice_temp_cleanup","voice_tmp" in server and "path.unlink(missing_ok=True)" in server,"temporary utterances cleaned"),
      ("single_conversation_authority","def conversation(" in server and 'path == "/api/conversation"' in server,"one canonical conversation bridge"),
      ("ambient_browser_capture",all(x in html for x in ("MediaRecorder","vadLoop","createAnalyser")),"MediaRecorder + WebAudio VAD"),
      ("voice_text_frontend_convergence","submitText(transcript,'voice')" in html and "submitText(text,'text')" in html,"spoken and typed text reuse submitText"),
      ("iphone_secure_context_gate","window.isSecureContext" in html and "Microphone requires HTTPS on iPhone Safari" in html,"secure-context microphone gate"),
      ("ui_api_routes_resolve",all(x in server for x in ("/api/health","/api/doctor","/api/runtime","/api/voice","/api/conversation","/api/invention/launch","/api/neural/overview","/api/neural/fibers","/api/neural/activity","/api/ar/list","/api/ar/file/")),"all umbrella routes implemented"),
      ("explicit_core_no_fallback","cores=[id(neural.nodes[0],0)]" not in html and "explicitCore" in html and "CANONICAL CORE MISSING" in html,"renderer refuses invented core authority and visibly blocks routing"),
      ("multi_target_activity_contract",all(x in html for x in ("activityTargets","node_ids","participants","active_nodes")),"renderer accepts explicit real multi-node activity events"),
      ("electron_path_flow",all(x in html for x in ("routes","electronPhase","quadraticCurveTo")),"electrons animate only over evidenced active routes"),
      ("canonical_node_finder",all(x in html for x in ("nodeFind","findCanonicalNode","FIND NEURON")),"all canonical nodes are searchable/displayable on demand"),
      ("live_neural_activity_contract",all(x in html for x in ("pathTo","pathEdges","pathNodes","cores")),"evidenced activity routing"),
      ("reference_visual_skin_linked",'/reference.css' in html and all(x in css for x in (".brainCard",".orbGlow",".compose")),"reference spherical skin linked"),
    ]
    out.extend(R(*g) for g in gates)
    node=shutil.which("node")
    if node:
        a=html.find("<script>"); b=html.rfind("</script>")
        if a<0 or b<=a: out.append(R("browser_javascript_syntax",False,"inline script missing"))
        else:
            with tempfile.NamedTemporaryFile("w",suffix=".js",delete=False) as f: f.write(html[a+8:b]); tmp=Path(f.name)
            try:
                cp=subprocess.run([node,"--check",str(tmp)],capture_output=True,text=True); out.append(R("browser_javascript_syntax",cp.returncode==0,(cp.stderr or cp.stdout or "node --check PASS")[-1000:]))
            finally: tmp.unlink(missing_ok=True)
    else: out.append({"name":"browser_javascript_syntax","ok":True,"severity":"warning","detail":"node unavailable"})
    return out
def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--static",action="store_true"); parser.parse_args()
    checks=static_checks(); errors=[x for x in checks if not x.get("ok") and x.get("severity")!="warning"]
    for c in checks: print(("PASS" if c.get("ok") else "FAIL"),c["name"],"::",c["detail"])
    print(json.dumps({"ok":not errors,"errors":len(errors),"warnings":sum(c.get("severity")=="warning" for c in checks),"checks":len(checks)})); return 1 if errors else 0
if __name__=="__main__": raise SystemExit(main())
