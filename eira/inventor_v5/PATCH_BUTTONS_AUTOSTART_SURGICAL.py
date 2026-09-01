#!/usr/bin/env python3
from pathlib import Path
import json, py_compile, re

ROOT = Path.cwd()
EXT = ROOT / "extensions" / "eira_inventor_holographic_lab"
SERVER = EXT / "server.py"
SITE = ROOT / "sitecustomize.py"

if not SERVER.is_file():
    raise SystemExit("FAIL: server.py not found")

s = SERVER.read_text(encoding="utf-8")

js = r'''
async function eiraFileToB64(f){
  return await new Promise((res,rej)=>{
    const r=new FileReader();
    r.onload=()=>res(String(r.result).split(',')[1]||'');
    r.onerror=()=>rej(r.error||new Error('file_read_failed'));
    r.readAsDataURL(f);
  });
}
const arcBtn=document.getElementById('arc_upload');
if(arcBtn){
  arcBtn.onclick=async()=>{
    const st=document.getElementById('arc_status');
    try{
      const fs=[...(document.getElementById('arc_files').files||[])];
      if(!fs.length) throw new Error('Choose at least one image or USDZ');
      arcBtn.disabled=true;
      st.className='muted';
      st.textContent='Uploading...';
      const files=[];
      for(const f of fs){
        files.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:await eiraFileToB64(f)});
      }
      const payload={
        title:(document.getElementById('arc_title').value||'Archived files').trim(),
        description:(document.getElementById('arc_desc').value||'').trim(),
        files
      };
      const r=await fetch('/api/archive-upload',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(payload)
      });
      const text=await r.text();
      let data={};
      try{data=text?JSON.parse(text):{};}catch(_){throw new Error(text||('HTTP '+r.status));}
      if(!r.ok) throw new Error(data.error||('HTTP '+r.status));
      st.className='good';
      st.textContent='Archived: '+(data.title||payload.title);
      document.getElementById('arc_files').value='';
      if(typeof loadArchive==='function') await loadArchive();
    }catch(e){
      st.className='bad';
      st.textContent=String(e && e.message ? e.message : e);
    }finally{
      arcBtn.disabled=false;
    }
  };
}
'''

s = re.sub(r"\n?\$\('arc_upload'\)\.onclick=async\(\)=>\{.*?\}\s*\n", "\n", s, flags=re.S)
if "async function eiraFileToB64" not in s:
    if "</script>" not in s:
        raise SystemExit("FAIL: script tag not found")
    s = s.replace("</script>", js + "\n</script>", 1)

m = re.search(r"(?ms)^ def do_POST\(self\):\n(?P<body>.*?)(?=^\ndef main\()", s)
if not m:
    raise SystemExit("FAIL: do_POST block not found")

old_body = m.group("body")
guard = re.search(r"(?ms)^  if (?:urlparse\(self\.path\)\.path|p)!='/api/jobs':.*?\n(?P<logic>  try:.*)$", old_body)
if not guard:
    raise SystemExit("FAIL: could not preserve /api/jobs implementation")
job_logic = guard.group("logic")

new_post = r''' def do_POST(self):
  p=urlparse(self.path).path
  if p=='/api/archive-upload':
   try:
    n=int(self.headers.get('Content-Length','0'))
    obj=json.loads(self.rfile.read(n) or b'{}')
    files=obj.get('files') or []
    if not files:
     return send(self,400,{'error':'no_files'})
    jid='archive_'+uuid.uuid4().hex[:10]
    out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid)
    src=out/'source'
    src.mkdir(parents=True)
    stored=[]
    usdz_count=0
    image_count=0
    for i,x in enumerate(files):
     name=safe_name(x.get('name') or f'file_{i}')
     raw=base64.b64decode(x.get('data_base64') or '',validate=True)
     mime=str(x.get('mime') or '')
     lower=name.lower()
     is_usdz=lower.endswith('.usdz')
     is_image=mime.startswith('image/') or lower.endswith(('.png','.jpg','.jpeg','.webp','.heic','.gif'))
     if not (is_usdz or is_image):
      continue
     if is_usdz:
      if len(raw)<4 or raw[:2]!=b'PK':
       return send(self,400,{'error':'invalid_usdz_zip','file':name})
      target=out/('model.usdz' if usdz_count==0 else name)
      usdz_count+=1
     else:
      target=src/name
      image_count+=1
     target.write_bytes(raw)
     stored.append(str(target.relative_to(out)))
    if not stored:
     return send(self,400,{'error':'no_supported_files'})
    j={
      'id':jid,'status':'completed','stage':'archived',
      'title':obj.get('title') or 'Archived files',
      'description':obj.get('description') or '',
      'output_dir':str(out),'created_at':time.time(),
      'archived_directly':True,'stored_files':stored,
      'usdz_count':usdz_count,'image_count':image_count
    }
    save_meta(j)
    j['artifacts']=artifacts_for(out,jid)
    with LOCK:
     JOBS[jid]=j
    return send(self,201,j)
   except Exception as e:
    return send(self,400,{'error':f'{type(e).__name__}:{e}'})
  if p!='/api/jobs':
   return send(self,404,{'error':'not_found'})
''' + job_logic + "\n"

s = s[:m.start()] + new_post + s[m.end():]
SERVER.write_text(s, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)

site = SITE.read_text(encoding="utf-8") if SITE.exists() else ""
start = "# EIRA_INVENTOR_V5_AUTOSTART"
if start in site:
    site = site.split(start,1)[0].rstrip() + "\n"

hook = r'''# EIRA_INVENTOR_V5_AUTOSTART
import os,sys,subprocess,time,urllib.request
try:
    if os.path.basename(sys.argv[0])=='main.py':
        good=False
        try:
            with urllib.request.urlopen('http://127.0.0.1:8787/api/health',timeout=.35) as r:
                body=r.read().decode('utf-8','replace')
            good=('"ok": true' in body or '"ok":true' in body) and ('archive' in body or 'version' in body)
        except Exception:
            good=False
        if not good:
            try:
                p=subprocess.run(
                    "ss -ltnp | sed -n 's/.*:8787.*pid=\\([0-9]*\\).*/\\1/p' | head -1",
                    shell=True,text=True,capture_output=True,timeout=1
                )
                pid=(p.stdout or '').strip()
                if pid.isdigit():
                    os.kill(int(pid),15)
                    time.sleep(.5)
            except Exception:
                pass
            log=open('/tmp/eira_inventor_v5_server.log','ab',buffering=0)
            subprocess.Popen(
                [sys.executable,'-m','extensions.eira_inventor_holographic_lab.server','--host','0.0.0.0','--port','8787'],
                cwd=os.getcwd(),stdout=log,stderr=log,start_new_session=True
            )
except Exception:
    pass
'''
SITE.write_text(site + hook, encoding="utf-8")
py_compile.compile(str(SITE), doraise=True)

print("BUTTONS_AND_AUTOSTART_HARDENED_PASS")
print("server.py syntax: PASS")
print("sitecustomize.py syntax: PASS")
