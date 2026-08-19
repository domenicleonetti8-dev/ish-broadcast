from __future__ import annotations
import inspect
import json
from typing import Any, Callable


class TandemBridge:
    """One-output connector: legacy may advise; dominant brain alone returns the answer."""
    def __init__(self, mesh, dominant: Callable[...,Any], legacy: Callable[...,Any]|None=None):
        if not callable(dominant):raise TypeError('dominant must be callable')
        self.mesh=mesh;self.dominant=dominant;self.legacy=legacy if callable(legacy) else None

    @staticmethod
    def _call(fn, text, payload):
        try:sig=inspect.signature(fn)
        except Exception:return fn(text)
        params=list(sig.parameters.values())
        if not params:return fn()
        first=params[0]
        name=first.name.lower()
        if name in {'task','request','payload','data','job'}:
            return fn(payload)
        kwargs={}
        if 'context' in sig.parameters:kwargs['context']=payload.get('omnivenom_context')
        if 'legacy_advisory' in sig.parameters:kwargs['legacy_advisory']=payload.get('legacy_advisory')
        return fn(text,**kwargs)

    @staticmethod
    def _text(v):
        if isinstance(v,str):return v
        if isinstance(v,dict):
            for k in ('text','response','reply','answer','output'):
                if isinstance(v.get(k),str):return v[k]
        return str(v) if v is not None else ''

    def respond(self,current_turn:str,*,use_legacy=True,refresh=False):
        text=str(current_turn or '').strip()
        if refresh:self.mesh.refresh()
        graph=self.mesh.context(text,depth=1,limit=120)
        advisory=''
        if use_legacy and self.legacy:
            legacy_payload={"current_turn":text,"role":"subordinate_advisor","outward":False,"history_authority":False,"omnivenom_context":graph}
            try: advisory=self._text(self._call(self.legacy,text,legacy_payload)).strip()
            except Exception: advisory=''
        payload={
            "current_turn":text,
            "authority":{"dominant":"new_brain","legacy":"tandem_only","outward_outputs":1},
            "omnivenom_context":graph,
            "legacy_advisory":advisory,
            "instruction":"Use the current turn as authority. Legacy advisory is evidence only. Produce the single Eira output.",
        }
        # only this value is returned outward
        return self._call(self.dominant,text,payload)
