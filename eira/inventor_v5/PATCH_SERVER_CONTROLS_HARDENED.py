#!/usr/bin/env python3
from pathlib import Path
import json, py_compile, textwrap

ROOT=Path.cwd()
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'
if not EXT.is_dir(): raise SystemExit('FAIL: extension_not_found')

SERVER=r'''from __future__ import annotations
import base64,json,mimetypes,threading,time,traceback,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote
from .pipeline import run_invention

ROOT=Path(__file__).resolve().parent
INV=ROOT/'inventions'; INV.mkdir(parents=True,exist_ok=True)
JOBS={}; LOCK=threading.Lock()

HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Eira Invention Lab</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:18px}main{max-width:980px;margin:auto}.card{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:16px;margin:14px 0}h1{font-size:27px}h3{font-size:22px}input,textarea,button{width:100%;box-sizing:border-box;margin:7px 0;padding:13px;border-radius:10px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px}button{background:#238636;font-weight:800}.muted{color:#8b949e}.good{color:#3fb950}.bad{color:#f85149}a{color:#58a6ff}.item{border-top:1px solid #30363d;padding:14px 0}.item:first-child{border-top:0}.links a{display:inline-block;margin:5px 12px 5px 0}pre{white-space:pre-wrap;word-break:break-word;background:#0d1117;padding:12px;border-radius:10px;max-height:320px;overflow:auto}</style></head><body><main>
<h1>Eira Invention Lab V5</h1>
<div class="card"><h3>Build New Invention</h3><input id="title" placeholder="Invention title"><textarea id="desc" rows="6" placeholder="Describe function, systems, dimensions, materials, behavior, and anything the drawing does not show."></textarea><input id="files" type="file" accept="image/*" multiple><button id="go" type="button">Build Invention</button><div id="upload" class="muted"></div></div>
<div class="card"><h3>Current Job</h3><div id="status" class="muted">idle</div><pre id="report"></pre><div id="links" class="links"></div></div>
<div class="card"><h3>Direct Archive Upload</h3><input id="arc_title" placeholder="Archive title"><textarea id="arc_desc" rows="3" placeholder="Description / notes"></textarea><input id="arc_files" type="file" accept="image/*,.usdz,model/vnd.usdz+zip,application/octet-stream" multiple><button id="arc_upload" type="button">Add Files to Archive</button><div id="arc_status" class="muted"></div></div>
<div class="card"><h3>Archive</h3><input id="search" placeholder="Search title, description, date, job id"><button id="searchBtn" type="button">Search Archive</button><div id="archive" class="muted">Loading archive...</div></div>
<script>
const $=id=>document.getElementById(id);let job=null,timer=null;
async function api(url,opt){const r=await fetch(url,opt);const t=await r.text();let x={};try{x=t?JSON.parse(t):{}}catch(_){throw Error('Server returned non-JSON: '+t.slice(0,300))}if(!r.ok)throw Error(x.error||t||('HTTP '+r.status));return x}
function b64file(f){return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=()=>rej(Error('Could not read '+f.name));r.readAsDataURL(f)})}
function artLinks(a){return Object.entries(a||{}).map(([k,v])=>`<a href="${v}">${k}</a>`).join(' ')}
async function loadArchive(){try{const d=await api('/api/archive?q='+encodeURIComponent($('search').value||''));$('archive').innerHTML=d.items.length?d.items.map(x=>`<div class="item"><b>${x.title}</b><div class="muted">${x.created} - ${x.status}</div><div>${x.description||''}</div><div class="links">${artLinks(x.artifacts)}</div></div>`).join(''):'No matching inventions found.'}catch(e){$('archive').textContent=e.message;$('archive').className='bad'}}
$('searchBtn').addEventListener('click',loadArchive);$('search').addEventListener('keydown',e=>{if(e.key==='Enter')loadArchive()});
$('arc_upload').addEventListener('click',async()=>{const btn=$('arc_upload');try{const fs=[...$('arc_files').files];if(!fs.length)throw Error('Choose at least one image or USDZ');btn.disabled=true;$('arc_status').className='muted';$('arc_status').textContent='Reading '+fs.length+' file(s)...';const files=[];for(const f of fs)files.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:await b64file(f)});$('arc_status').textContent='Uploading to Eira archive...';const j=await api('/api/archive-upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('arc_title').value||'Archived files',description:$('arc_desc').value||'',files})});$('arc_status').className='good';$('arc_status').textContent='Archived successfully: '+j.title+' ('+j.stored_files.length+' file(s))';$('arc_files').value='';await loadArchive()}catch(e){$('arc_status').className='bad';$('arc_status').textContent='Archive upload failed: '+e.message}finally{btn.disabled=false}});
$('go').addEventListener('click',async()=>{const btn=$('go');try{btn.disabled=true;$('status').className='muted';$('status').textContent='Reading images...';const imgs=[];for(const f of $('files').files)imgs.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:await b64file(f)});const j=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('title').value||'Untitled invention',description:$('desc').value||'',images:imgs})});job=j.id;poll()}catch(e){$('status').className='bad';$('status').textContent='Build request failed: '+e.message;btn.disabled=false}});
async function poll(){if(!job)return;try{const j=await api('/api/jobs/'+job);$('status').textContent=j.status+(j.stage?' - '+j.stage:'');$('report').textContent=JSON.stringify(j,null,2);if(j.status==='completed'||j.status==='failed'){clearTimeout(timer);$('go').disabled=false;$('status').className=j.status==='completed'?'good':'bad';$('links').innerHTML=artLinks(j.artifacts);await loadArchive();return}timer=setTimeout(poll,1500)}catch(e){$('status').className='bad';$('status').textContent=e.message;$('go').disabled=false}}
loadArchive();
</script></main></body></html>'''

def safe_name(s):
 s=''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(s));return s[:160] or 'file'
def send(h,code,data,ctype='application/json'):
 if not isinstance(data,(bytes,bytearray)):data=(data if isinstance(data,str) else json.dumps(data,default=str)).encode('utf-8')
 h.send_response(code);h.send_header('Content-Type',ctype);h.send_header('Content-Length',str(len(data)));h.send_header('Cache-Control','no-store');h.end_headers();h.wfile.write(data)
def meta_path(out):return Path(out)/'archive.json'
def save_meta(j):meta_path(j['output_dir']).write_text(json.dumps({k:v for k,v in j.items() if k!='traceback'},indent=2,default=str)+'\n',encoding='utf-8')
def artifacts_for(out,jid):
 out=Path(out);d={}
 for f in sorted(out.rglob('*')):
  if not f.is_file() or f.name in {'archive.json','archive_entry.json'}:continue
  rel=f.relative_to(out).as_posix(); label=('USDZ / Open in AR' if f.suffix.lower()=='.usdz' else ('Image: '+f.name if f.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.heic','.gif'} else 'File: '+rel))
  d[label]=f'/archive_artifact/{out.name}/{rel}'
 return d
def scan_archive(q=''):
 q=q.lower().strip();items=[]
 for out in sorted((p for p in INV.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime,reverse=True):
  try:m=json.loads(meta_path(out).read_text()) if meta_path(out).is_file() else {}
  except Exception:m={}
  rid=str(m.get('id') or out.name);title=str(m.get('title') or out.name);desc=str(m.get('description') or '');created=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(float(m.get('created_at') or out.stat().st_mtime)));status=str(m.get('status') or 'saved');hay=' '.join((rid,title,desc,created,out.name)).lower()
  if q and q not in hay:continue
  items.append({'id':rid,'title':title,'description':desc,'created':created,'status':status,'artifacts':artifacts_for(out,rid)})
 return items[:200]
def _vision_provider():
 for mod,attr in [('vision_provider','get_provider'),('vision_runtime','get_provider'),('vision_assembly','provider')]:
  try:
   m=__import__(f'extensions.eira_inventor_holographic_lab.{mod}',fromlist=[attr]);p=getattr(m,attr);return p() if callable(p) and attr=='get_provider' else p
  except Exception:pass
 raise RuntimeError('vision_provider_not_configured')
def worker(job_id):
 with LOCK:j=JOBS[job_id];j['status']='running';j['stage']='vision/build/inspect/repair';save_meta(j)
 try:
  out=Path(j['output_dir']);r=run_invention(description=j['description'],images=[Path(x) for x in j['images']],output_dir=out,vision_provider=_vision_provider(),blender='blender',max_repairs=4)
  with LOCK:j.update({'status':'completed','stage':'accepted','report':r,'artifacts':artifacts_for(out,job_id)});save_meta(j)
 except Exception as e:
  with LOCK:j.update({'status':'failed','stage':'error','error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc()[-5000:]});save_meta(j)

class H(BaseHTTPRequestHandler):
 server_version='EiraInventorV5/5.6'
 def log_message(self,fmt,*args):print('[InventorV5] '+fmt%args,flush=True)
 def do_GET(self):
  u=urlparse(self.path);p=u.path
  if p=='/':return send(self,200,HTML,'text/html; charset=utf-8')
  if p=='/api/health':return send(self,200,{'ok':True,'version':'5.6.0','archive_count':len(scan_archive()),'controls':['build','archive-upload','archive-search']})
  if p=='/api/archive':return send(self,200,{'items':scan_archive(parse_qs(u.query).get('q',[''])[0])})
  if p.startswith('/api/jobs/'):
   i=p.rsplit('/',1)[-1]
   with LOCK:j=JOBS.get(i)
   return send(self,200 if j else 404,j or {'error':'not_found'})
  if p.startswith('/archive_artifact/'):
   rel=unquote(p[len('/archive_artifact/'):]);parts=Path(rel).parts
   if not parts:return send(self,404,{'error':'not_found'})
   root=(INV/parts[0]).resolve();f=(INV/rel).resolve()
   if root.parent!=INV.resolve() or (root!=f and root not in f.parents) or not f.is_file():return send(self,404,{'error':'not_found'})
   c='model/vnd.usdz+zip' if f.suffix.lower()=='.usdz' else (mimetypes.guess_type(f.name)[0] or 'application/octet-stream');return send(self,200,f.read_bytes(),c)
  return send(self,404,{'error':'not_found'})
 def do_POST(self):
  p=urlparse(self.path).path
  try:
   n=int(self.headers.get('Content-Length','0'));raw_body=self.rfile.read(n);obj=json.loads(raw_body or b'{}')
   if p=='/api/archive-upload':
    files=obj.get('files') or []
    if not files:return send(self,400,{'error':'no_files'})
    jid='archive_'+uuid.uuid4().hex[:10];out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid);src=out/'source';src.mkdir(parents=True);stored=[];usdz_count=0;image_count=0
    for i,x in enumerate(files):
     name=safe_name(x.get('name') or f'file_{i}');b=base64.b64decode(x.get('data_base64') or '',validate=True);mime=str(x.get('mime') or '');is_usdz=name.lower().endswith('.usdz');is_image=mime.startswith('image/') or name.lower().endswith(('.png','.jpg','.jpeg','.webp','.heic','.gif'))
     if not (is_usdz or is_image):continue
     if is_usdz:
      if len(b)<4 or b[:2]!=b'PK':return send(self,400,{'error':'invalid_usdz_zip','file':name})
      target=out/('model.usdz' if usdz_count==0 else name);usdz_count+=1
     else:target=src/name;image_count+=1
     target.write_bytes(b);stored.append(str(target.relative_to(out)))
    if not stored:return send(self,400,{'error':'no_supported_files'})
    j={'id':jid,'status':'completed','stage':'archived','title':obj.get('title') or 'Archived files','description':obj.get('description') or '','output_dir':str(out),'created_at':time.time(),'archived_directly':True,'stored_files':stored,'usdz_count':usdz_count,'image_count':image_count};save_meta(j);j['artifacts']=artifacts_for(out,jid)
    with LOCK:JOBS[jid]=j
    return send(self,201,j)
   if p=='/api/jobs':
    jid=uuid.uuid4().hex[:12];out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid);src=out/'source';src.mkdir(parents=True);imgs=[]
    for k,x in enumerate(obj.get('images') or []):
     name=safe_name(x.get('name') or f'image_{k}.jpg');f=src/name;f.write_bytes(base64.b64decode(x.get('data_base64') or '',validate=True));imgs.append(str(f))
    j={'id':jid,'status':'queued','stage':'queued','title':obj.get('title') or 'Untitled invention','description':obj.get('description') or '','images':imgs,'output_dir':str(out),'created_at':time.time()};save_meta(j)
    with LOCK:JOBS[jid]=j
    threading.Thread(target=worker,args=(jid,),daemon=True).start();return send(self,201,j)
   return send(self,404,{'error':'not_found'})
  except Exception as e:return send(self,400,{'error':f'{type(e).__name__}:{e}'})

def main(host='0.0.0.0',port=8787):
 print(f'EIRA_INVENTOR_V5_SERVER http://{host}:{port}',flush=True);ThreadingHTTPServer((host,port),H).serve_forever()
if __name__=='__main__':
 import argparse;a=argparse.ArgumentParser();a.add_argument('--host',default='0.0.0.0');a.add_argument('--port',type=int,default=8787);x=a.parse_args();main(x.host,x.port)
'''

(EXT/'server.py').write_text(textwrap.dedent(SERVER).lstrip(),encoding='utf-8')
py_compile.compile(str(EXT/'server.py'),doraise=True)
manifest=EXT/'manifest.json'
if manifest.exists():
 obj=json.loads(manifest.read_text());obj['version']='5.6.0';obj['web_controls']={'build':True,'archive_upload':True,'archive_search':True};manifest.write_text(json.dumps(obj,indent=2)+'\n')
print('SERVER_CONTROLS_HARDENED_PASS')
print('VERSION: 5.6.0')
