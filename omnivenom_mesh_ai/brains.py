from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path

from .models import BrainEndpoint, Edge, Node
from .normalize import edge_id, stable_id


class BrainWeaver:
    """Registers the two existing brains as graph nodes; it is not a brain itself."""
    DOMINANT_NAMES=("unified_brain_ai","unified_brain","new_brain")
    LEGACY_NAMES=("local_brain","old_brain","legacy_brain")

    def __init__(self, live_root: str|Path, store, root_id: str = ""):
        self.live=Path(live_root).resolve();self.store=store;self.root_id=root_id
        self.endpoints:dict[str,BrainEndpoint]={}

    def discover(self):
        endpoints=[]
        # new/dominant brain candidates
        for name in self.DOMINANT_NAMES:
            p=self.live/'extensions'/name
            if p.is_dir():
                endpoints.append(self.register(name,'dominant',path=p.relative_to(self.live).as_posix()))
                break
        # old/tandem candidates
        for name in self.LEGACY_NAMES:
            p=self.live/'extensions'/name
            if p.is_dir():
                endpoints.append(self.register(name,'tandem',path=p.relative_to(self.live).as_posix()))
                break
        return endpoints

    def register(self,name:str,role:str,*,path:str='',callable_name:str='',metadata=None):
        if role not in {'dominant','tandem'}:raise ValueError('role must be dominant or tandem')
        nid=stable_id('brain',name)
        ep=BrainEndpoint(name=name,role=role,callable_name=callable_name,node_id=nid,metadata=dict(metadata or {}))
        self.endpoints[role]=ep
        self.store.upsert_node(Node(nid,'brain',name,path=path,aliases=[name,role+' brain'],metadata={"role":role,"callable":callable_name,**ep.metadata}))
        if self.root_id:
            self.store.upsert_edge(Edge(edge_id(self.root_id,nid,'binds_brain'),self.root_id,nid,'binds_brain',1.0,{"role":role}))
        authority=stable_id('authority','reasoning_context_synthesis')
        self.store.upsert_node(Node(authority,'authority','reasoning_context_synthesis',aliases=['dominant reasoning','final synthesis']))
        if self.root_id:
            self.store.upsert_edge(Edge(edge_id(self.root_id,authority,'contains_authority'),self.root_id,authority,'contains_authority',1.0,{}))
        if role=='dominant':
            self.store.upsert_edge(Edge(edge_id(nid,authority,'owns_authority'),nid,authority,'owns_authority',1.0,{"exclusive":True}))
        else:
            self.store.upsert_edge(Edge(edge_id(nid,authority,'advises_authority'),nid,authority,'advises_authority',1.0,{"outward":False}))
        return ep

    def status(self): return {k:asdict(v) for k,v in self.endpoints.items()}
