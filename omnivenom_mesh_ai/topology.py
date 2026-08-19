from __future__ import annotations
from collections import deque


class Topology:
    def __init__(self, store, root_id: str):self.store=store;self.root_id=root_id

    def audit(self):
        nodes=self.store.nodes();edges=self.store.edges();ids={n['node_id'] for n in nodes}
        graph={x:set() for x in ids}
        for e in edges:
            a,b=e['source'],e['target']
            if a in graph and b in graph:
                graph[a].add(b);graph[b].add(a)
        seen=set();q=deque([self.root_id] if self.root_id in graph else [])
        while q:
            n=q.popleft()
            if n in seen:continue
            seen.add(n);q.extend(graph[n]-seen)
        unreachable=sorted(ids-seen)
        return {"nodes":len(nodes),"edges":len(edges),"reachable":len(seen),"unreachable":len(unreachable),"unreachable_ids":unreachable[:50]}
