#!/usr/bin/env python3
from pathlib import Path
import json, py_compile

ROOT=Path.cwd()
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'
SERVER=EXT/'server.py'
if not SERVER.is_file(): raise SystemExit('FAIL: server.py not found')
s=SERVER.read_text(encoding='utf-8')

# Add direct archive upload UI before Archive card.
marker='<div class="card"><h3>Archive</h3>'
if 'Direct Archive Upload' not in s and marker in s:
    ui='''<div class="card"><h3>Direct Archive Upload</h3><input id="arc_title" placeholder="Archive title"><textarea id="arc_desc" rows="3" placeholder="Description / notes"></textarea><input id="arc_files" type="file" accept="image/*,.usdz,model/vnd.usdz+zip" multiple><button id="arc_upload">Add Files to Archive</button><div id="arc_status" class="muted"></div></div>\n'''
    s=s.replace(marker,ui+marker,1)

# Add browser-side uploader before closing script.
if "$('arc_upload').onclick" not in s:
    js=r'''
$('arc_upload').onclick=async()=>{try{let fs=[...$('arc_files').files];if(!fs.length)throw Error('Choose at least one image or USDZ');$('arc_upload').disabled=true;$('arc_status').textContent='uploading...';let files=[];for(const f of fs){let b64=await new Promise((res,rej)=>{let r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(f)});files.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:b64})}let j=await api('/api/archive-upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('arc_title').value||'Archived files',description:$('arc_desc').value||'',files})});$('arc_status').textContent='Archived: '+j.title;$('arc_status').className='good';$('arc_upload').disabled=false;$('arc_files').value='';if(typeof loadArchive==='function')loadArchive()}catch(e){$('arc_status').textContent=e.message;$('arc_status').className='bad';$('arc_upload').disabled=false}}
'''
    s=s.replace('</script></main></body></html>',js+'\n</script></main></body></html>',1)

# Extend artifact scanner to include arbitrary archived files in source/ and root.
old=""" for fn,label in [('model.usdz','USDZ / Open in AR'),('model.glb','GLB'),('invention_spec.json','Invention Spec'),('inspection_report.json','Inspection Report')]:\n  if (out/fn).is_file(): d[label]=f'/archive_artifact/{out.name}/{fn}'\n src=out/'source'\n"""
new=""" for fn,label in [('model.usdz','USDZ / Open in AR'),('model.glb','GLB'),('invention_spec.json','Invention Spec'),('inspection_report.json','Inspection Report')]:\n  if (out/fn).is_file(): d[label]=f'/archive_artifact/{out.name}/{fn}'\n for f in sorted(out.iterdir()):\n  if f.is_file() and f.name not in {'archive.json','archive_entry.json','model.usdz','model.glb','invention_spec.json','inspection_report.json'}:\n   d['File: '+f.name]=f'/archive_artifact/{out.name}/{f.name}'\n src=out/'source'\n"""
if old in s:
    s=s.replace(old,new,1)

# Add POST endpoint before normal /api/jobs handler.
needle=""" def do_POST(self):\n"""
if "p=='/api/archive-upload'" not in s and needle in s:
    block=""" def do_POST(self):\n  p=urlparse(self.path).path\n  if p=='/api/archive-upload':\n   try:\n    n=int(self.headers.get('Content-Length','0')); obj=json.loads(self.rfile.read(n) or b'{}')\n    files=obj.get('files') or []\n    if not files: return send(self,400,{'error':'no_files'})\n    jid='archive_'+uuid.uuid4().hex[:10]; out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid); src=out/'source'; src.mkdir(parents=True)\n    stored=[]; usdz_count=0; image_count=0\n    for i,x in enumerate(files):\n     name=safe_name(x.get('name') or f'file_{i}'); raw=base64.b64decode(x.get('data_base64') or '',validate=True); mime=str(x.get('mime') or '')\n     is_usdz=name.lower().endswith('.usdz')\n     is_image=mime.startswith('image/') or name.lower().endswith(('.png','.jpg','.jpeg','.webp','.heic','.gif'))\n     if not (is_usdz or is_image): continue\n     if is_usdz:\n      if len(raw)<4 or raw[:2]!=b'PK': return send(self,400,{'error':'invalid_usdz_zip','file':name})\n      target=out/('model.usdz' if usdz_count==0 else name); usdz_count+=1\n     else:\n      target=src/name; image_count+=1\n     target.write_bytes(raw); stored.append(str(target.relative_to(out)))\n    if not stored: return send(self,400,{'error':'no_supported_files'})\n    j={'id':jid,'status':'completed','stage':'archived','title':obj.get('title') or 'Archived files','description':obj.get('description') or '', 'output_dir':str(out),'created_at':time.time(),'archived_directly':True,'stored_files':stored,'usdz_count':usdz_count,'image_count':image_count}\n    save_meta(j); j['artifacts']=artifacts_for(out,jid)\n    with LOCK:JOBS[jid]=j\n    return send(self,201,j)\n   except Exception as e:return send(self,400,{'error':f'{type(e).__name__}:{e}'})\n"""
    s=s.replace(needle,block,1)

SERVER.write_text(s,encoding='utf-8')
py_compile.compile(str(SERVER),doraise=True)

m=EXT/'manifest.json'
if m.exists():
    obj=json.loads(m.read_text())
    obj['version']='5.5.0'
    obj['archive_direct_upload']={'images':True,'usdz':True,'pipeline_required':False}
    m.write_text(json.dumps(obj,indent=2)+'\n')

print('ARCHIVE_DIRECT_UPLOAD_PATCH_PASS')
print('Supports: images + USDZ -> persistent archive, no build pipeline')
