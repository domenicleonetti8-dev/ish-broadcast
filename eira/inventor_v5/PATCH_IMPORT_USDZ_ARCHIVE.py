#!/usr/bin/env python3
from pathlib import Path
import json, py_compile, textwrap

ROOT=Path.cwd()
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'
SERVER=EXT/'server.py'
if not SERVER.is_file(): raise SystemExit('FAIL: server.py not found')

s=SERVER.read_text(encoding='utf-8')

# Inject UI controls before archive card if not already present.
if 'Import Existing USDZ' not in s:
    s=s.replace(
        '<div class="card"><b>Archive</b>',
        '<div class="card"><b>Import Existing USDZ</b><input id="import_usdz" type="file" accept=".usdz,model/vnd.usdz+zip,application/octet-stream"><input id="import_title" placeholder="Archive title (optional)"><textarea id="import_desc" rows="3" placeholder="Archive note / benchmark description (optional)"></textarea><button id="import_btn">Import USDZ to Archive</button><div id="import_status" class="muted"></div></div>\n<div class="card"><b>Archive</b>'
    )

    hook = r'''
$('import_btn').onclick=async()=>{try{let f=$('import_usdz').files[0];if(!f)throw Error('Choose a USDZ first');if(!f.name.toLowerCase().endsWith('.usdz'))throw Error('File must be .usdz');$('import_btn').disabled=true;$('import_status').textContent='importing...';let b64=await new Promise((res,rej)=>{let r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(f)});let j=await api('/api/import-usdz',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name,title:$('import_title').value||f.name.replace(/\.usdz$/i,''),description:$('import_desc').value||'',data_base64:b64})});$('import_status').textContent='Imported: '+j.title;$('import_status').className='good';$('import_btn').disabled=false;if(typeof loadArchive==='function')loadArchive()}catch(e){$('import_status').textContent=e.message;$('import_status').className='bad';$('import_btn').disabled=false}}
'''
    s=s.replace('</script></main></body></html>', hook+'\n</script></main></body></html>')

# Add POST endpoint before generic jobs POST handling.
needle=""" def do_POST(self):\n"""
if '/api/import-usdz' not in s:
    replacement=""" def do_POST(self):\n  p=urlparse(self.path).path\n  if p=='/api/import-usdz':\n   try:\n    n=int(self.headers.get('Content-Length','0')); obj=json.loads(self.rfile.read(n) or b'{}')\n    raw=base64.b64decode(obj.get('data_base64') or '',validate=True)\n    if len(raw)<4 or raw[:2]!=b'PK': return send(self,400,json_bytes({'error':'invalid_usdz_zip'}))\n    jid='import_'+uuid.uuid4().hex[:10]; title=obj.get('title') or obj.get('name') or 'Imported USDZ'; out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid); out.mkdir(parents=True)\n    name=safe_name(obj.get('name') or 'model.usdz')\n    if not name.lower().endswith('.usdz'): name += '.usdz'\n    target=out/name; target.write_bytes(raw)\n    meta={'id':jid,'status':'completed','stage':'imported','title':title,'description':obj.get('description') or '', 'output_dir':str(out),'created_at':time.time(),'imported':True,'benchmark':'V28 Completed Reference / Complexity Benchmark' if 'V28' in title or 'V28' in name else None,'usdz_url':f'/artifact/{jid}/{name}','glb_url':None,'source_images':[]}\n    (out/'archive_entry.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')\n    with LOCK:JOBS[jid]=meta\n    return send(self,201,json_bytes(meta))\n   except Exception as e:return send(self,400,json_bytes({'error':f'{type(e).__name__}:{e}'}))\n"""
    s=s.replace(needle,replacement,1)

SERVER.write_text(s,encoding='utf-8')
py_compile.compile(str(SERVER),doraise=True)

m=EXT/'manifest.json'
if m.exists():
    obj=json.loads(m.read_text())
    obj['version']='5.4.0'
    obj['archive_import']={'usdz':True,'persistent':True}
    m.write_text(json.dumps(obj,indent=2)+'\n')

print('IMPORT_USDZ_ARCHIVE_PATCH_PASS')
