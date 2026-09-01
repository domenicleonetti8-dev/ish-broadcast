#!/usr/bin/env python3
from pathlib import Path
import json, py_compile, textwrap

ROOT = Path.cwd()
EXT = ROOT / 'extensions' / 'eira_inventor_holographic_lab'
if not EXT.is_dir():
    raise SystemExit('FAIL: extension_not_found')

SERVER = r"""
from __future__ import annotations
import base64,json,mimetypes,os,subprocess,sys,threading,time,traceback,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote

from .pipeline import run_invention

ROOT=Path(__file__).resolve().parent
INV=ROOT/'inventions'; INV.mkdir(parents=True,exist_ok=True)
JOBS={}; LOCK=threading.Lock()

HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Eira Invention Lab V5</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:18px}main{max-width:980px;margin:auto}.card{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:16px;margin:12px 0}h1{font-size:26px}input,textarea,button{width:100%;box-sizing:border-box;margin:7px 0;padding:12px;border-radius:10px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}button{background:#238636;font-weight:700}.muted{color:#8b949e;font-size:13px}.good{color:#3fb950}.bad{color:#f85149}a{color:#58a6ff}.item{border-top:1px solid #30363d;padding:12px 0}.item:first-child{border-top:0}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:650px){.row{grid-template-columns:1fr}}pre{white-space:pre-wrap;word-break:break-word;background:#0d1117;padding:12px;border-radius:10px;max-height:320px;overflow:auto}.links a{display:inline-block;margin:5px 10px 5px 0}</style></head><body><main>
<h1>Eira Invention Lab V5</h1><div class="muted">Isolated drawing/image to interpreted engineering model to inspect/repair to iPhone AR USDZ</div>
<div class="card"><h3>Build New Invention</h3><input id="title" placeholder="Invention title"><textarea id="desc" rows="7" placeholder="Describe function, systems, dimensions, materials, behavior, and anything the drawing does not show."></textarea><input id="files" type="file" accept="image/*" multiple><button id="go">Build Invention</button><div id="upload" class="muted"></div></div>
<div class="card"><h3>Current Job</h3><div id="status" class="muted">idle</div><pre id="report"></pre><div id="links" class="links"></div></div>
<div class="card"><h3>Archive</h3><input id="search" placeholder="Search title, description, date, job id"><button id="searchBtn">Search Archive</button><div id="archive" class="muted">Loading archive...</div></div>
<script>
const $=x=>document.getElementById(x);let job=null,timer=null;
async function api(u,o){let r=await fetch(u,o);let t=await r.text();if(!r.ok)throw Error(t);return t?JSON.parse(t):{}}
function artLinks(a){let x=[];for(const [k,v] of Object.entries(a||{})){x.push(`<a href="${v}">${k}</a>`)}return x.join(' ')}
$('go').onclick=async()=>{try{$('go').disabled=true;$('status').textContent='uploading';let imgs=[];for(const f of $('files').files){let b64=await new Promise((res,rej)=>{let r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(f)});imgs.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:b64})}$('upload').textContent=imgs.length+' image(s) attached';let j=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('title').value||'Untitled invention',description:$('desc').value,images:imgs})});job=j.id;poll()}catch(e){$('status').textContent=e.message;$('status').className='bad';$('go').disabled=false}}
async function poll(){if(!job)return;try{let j=await api('/api/jobs/'+job);$('status').textContent=j.status+(j.stage?' - '+j.stage:'');$('report').textContent=JSON.stringify(j,null,2);if(j.status==='completed'){clearTimeout(timer);$('go').disabled=false;$('status').className='good';$('links').innerHTML=artLinks(j.artifacts);loadArchive();return}if(j.status==='failed'){clearTimeout(timer);$('go').disabled=false;$('status').className='bad';loadArchive();return}timer=setTimeout(poll,1500)}catch(e){$('status').textContent=e.message;$('go').disabled=false}}
async function loadArchive(){try{let q=encodeURIComponent($('search').value||'');let d=await api('/api/archive?q='+q);$('archive').innerHTML=d.items.length?d.items.map(x=>`<div class="item"><b>${x.title}</b><div class="muted">${x.created} - ${x.status} - ${x.id}</div><div>${x.description||''}</div><div class="links">${artLinks(x.artifacts)}</div></div>`).join(''):'No matching inventions found.'}catch(e){$('archive').textContent=e.message}}
$('searchBtn').onclick=loadArchive;$('search').onkeydown=e=>{if(e.key==='Enter')loadArchive()};loadArchive();
</script></main></body></html>'''

def safe_name(s):
 s=''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(s)); return s[:140] or 'file'
def send(h,code,data,ctype='application/json'):
 if not isinstance(data,(bytes,bytearray)): data=(data if isinstance(data,str) else json.dumps(data,default=str)).encode('utf-8')
 h.send_response(code);h.send_header('Content-Type',ctype);h.send_header('Content-Length',str(len(data)));h.send_header('Cache-Control','no-store');h.end_headers();h.wfile.write(data)
def meta_path(out): return Path(out)/'archive.json'
def save_meta(j):
 p=meta_path(j['output_dir']); p.write_text(json.dumps({k:v for k,v in j.items() if k!='traceback'},indent=2,default=str)+'\n',encoding='utf-8')
def artifacts_for(out,jid):
 out=Path(out); d={}
 for fn,label in [('model.usdz','USDZ / Open in AR'),('model.glb','GLB'),('invention_spec.json','Invention Spec'),('inspection_report.json','Inspection Report')]:
  if (out/fn).is_file(): d[label]=f'/archive_artifact/{out.name}/{fn}'
 src=out/'source'
 if src.is_dir():
  for f in sorted(src.iterdir()):
   if f.is_file(): d['Source: '+f.name]=f'/archive_artifact/{out.name}/source/{f.name}'
 return d

def scan_archive(q=''):
 q=q.lower().strip(); items=[]
 for out in sorted([p for p in INV.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True):
  m={}
  try:
   if meta_path(out).is_file(): m=json.loads(meta_path(out).read_text())
  except Exception: pass
  rid=str(m.get('id') or out.name); title=str(m.get('title') or out.name); desc=str(m.get('description') or '')
  created=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(float(m.get('created_at') or out.stat().st_mtime)))
  status=str(m.get('status') or ('completed' if (out/'model.usdz').is_file() else 'saved'))
  hay=' '.join([rid,title,desc,created,out.name]).lower()
  if q and q not in hay: continue
  items.append({'id':rid,'title':title,'description':desc,'created':created,'status':status,'folder':out.name,'artifacts':artifacts_for(out,rid)})
 return items[:200]

def _vision_provider():
 candidates=[('vision_provider','get_provider'),('vision_runtime','get_provider'),('vision_assembly','provider')]
 for mod,attr in candidates:
  try:
   m=__import__(f'extensions.eira_inventor_holographic_lab.{mod}',fromlist=[attr]); p=getattr(m,attr)
   return p() if callable(p) and attr=='get_provider' else p
  except Exception: pass
 raise RuntimeError('vision_provider_not_configured: add extension-local vision provider adapter')

def worker(job_id):
 with LOCK:
  j=JOBS[job_id];j['status']='running';j['stage']='vision/build/inspect/repair';save_meta(j)
 try:
  out=Path(j['output_dir']); r=run_invention(description=j['description'],images=[Path(x) for x in j['images']],output_dir=out,vision_provider=_vision_provider(),blender='blender',max_repairs=4)
  with LOCK:
   j.update({'status':'completed','stage':'accepted','report':r,'artifacts':artifacts_for(out,job_id)});save_meta(j)
 except Exception as e:
  with LOCK:
   j.update({'status':'failed','stage':'error','error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()[-5000:]});save_meta(j)

class H(BaseHTTPRequestHandler):
 server_version='EiraInventorV5/5.3'
 def log_message(self,fmt,*args): print('[InventorV5] '+fmt%args,flush=True)
 def do_GET(self):
  u=urlparse(self.path); p=u.path
  if p=='/': return send(self,200,HTML,'text/html; charset=utf-8')
  if p=='/api/health': return send(self,200,{'ok':True,'version':'5.3.0','archive_count':len(scan_archive())})
  if p=='/api/archive': return send(self,200,{'items':scan_archive(parse_qs(u.query).get('q',[''])[0])})
  if p.startswith('/api/jobs/'):
   i=p.rsplit('/',1)[-1]
   with LOCK:j=JOBS.get(i)
   return send(self,200 if j else 404,j or {'error':'not_found'})
  if p.startswith('/archive_artifact/'):
   rel=unquote(p[len('/archive_artifact/'):]); parts=Path(rel).parts
   if not parts:return send(self,404,'not found','text/plain')
   root=(INV/parts[0]).resolve(); f=(INV/rel).resolve()
   if root.parent!=INV.resolve() or (root!=f and root not in f.parents) or not f.is_file(): return send(self,404,'not found','text/plain')
   c=mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
   if f.suffix.lower()=='.usdz': c='model/vnd.usdz+zip'
   return send(self,200,f.read_bytes(),c)
  return send(self,404,{'error':'not_found'})
 def do_POST(self):
  if urlparse(self.path).path!='/api/jobs': return send(self,404,{'error':'not_found'})
  try:
   n=int(self.headers.get('Content-Length','0')); obj=json.loads(self.rfile.read(n) or b'{}'); jid=uuid.uuid4().hex[:12]; out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid); src=out/'source';src.mkdir(parents=True)
   imgs=[]
   for k,x in enumerate(obj.get('images') or []):
    name=safe_name(x.get('name') or f'image_{k}.jpg'); f=src/name; f.write_bytes(base64.b64decode(x.get('data_base64') or '',validate=True)); imgs.append(str(f))
   j={'id':jid,'status':'queued','stage':'queued','title':obj.get('title') or 'Untitled invention','description':obj.get('description') or '','images':imgs,'output_dir':str(out),'created_at':time.time()};save_meta(j)
   with LOCK:JOBS[jid]=j
   threading.Thread(target=worker,args=(jid,),daemon=True).start();return send(self,201,j)
  except Exception as e:return send(self,400,{'error':f'{type(e).__name__}:{e}'})

def main(host='0.0.0.0',port=8787):
 print(f'EIRA_INVENTOR_V5_SERVER http://{host}:{port}',flush=True);ThreadingHTTPServer((host,port),H).serve_forever()
if __name__=='__main__':
 import argparse;a=argparse.ArgumentParser();a.add_argument('--host',default='0.0.0.0');a.add_argument('--port',type=int,default=8787);x=a.parse_args();main(x.host,x.port)
"""

(EXT/'server.py').write_text(textwrap.dedent(SERVER).lstrip(),encoding='utf-8')
py_compile.compile(str(EXT/'server.py'),doraise=True)

manifest=EXT/'manifest.json'; obj=json.loads(manifest.read_text()); obj['version']='5.3.0'; obj['web']={'module':'server','default_host':'0.0.0.0','default_port':8787,'path':'/','archive_search':True}; manifest.write_text(json.dumps(obj,indent=2)+'\n')

site=ROOT/'sitecustomize.py'
HOOK="""# EIRA_INVENTOR_V5_AUTOSTART\nimport os,sys,subprocess,socket\ntry:\n    if os.path.basename(sys.argv[0])=='main.py':\n        s=socket.socket();s.settimeout(.15)\n        alive=(s.connect_ex(('127.0.0.1',8787))==0);s.close()\n        if not alive:\n            log=open('/tmp/eira_inventor_v5_server.log','ab',buffering=0)\n            subprocess.Popen([sys.executable,'-m','extensions.eira_inventor_holographic_lab.server','--host','0.0.0.0','--port','8787'],cwd=os.getcwd(),stdout=log,stderr=log,start_new_session=True)\nexcept Exception:\n    pass\n"""
old=site.read_text() if site.exists() else ''
if '# EIRA_INVENTOR_V5_AUTOSTART' in old:
 old=old.split('# EIRA_INVENTOR_V5_AUTOSTART')[0].rstrip()+'\n'
site.write_text(old+HOOK,encoding='utf-8')
py_compile.compile(str(site),doraise=True)
print('SAFARI_ARCHIVE_FINAL_PATCH_PASS')
print('PAGE: http://100.107.25.56:8787/')
