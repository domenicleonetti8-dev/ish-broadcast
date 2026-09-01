from __future__ import annotations
import argparse,base64,json,mimetypes,os,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,unquote
from .storage import Store
from .pipeline import run_job
ROOT=Path(__file__).resolve().parent; DATA_ROOT=Path(os.environ.get('EIRA_INVENTOR_ARCHIVE',str(ROOT/'archive'))).resolve(); STORE=Store(DATA_ROOT); STATIC=ROOT/'static'; _LOCK=threading.Lock()
def _test_vision(_img,_txt): return {'assembly_id':'test','name':'test','parts':[{'part_id':'p','name':'part','geometry':{'kind':'primitive','primitive':'box','dimensions':{'x':1,'y':1,'z':1}},'transform':{'location':[0,0,0],'rotation_deg':[0,0,0],'scale':[1,1,1]},'source':{'provenance':'assumed','confidence':1.0},'engineering':{}}],'joints':[]}
def process_job(jid):
    if not _LOCK.acquire(blocking=False): return
    try:
        j=STORE.get_job(jid); inv=STORE.get_invention(j['invention_id']); a=inv['assets'][-1]; image=DATA_ROOT/a['relpath']; out=STORE.models/jid
        if os.environ.get('EIRA_INVENTOR_TEST_MODE')=='1':
            j.update(status='starting',updated=time.time()); STORE.save_job(j); j.update(status='vision_running',updated=time.time()); STORE.save_job(j)
            from .compiler import compile_assembly
            compiled,scene=compile_assembly(_test_vision(str(image),inv.get('description',''))); out.mkdir(parents=True,exist_ok=True); glb=out/'assembly.glb'; scene.export(glb); j.update(status='completed',updated=time.time(),model_url=f'/archive/models/{jid}/assembly.glb',error=None); STORE.save_job(j); return
        result=run_job(j,str(image),inv.get('description',''),out)
        if result.get('model_url'): result['model_url']=f'/archive/models/{jid}/assembly.glb'
        STORE.save_job(result)
    except Exception as e:
        try: j=STORE.get_job(jid); j.update(status='failed',updated=time.time(),error=f'{type(e).__name__}:{e}'); STORE.save_job(j)
        except Exception: pass
    finally:_LOCK.release()
class H(BaseHTTPRequestHandler):
    server_version='EIRA-InventorLab/5.0'
    def log_message(self,fmt,*args): print('[InventorLab]',fmt%args,flush=True)
    def sendb(self,c,data,ctype='application/octet-stream'):
        self.send_response(c); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def sendj(self,c,o): self.sendb(c,json.dumps(o,default=str).encode(),'application/json; charset=utf-8')
    def body(self):
        n=int(self.headers.get('Content-Length','0') or '0')
        if n>50_000_000: raise ValueError('request_too_large')
        return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        p=urlparse(self.path).path
        try:
            if p=='/health': return self.sendj(200,{'ok':True,'service':'eira-inventor-v5','data_root':str(DATA_ROOT)})
            if p=='/api/inventions': return self.sendj(200,STORE.list_inventions())
            if p.startswith('/api/inventions/'): return self.sendj(200,STORE.get_invention(unquote(p.rsplit('/',1)[-1])))
            if p.startswith('/api/jobs/'): return self.sendj(200,STORE.get_job(unquote(p.rsplit('/',1)[-1])))
            if p.startswith('/archive/'):
                rel=Path(unquote(p[len('/archive/'):])) ; target=(DATA_ROOT/rel).resolve()
                if DATA_ROOT not in target.parents and target!=DATA_ROOT: raise PermissionError('unsafe_path')
                if not target.is_file(): return self.sendj(404,{'error':'not_found'})
                return self.sendb(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            f=(STATIC/('index.html' if p=='/' else p.lstrip('/'))).resolve()
            if STATIC not in f.parents and f!=STATIC: raise PermissionError('unsafe_path')
            if not f.is_file(): return self.sendj(404,{'error':'not_found'})
            return self.sendb(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'text/plain')
        except (ValueError,KeyError) as e:return self.sendj(404,{'error':str(e)})
        except Exception as e:return self.sendj(500,{'error':f'{type(e).__name__}:{e}'})
    def do_POST(self):
        p=urlparse(self.path).path
        try:
            o=self.body()
            if p=='/api/inventions': return self.sendj(201,STORE.create_invention(o.get('title',''),o.get('description','')))
            if p=='/api/upload': return self.sendj(201,STORE.add_asset(o['invention_id'],o.get('name','asset.bin'),o.get('mime','application/octet-stream'),base64.b64decode(o.get('data_base64',''),validate=True),o.get('kind','source')))
            if p=='/api/render':
                j=STORE.queue_render(o['invention_id'],o.get('mode','engineering_completion')); threading.Thread(target=process_job,args=(j['job_id'],),daemon=True).start(); return self.sendj(202,j)
            if p=='/api/delete-invention': return self.sendj(200,STORE.delete_invention(o['invention_id']))
            return self.sendj(404,{'error':'not_found'})
        except (ValueError,KeyError) as e:return self.sendj(400,{'error':str(e)})
        except Exception as e:return self.sendj(500,{'error':f'{type(e).__name__}:{e}'})
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--host',default='0.0.0.0'); ap.add_argument('--port',type=int,default=8787); a=ap.parse_args(); ThreadingHTTPServer((a.host,a.port),H).serve_forever()
if __name__=='__main__':main()
