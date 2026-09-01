#!/usr/bin/env python3
from pathlib import Path
import py_compile,re

ROOT=Path.cwd()
EXT=ROOT/'extensions'/'eira_inventor_holographic_lab'
SERVER=EXT/'server.py'
JS=EXT/'archive_controls.js'
if not SERVER.is_file(): raise SystemExit('FAIL: server.py not found')

js=r'''(function(){
'use strict';
function id(x){return document.getElementById(x)}
function msg(el,text,cls){if(!el)return;el.textContent=text;el.className=cls||'muted'}
async function asJson(url,opt){
  const r=await fetch(url,opt);const t=await r.text();let d={};
  try{d=t?JSON.parse(t):{}}catch(_){throw new Error('Non-JSON response: '+t.slice(0,200))}
  if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d;
}
function readB64(f){return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]||'');r.onerror=()=>rej(new Error('Could not read '+f.name));r.readAsDataURL(f)})}
function links(a){return Object.entries(a||{}).map(([k,v])=>'<a href="'+v+'">'+k+'</a>').join(' ')}
async function reloadArchive(){
  const box=id('archive');
  try{
    const q=encodeURIComponent((id('search')&&id('search').value)||'');
    const d=await asJson('/api/archive?q='+q);
    if(!box)return;
    box.className='muted';
    box.innerHTML=d.items&&d.items.length?d.items.map(x=>'<div class="item"><b>'+x.title+'</b><div class="muted">'+x.created+' - '+x.status+'</div><div>'+(x.description||'')+'</div><div class="links">'+links(x.artifacts)+'</div></div>').join(''):'No matching inventions found.';
  }catch(e){msg(box,'Archive search failed: '+e.message,'bad')}
}
async function uploadArchive(ev){
  if(ev){ev.preventDefault();ev.stopPropagation()}
  const btn=id('arc_upload'),st=id('arc_status'),inp=id('arc_files');
  try{
    const fs=inp?Array.from(inp.files||[]):[];
    if(!fs.length)throw new Error('Choose at least one image or USDZ');
    btn.disabled=true;msg(st,'Reading '+fs.length+' file(s)...','muted');
    const files=[];
    for(const f of fs)files.push({name:f.name,mime:f.type||'application/octet-stream',data_base64:await readB64(f)});
    msg(st,'Uploading to archive...','muted');
    const payload={title:((id('arc_title')&&id('arc_title').value)||'Archived files').trim(),description:((id('arc_desc')&&id('arc_desc').value)||'').trim(),files};
    const d=await asJson('/api/archive-upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    msg(st,'Archived successfully: '+(d.title||payload.title),'good');if(inp)inp.value='';await reloadArchive();
  }catch(e){msg(st,'Archive upload failed: '+e.message,'bad')}
  finally{if(btn)btn.disabled=false}
  return false;
}
function bind(){
  const sb=id('searchBtn');if(sb){sb.type='button';sb.onclick=function(e){e.preventDefault();e.stopPropagation();reloadArchive();return false}}
  const sf=id('search');if(sf){sf.onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();e.stopPropagation();reloadArchive();return false}}}
  const ab=id('arc_upload');if(ab){ab.type='button';ab.onclick=uploadArchive}
  window.eiraReloadArchive=reloadArchive;
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind,{once:true});else bind();
})();
'''
JS.write_text(js,encoding='utf-8')

s=SERVER.read_text(encoding='utf-8')
# Add external script tag using the exact live HTML terminator.
tag='<script src="/archive-controls.js?v=final1"></script>'
if tag not in s:
    marker="</body></html>'''"
    if marker not in s: raise SystemExit('FAIL: exact live html marker not found')
    s=s.replace(marker,tag+'\n'+marker,1)

# Serve the independent JS file from do_GET.
if "p=='/archive-controls.js'" not in s:
    pat=r"(def do_GET\(self\):\n\s+u=urlparse\(self\.path\);p=u\.path\n)"
    m=re.search(pat,s)
    if not m: raise SystemExit('FAIL: live do_GET header not found')
    ins="  if p=='/archive-controls.js':\n   return send(self,200,(ROOT/'archive_controls.js').read_bytes(),'application/javascript; charset=utf-8')\n"
    s=s[:m.end()]+ins+s[m.end():]

SERVER.write_text(s,encoding='utf-8')
py_compile.compile(str(SERVER),doraise=True)
print('ARCHIVE_EXTERNAL_JS_FINAL_PASS')
print('server.py syntax: PASS')
print('archive_controls.js: PASS')
