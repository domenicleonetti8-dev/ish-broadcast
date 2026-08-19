from __future__ import annotations
from pathlib import Path

from .brains import BrainWeaver
from .crawler import LiveCrawler
from .registry import FindableRegistry
from .resolver import MorphResolver
from .store import MeshStore
from .topology import Topology


class Omnivenom:
    """Standalone neural/spiderweb connective fabric. Contains no language model or brain."""
    def __init__(self, live_root: str|Path, state_path: str|Path|None=None):
        self.live=Path(live_root).expanduser().resolve()
        state=Path(state_path) if state_path else self.live/'data'/'omnivenom'/'mesh.sqlite3'
        self.store=MeshStore(state)
        self.crawler=LiveCrawler(self.live,self.store)
        self.registry=FindableRegistry(self.store)
        self.resolver=MorphResolver(self.store)
        self.brains=BrainWeaver(self.live,self.store,self.crawler.root_id)
        self.topology=Topology(self.store,self.crawler.root_id)

    def refresh(self):
        scan=self.crawler.scan()
        brain=[x.name for x in self.brains.discover()]
        morph=self.resolver.reconcile()
        return {"scan":scan,"brains":brain,"morph":morph,"topology":self.topology.audit()}

    def find(self,query:str,limit:int=20):return self.registry.find(query,limit)
    def context(self,query:str,depth:int=1,limit:int=250):return self.registry.neighborhood(query,depth=depth,limit=limit)
    def status(self):return {**self.store.counts(),"brains":self.brains.status(),"topology":self.topology.audit()}

    def bind(self,dominant,legacy=None):
        from .tandem import TandemBridge
        self.brains.register(getattr(dominant,'__name__','new_brain'),'dominant',callable_name=getattr(dominant,'__name__',''))
        if legacy:self.brains.register(getattr(legacy,'__name__','old_brain'),'tandem',callable_name=getattr(legacy,'__name__',''))
        return TandemBridge(self,dominant,legacy)

    def close(self): self.store.close()
    def __enter__(self): return self
    def __exit__(self,*exc): self.close()
