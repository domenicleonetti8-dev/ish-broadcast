#!/usr/bin/env python3
from pathlib import Path
import json, py_compile, re, shutil

ROOT=Path.cwd()
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'
SERVER=EXT/'server.py'
INV=EXT/'inventions'
if not SERVER.is_file(): raise SystemExit('FAIL: server.py missing')

# Remove only failed Untitled invention archive entries.
removed=[]
if INV.is_dir():
    for d in INV.iterdir():
        if not d.is_dir():
            continue
        m=d/'archive.json'
        try:
            obj=json.loads(m.read_text()) if m.is_file() else {}
        except Exception:
            obj={}
        title=str(obj.get('title') or '')
        status=str(obj.get('status') or '')
        if title=='Untitled invention' and status=='failed':
            shutil.rmtree(d)
            removed.append(d.name)

s=SERVER.read_text(encoding='utf-8')

# Replace the direct archive card with a plain multipart form that works without JS.
card_pat=re.compile(r'<div class="card"><h3>Direct Archive Upload</h3>.*?</div>\s*<div class="card"><h3>Archive</h3>',re.S)
replacement='''<div class="card"><h3>Direct Archive Upload</h3><form method="POST" action="/archive-upload-form" enctype="multipart/form-data"><input name="title" placeholder="Archive title"><textarea name="description" rows="3" placeholder="Description / notes"></textarea><input name="files" type="file" accept="image/*,.usdz,model/vnd.usdz+zip,application/octet-stream" multiple><button type="submit">Add Files to Archive</button></form><div id="arc_status" class="muted">Server-side upload fallback active.</div></div>\n<div class="card"><h3>Archive</h3>'''
if not card_pat.search(s):
    raise SystemExit('FAIL: direct archive card marker not found')
s=card_pat.sub(replacement,s,count=1)

# Replace Archive controls with a plain GET form; archive list remains where existing JS can fill it, but search works server-side too.
s=s.replace('<input id="search" placeholder="Search title, description, date, job id"><button type="button" id="searchBtn">Search Archive</button>',
            '<form method="GET" action="/"><input name="q" id="search" placeholder="Search title, description, date, job id"><button type="submit" id="searchBtn">Search Archive</button></form>',1)

# Add helper imports if absent.
if 'from email.parser import BytesParser' not in s:
    s=s.replace('from pathlib import Path\n','from pathlib import Path\nfrom email.parser import BytesParser\nfrom email.policy import default as email_default_policy\n',1)

# Add server-side root rendering helper.
helper='''\ndef render_root_html(query=''):\n html=HTML\n items=scan_archive(query)\n rows=[]\n for x in items:\n  links=' '.join(f'<a href="{v}">{k}</a>' for k,v in (x.get('artifacts') or {}).items())\n  rows.append(f'<div class="item"><b>{x.get("title","")}</b><div class="muted">{x.get("created","")} - {x.get("status","")}</div><div>{x.get("description","")}</div><div class="links">{links}</div></div>')\n listing=''.join(rows) if rows else 'No matching inventions found.'\n html=html.replace('Loading archive...',listing,1)\n return html\n\ndef parse_multipart_form(headers, body):\n ctype=headers.get('Content-Type','')\n if 'multipart/form-data' not in ctype:\n  raise ValueError('expected_multipart_form')\n msg=BytesParser(policy=email_default_policy).parsebytes((f'Content-Type: {ctype}\\r\\nMIME-Version: 1.0\\r\\n\\r\\n').encode()+body)\n title=''; description=''; files=[]\n for part in msg.iter_parts():\n  disp=part.get('Content-Disposition','')\n  if 'form-data' not in disp: continue\n  name=part.get_param('name',header='Content-Disposition')\n  filename=part.get_filename()\n  payload=part.get_payload(decode=True) or b''\n  if filename:\n   files.append((filename,part.get_content_type(),payload))\n  elif name=='title': title=payload.decode('utf-8','replace')\n  elif name=='description': description=payload.decode('utf-8','replace')\n return title.strip(), description.strip(), files\n'''
if 'def render_root_html(' not in s:
    s=s.replace('\nclass H(BaseHTTPRequestHandler):',helper+'\nclass H(BaseHTTPRequestHandler):',1)

# Root GET now supports server-side search via ?q=
s=s.replace("if p=='/':return send(self,200,HTML,'text/html; charset=utf-8')",
            "if p=='/': return send(self,200,render_root_html(parse_qs(u.query).get('q',[''])[0]),'text/html; charset=utf-8')",1)

# Insert multipart POST handler before existing JSON body parsing.
needle="  p=urlparse(self.path).path\n"
insert="""  p=urlparse(self.path).path\n  if p=='/archive-upload-form':\n   try:\n    n=int(self.headers.get('Content-Length','0')); body=self.rfile.read(n)\n    title,description,files=parse_multipart_form(self.headers,body)\n    if not files:\n     return send(self,400,'No files selected','text/plain; charset=utf-8')\n    jid='archive_'+uuid.uuid4().hex[:10]; out=INV/(time.strftime('%Y%m%d_%H%M%S')+'_'+jid); src=out/'source'; src.mkdir(parents=True)\n    stored=[]; usdz_count=0; image_count=0\n    for filename,mime,raw in files:\n     name=safe_name(filename); lower=name.lower(); is_usdz=lower.endswith('.usdz'); is_image=mime.startswith('image/') or lower.endswith(('.png','.jpg','.jpeg','.webp','.heic','.gif'))\n     if not (is_usdz or is_image): continue\n     if is_usdz:\n      if len(raw)<4 or raw[:2]!=b'PK': continue\n      target=out/('model.usdz' if usdz_count==0 else name); usdz_count+=1\n     else:\n      target=src/name; image_count+=1\n     target.write_bytes(raw); stored.append(str(target.relative_to(out)))\n    if not stored:\n     return send(self,400,'No supported files were uploaded','text/plain; charset=utf-8')\n    j={'id':jid,'status':'completed','stage':'archived','title':title or 'Archived files','description':description,'output_dir':str(out),'created_at':time.time(),'archived_directly':True,'stored_files':stored,'usdz_count':usdz_count,'image_count':image_count}\n    save_meta(j)\n    self.send_response(303); self.send_header('Location','/'); self.end_headers(); return\n   except Exception as e:\n    return send(self,400,f'Archive upload failed: {type(e).__name__}:{e}','text/plain; charset=utf-8')\n"""
idx=s.find(' def do_POST(self):')
if idx<0: raise SystemExit('FAIL: do_POST missing')
sub=s[idx:]
pos=sub.find(needle)
if pos<0: raise SystemExit('FAIL: do_POST path line missing')
abspos=idx+pos
s=s[:abspos]+insert+s[abspos+len(needle):]

SERVER.write_text(s,encoding='utf-8')
py_compile.compile(str(SERVER),doraise=True)
print('ARCHIVE_NO_JS_FALLBACK_PASS')
print('REMOVED_FAILED_UNTITLED:',len(removed))
for x in removed: print('REMOVED:',x)
print('server.py syntax: PASS')
