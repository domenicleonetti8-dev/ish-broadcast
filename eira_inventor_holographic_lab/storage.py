from __future__ import annotations
import json,time,uuid,hashlib,re
from pathlib import Path
class Store:
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True); self.inv=self.root/'inventions'; self.jobs=self.root/'jobs'; self.files=self.root/'files'; self.models=self.root/'models'
        for p in (self.inv,self.jobs,self.files,self.models): p.mkdir(parents=True,exist_ok=True)
    def _read(self,p,default=None):
        try:return json.loads(p.read_text())
        except FileNotFoundError:return default
    def _write(self,p,obj):
        tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(obj,indent=2,default=str)); tmp.replace(p); return obj
    def list_inventions(self):
        out=[self._read(p) for p in self.inv.glob('inv_*.json')]; return sorted([x for x in out if x],key=lambda x:x.get('updated',0),reverse=True)
    def create_invention(self,title,description=''):
        title=' '.join(str(title).split()).strip()
        if not title: raise ValueError('title_required')
        norm=re.sub(r'\s+',' ',title.lower())
        for x in self.list_inventions():
            if re.sub(r'\s+',' ',x.get('title','').lower())==norm: x['duplicate_detected']=True; return x
        now=time.time(); iid='inv_'+uuid.uuid4().hex; return self._write(self.inv/f'{iid}.json',{'id':iid,'title':title,'description':str(description),'created':now,'updated':now,'version':1,'assets':[],'notes':[]})
    def get_invention(self,iid):
        x=self._read(self.inv/f'{iid}.json')
        if not x: raise KeyError('invention_not_found')
        return x
    def delete_invention(self,iid):
        x=self.get_invention(iid); (self.inv/f'{iid}.json').unlink(); return {'deleted':iid,'title':x.get('title')}
    def add_asset(self,iid,name,mime,data,kind='source'):
        x=self.get_invention(iid); aid='asset_'+uuid.uuid4().hex; d=self.files/iid; d.mkdir(exist_ok=True); safe=re.sub(r'[^A-Za-z0-9._-]+','_',Path(name).name)[:100] or 'asset.bin'; rel=f'files/{iid}/{aid}_{safe}'; p=self.root/rel; p.write_bytes(data)
        a={'id':aid,'invention_id':iid,'name':safe,'mime':mime,'relpath':rel,'sha256':hashlib.sha256(data).hexdigest(),'kind':kind,'created':time.time()}; x.setdefault('assets',[]).append(a); x['version']=int(x.get('version',0))+1; x['updated']=time.time(); self._write(self.inv/f'{iid}.json',x); return a
    def queue_render(self,iid,mode='engineering_completion',options=None):
        inv=self.get_invention(iid)
        if not inv.get('assets'): raise ValueError('source_asset_required')
        opts=dict(options or {})
        allowed={
            'repair_attempts','visual_review','review_model','visual_review_threshold','visual_review_timeout_s',
            'blender_timeout_s','preview_resolution','support_gap_m','forbidden_overlap_m3','duration_s','fps'
        }
        clean={k:opts[k] for k in allowed if k in opts}
        jid='render_'+uuid.uuid4().hex
        j={'job_id':jid,'invention_id':iid,'mode':str(mode),'created':time.time(),'updated':time.time(),'status':'queued','error':None,'model_url':None,**clean}
        return self._write(self.jobs/f'{jid}.json',j)
    def get_job(self,jid):
        j=self._read(self.jobs/f'{jid}.json')
        if not j: raise KeyError('job_not_found')
        return j
    def save_job(self,j): return self._write(self.jobs/f"{j['job_id']}.json",j)
