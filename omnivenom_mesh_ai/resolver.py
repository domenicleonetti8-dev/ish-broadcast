from __future__ import annotations
import json
from .models import Edge, Node
from .normalize import edge_id, stable_id


class MorphResolver:
    """Repairs graph identity without blindly moving or rewriting LIVE files."""
    def __init__(self, store):
        self.store=store

    def reconcile(self):
        nodes=self.store.nodes()
        active=[n for n in nodes if n['state']=='active']
        unresolved=[n for n in nodes if n['state']=='unresolved']
        modules={}
        for n in active:
            try: meta=json.loads(n['metadata_json'])
            except Exception: meta={}
            mod=meta.get('module')
            if mod and n.get('kind')=='file': modules.setdefault(str(mod),[]).append(n)
        resolved=0;dupes=0;moved=0;recovered=0
        for u in unresolved:
            try: meta=json.loads(u['metadata_json'])
            except Exception: meta={}
            expected=str(meta.get('expected_module') or u['name'])
            candidates=modules.get(expected) or []
            if len(candidates)==1:
                n=candidates[0]
                e=Edge(edge_id(u['node_id'],n['node_id'],'resolved_into'),u['node_id'],n['node_id'],'resolved_into',1.0,{"expected_module":expected})
                self.store.upsert_edge(e);self.store.lineage(u['node_id'],n['node_id'],'resolved_into','missing module later discovered');resolved+=1
        # missing path -> newly active identical/semantic content: reconnect lineage rather than losing it
        missing=[n for n in nodes if n['state']=='missing']
        active_by_hash={}
        active_by_sem={}
        for n in active:
            if n.get('content_sha256'): active_by_hash.setdefault(n['content_sha256'],[]).append(n)
            if n.get('semantic_sha256'): active_by_sem.setdefault(n['semantic_sha256'],[]).append(n)
        for old in missing:
            candidates=active_by_hash.get(old.get('content_sha256') or '',[]) if old.get('content_sha256') else []
            relation='moved_to'; confidence=1.0; reason='missing path recovered at identical-content location'
            if not candidates and old.get('semantic_sha256'):
                candidates=active_by_sem.get(old['semantic_sha256'],[])
                relation='morphed_to'; confidence=0.9; reason='missing path recovered at semantically equivalent Python location'
            if candidates:
                candidates=sorted(candidates,key=lambda x:(len(x['path']),x['path']))
                new=candidates[0]
                e=Edge(edge_id(old['node_id'],new['node_id'],relation),old['node_id'],new['node_id'],relation,confidence,{"old_path":old['path'],"new_path":new['path']})
                self.store.upsert_edge(e);self.store.lineage(old['node_id'],new['node_id'],relation,reason);recovered+=1
        # exact-content aliases: choose live/non-backup shortest path as canonical
        by_hash={}
        for n in active:
            d=n.get('content_sha256') or ''
            if d: by_hash.setdefault(d,[]).append(n)
        for digest,rows in by_hash.items():
            if len(rows)<2: continue
            def score(x):
                p=x['path'].lower(); backup=any(k in p for k in ('backup','bak','archive','old','snapshot'))
                return (1 if backup else 0,len(x['path']),x['path'])
            rows=sorted(rows,key=score);canonical=rows[0]
            for other in rows[1:]:
                e=Edge(edge_id(other['node_id'],canonical['node_id'],'content_alias_of'),other['node_id'],canonical['node_id'],'content_alias_of',1.0,{"sha256":digest})
                self.store.upsert_edge(e);self.store.lineage(other['node_id'],canonical['node_id'],'content_alias_of','identical bytes');dupes+=1
        # semantic matches connect moved/rewritten formatting variants
        by_sem={}
        for n in active:
            d=n.get('semantic_sha256') or ''
            if d: by_sem.setdefault(d,[]).append(n)
        for digest,rows in by_sem.items():
            if len(rows)<2: continue
            rows=sorted(rows,key=lambda x:(len(x['path']),x['path']));canonical=rows[0]
            for other in rows[1:]:
                if other.get('content_sha256')==canonical.get('content_sha256'): continue
                e=Edge(edge_id(other['node_id'],canonical['node_id'],'semantic_lineage'),other['node_id'],canonical['node_id'],'semantic_lineage',0.9,{"semantic_sha256":digest})
                self.store.upsert_edge(e);self.store.lineage(other['node_id'],canonical['node_id'],'semantic_lineage','same normalized Python AST');moved+=1
        return {"resolved_unknowns":resolved,"recovered_locations":recovered,"exact_aliases":dupes,"semantic_lineage":moved}
