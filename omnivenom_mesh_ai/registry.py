from __future__ import annotations
import json
from .normalize import norm, tokens


class FindableRegistry:
    def __init__(self, store): self.store=store

    @staticmethod
    def _decode(row):
        d=dict(row)
        for key in ('aliases_json','capabilities_json','metadata_json','evidence_json'):
            if key in d:
                try:d[key[:-5] if key.endswith('_json') else key]=json.loads(d[key])
                except Exception:d[key[:-5] if key.endswith('_json') else key]={} if key=='metadata_json' else []
        return d

    def find(self, query: str, limit: int = 20):
        q=str(query or '').strip()
        if not q:return []
        # stable IDs are always directly findable
        direct=self.store.node(q)
        if direct:return [self._decode(direct)]
        nq=norm(q);qt=tokens(q)
        rows=self.store.aliases(nq,limit=max(100,limit*8))
        by={}
        for r in rows:
            nid=r['node_id'];alias=str(r.get('alias') or '')
            nt=tokens(' '.join([r.get('name',''),r.get('path',''),alias,r.get('aliases_json',''),r.get('capabilities_json','')]))
            overlap=len(qt & nt)
            exact=1 if norm(alias)==nq else 0
            prefix=1 if norm(alias).startswith(nq) else 0
            state_bonus=1 if r.get('state')=='active' else 0
            score=exact*100+prefix*25+overlap*10+state_bonus
            if score>by.get(nid,(-1,None))[0]:by[nid]=(score,r)
        ordered=sorted(by.values(),key=lambda x:(-x[0],len(x[1].get('path','')),x[1].get('path','')))
        return [self._decode(r) for _,r in ordered[:limit]]

    def neighborhood(self, query: str, *, depth: int = 1, limit: int = 250):
        roots=self.find(query,limit=12)
        ids=[x['node_id'] for x in roots]
        edges,node_ids=self.store.neighborhood(ids,depth=depth,limit=limit)
        nodes=[]
        for nid in node_ids:
            n=self.store.node(nid)
            if n:nodes.append(self._decode(n))
        return {"roots":roots,"nodes":nodes,"edges":[self._decode(x) for x in edges]}
