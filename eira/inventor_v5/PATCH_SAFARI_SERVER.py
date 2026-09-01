#!/usr/bin/env python3
from pathlib import Path
import textwrap, py_compile, json

ROOT=Path.cwd()
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'
if not EXT.is_dir(): raise SystemExit('FAIL: extension_not_found')

server = r'''
from __future__ import annotations
import base64,json,mimetypes,os,shutil,threading,time,traceback,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs

from .pipeline import run_invention

ROOT=Path(__file__).resolve().parent
INV=ROOT/'inventions'; INV.mkdir(parents=True,exist_ok=True)
JOBS={}; LOCK=threading.Lock()

HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Eira Inventor Lab V5</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:18px}main{max-width:920px;margin:auto}.card{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:16px;margin:12px 0}h1{font-size:26px}input,textarea,button{width:100%;box-sizing:border-box;margin:7px 0;padding:12px;border-radius:10px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}button{background:#238636;font-weight:700}.muted{color:#8b949e;font-size:13px}.good{color:#3fb950}.bad{color:#f85149}a{color:#58a6ff}pre{white-space:pre-wrap;word-break:break-word;background:#0d1117;padding:12px;border-radius:10px;max-height:320px;overflow:auto}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:600px){.row{grid-template-columns:1fr}}</style></head><body><main>
<h1>Eira Invention Lab V5</h1><div class="muted">Isolated drawing/image → interpreted engineering model → inspect/repair → iPhone AR USDZ</div>
<div class="card"><input id="title" placeholder="Invention title"><textarea id="desc" rows="7" placeholder="Describe the invention, function, systems, dimensions, materials, behavior, and anything the drawing does not show."></textarea><input id="files" type="file" accept="image/*" multiple><button id="go">Build Invention</button><div id="upload" class="muted"></div></div>
<div class="card"><b>Status</b><div id="status" class="muted">idle</div><pre id="report"></pre><div id="links"></div></div>
<script>
const $=x=>document.getElementById(x); let job=null,timer=null;
async function api(u,o){let r=await fetch(u,o);let t=await r.text();if(!r.ok)throw Error(t);return t?JSON.parse(t):{}}
$('go').onclick=async()=>{try{$('go').disabled=true;$('status').textContent='uploading';let imgs=[];for(const f of $('files').files){let b64=await new Promise((res,rej)=>{let r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(f)});imgs.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:b64})}$('upload').textContent=imgs.length+' image(s) attached';let j=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('title').value||'Untitled invention',description:$('desc').value,images:imgs})});job=j.id;poll()}catch(e){$('status').textContent=e.message;$('status').className='bad';$('go').disabled=false}}
async function poll(){if(!job)return;try{let j=await api('/api/jobs/'+job);$('status').textContent=j.status+(j.stage?' — '+j.stage:'');$('report').textContent=JSON.stringify(j,null,2);if(j.status==='completed'){clearTimeout(timer);$('go').disabled=false;$('status').className='good';$('links').innerHTML=`<div class="row"><a href="${j.usdz_url}">Open / Download USDZ</a><a href="${j.glb_url}">Open GLB</a></div>`;return}if(j.status==='failed'){clearTimeout(timer);$('go').disabled=false;$('status').className='bad';return}timer=setTimeout(poll,1500)}catch(e){$('status').textContent=e.message;$('go').disabled=false}}
</script></main></body></html>'''

def json_bytes(x): return json.dumps(x,default=str).encode()
def safe_name(s):
 s=''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(s)); return s[:120] or 'file'

def _vision_provider():
 # Prefer extension-local provider adapter if present; fall back to legacy adapter names.
 candidates=[('vision_provider','get_provider'),('vision_runtime','get_provider'),('vision_assembly','provider')]
 for mod,attr in candidates:
  try:
   m=__import__(f'extensions.eira_inventor_holographic_lab.{mod}',fromlist=[attr]); p=getattr(m,attr)
   return p() if callable(p) and attr=='get_provider' else p
  except Exception: pass
 raise RuntimeError('vision_provider_not_configured: add extension-local vision provider adapter')

def worker(job_id):
 with LOCK: j=JOBS[job_id]; j['status']='running'; j['stage']='vision/build/inspect/repair'
 try:
  out=Path(j['output_dir']); provider=_vision_provider()
  r=run_invention(description=j['description'],images=[Path(x) for x in j['images']],output_dir=out,vision_provider=provider,blender='blender',max_repairs=4)
  with LOCK:
   j.update({'status':'completed','stage':'accepted','report':r,'usdz_url':f'/artifact/{job_id}/model.usdz','glb_url':f'/artifact/{job_id}/model.glb'})
 except Exception as e:
  with LOCK: j.update({'status':'failed','stage':'error','error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()[-5000:]})

def send(h,code,data,ctype='application/json'):
 if isinstance(data,str): data=data.encode()
 h.send_response(code);h.send_header('Content-Type',ctype);h.send_header('Content-Length',str(len(data)));h.send_header('Cache-Control','no-store');h.end_headers();h.wfile.write(data)

class H(BaseHTTPRequestHandler):
 server_version='EiraInventorV5/5.2'
 def log_message(self,fmt,*args): print('[InventorV5] '+fmt%args,flush=True)
 def do_GET(self):
  p=urlparse(self.path).path
  if p=='/': return send(self,200,HTML,'text/html; charset=utf-8')
  if p=='/api/health': return send(self,200,json_bytes({'ok':True,'version':'5.2.0','root':str(ROOT)}))
  if p.startswith('/api/jobs/'):
   i=p.rsplit('/',1)[-1]
   with LOCK: j=JOBS.get(i)
   return send(self,200 if j else 404,json_bytes(j or {'error':'not_found'}))
  if p.startswith('/artifact/'):
   parts=p.strip('/').split('/')
   if len(parts)!=3:return send(self,404,b'not found','text/plain')
   _,jid,name=parts; j=JOBS.get(jid)
   if not j:return send(self,404,b'not found','text/plain')
   f=Path(j['output_dir'])/safe_name(name)
   if not f.is_file():return send(self,404,b'not found','text/plain')
   return send(self,200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
  return send(self,404,b'not found','text/plain')
 def do_POST(self):
  if urlparse(self.path).path!='/api/jobs': return send(self,404,b'not found','text/plain')
  try:
   n=int(self.headers.get('Content-Length','0')); obj=json.loads(self.rfile.read(n) or b'{}'); jid=uuid.uuid4().hex[:12]; out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid); src=out/'source';src.mkdir(parents=True)
   imgs=[]
   for k,x in enumerate(obj.get('images') or []):
    name=safe_name(x.get('name') or f'image_{k}.jpg'); f=src/name; f.write_bytes(base64.b64decode(x.get('data_base64') or '',validate=True)); imgs.append(str(f))
   j={'id':jid,'status':'queued','stage':'queued','title':obj.get('title') or 'Untitled invention','description':obj.get('description') or '','images':imgs,'output_dir':str(out),'created_at':time.time()}
   with LOCK:JOBS[jid]=j
   threading.Thread(target=worker,args=(jid,),daemon=True).start();return send(self,201,json_bytes(j))
  except Exception as e:return send(self,400,json_bytes({'error':f'{type(e).__name__}:{e}'}))

def main(host='0.0.0.0',port=8787):
 print(f'EIRA_INVENTOR_V5_SERVER http://{host}:{port}',flush=True); ThreadingHTTPServer((host,port),H).serve_forever()
if __name__=='__main__':
 import argparse;a=argparse.ArgumentParser();a.add_argument('--host',default='0.0.0.0');a.add_argument('--port',type=int,default=8787);x=a.parse_args();main(x.host,x.port)
'''

(EXT/'server.py').write_text(textwrap.dedent(server).lstrip(),encoding='utf-8')
py_compile.compile(str(EXT/'server.py'),doraise=True)

m=EXT/'manifest.json'
obj=json.loads(m.read_text())
obj['version']='5.2.0'
obj['web']={'module':'server','default_host':'0.0.0.0','default_port':8787,'path':'/'}
m.write_text(json.dumps(obj,indent=2)+'\n')
print('SAFARI_SERVER_PATCH_PASS')
print('PAGE: http://100.107.25.56:8787/')
