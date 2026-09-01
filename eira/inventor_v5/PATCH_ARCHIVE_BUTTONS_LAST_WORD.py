#!/usr/bin/env python3
from pathlib import Path
import py_compile

ROOT=Path.cwd()
SERVER=ROOT/'extensions'/'eira_inventor_holographic_lab'/'server.py'
if not SERVER.is_file(): raise SystemExit('FAIL: server.py not found')
s=SERVER.read_text(encoding='utf-8')

# Make every visible control explicitly non-submit.
s=s.replace('<button id="arc_upload"', '<button type="button" id="arc_upload"') if '<button id="arc_upload"' in s and '<button type="button" id="arc_upload"' not in s else s
s=s.replace('<button id="searchBtn"', '<button type="button" id="searchBtn"') if '<button id="searchBtn"' in s and '<button type="button" id="searchBtn"' not in s else s
s=s.replace('<button id="go"', '<button type="button" id="go"') if '<button id="go"' in s and '<button type="button" id="go"' not in s else s

marker='EIRA_ARCHIVE_CONTROLS_LAST_WORD'
if marker not in s:
    js='''\n<script id="EIRA_ARCHIVE_CONTROLS_LAST_WORD">\n(function(){\n  function byId(x){return document.getElementById(x);}\n  function msg(el,text,kind){if(!el)return;el.textContent=text;el.className=kind||'muted';}\n  async function readB64(f){return await new Promise(function(resolve,reject){var r=new FileReader();r.onload=function(){resolve(String(r.result).split(',')[1]||'');};r.onerror=function(){reject(new Error('Could not read '+f.name));};r.readAsDataURL(f);});}\n  async function jsonFetch(url,opt){var r=await fetch(url,opt);var t=await r.text();var d={};try{d=t?JSON.parse(t):{};}catch(e){throw new Error('Server returned invalid response: '+t.slice(0,160));}if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d;}\n  function links(a){var out='';Object.entries(a||{}).forEach(function(kv){out+='<a href="'+kv[1]+'" style="margin-right:12px">'+kv[0]+'</a>';});return out;}\n  async function reloadArchive(){var box=byId('archive');try{var q=encodeURIComponent((byId('search')&&byId('search').value)||'');var d=await jsonFetch('/api/archive?q='+q);if(!d.items||!d.items.length){box.innerHTML='No matching inventions found.';return;}box.innerHTML=d.items.map(function(x){return '<div class="item"><b>'+String(x.title||x.id)+'</b><div class="muted">'+String(x.created||'')+' - '+String(x.status||'')+'</div><div>'+String(x.description||'')+'</div><div class="links">'+links(x.artifacts)+'</div></div>';}).join('');}catch(e){msg(box,'Archive search failed: '+e.message,'bad');}}\n  function bind(){\n    document.querySelectorAll('form').forEach(function(f){f.addEventListener('submit',function(e){e.preventDefault();e.stopPropagation();},true);});\n    var sb=byId('searchBtn');if(sb){sb.type='button';sb.onclick=function(e){e.preventDefault();e.stopPropagation();reloadArchive();return false;};}\n    var sf=byId('search');if(sf){sf.onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();e.stopPropagation();reloadArchive();return false;}};}\n    var ab=byId('arc_upload');if(ab){ab.type='button';ab.onclick=async function(e){e.preventDefault();e.stopPropagation();var st=byId('arc_status');try{var inp=byId('arc_files');var fs=inp?Array.from(inp.files||[]):[];if(!fs.length)throw new Error('Choose at least one image or USDZ');ab.disabled=true;msg(st,'Reading '+fs.length+' file(s)...','muted');var files=[];for(var i=0;i<fs.length;i++){files.push({name:fs[i].name,mime:fs[i].type||'application/octet-stream',data_base64:await readB64(fs[i])});}msg(st,'Uploading to archive...','muted');var payload={title:((byId('arc_title')&&byId('arc_title').value)||'Archived files').trim(),description:((byId('arc_desc')&&byId('arc_desc').value)||'').trim(),files:files};var d=await jsonFetch('/api/archive-upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});msg(st,'Archived successfully: '+String(d.title||payload.title),'good');if(inp)inp.value='';await reloadArchive();}catch(err){msg(st,'Archive upload failed: '+err.message,'bad');}finally{ab.disabled=false;}return false;};}\n    window.eiraReloadArchive=reloadArchive;\n  }\n  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',bind,{once:true});}else{bind();}\n})();\n</script>\n'''
    if '</body>' not in s: raise SystemExit('FAIL: body close not found')
    s=s.replace('</body>',js+'</body>',1)

SERVER.write_text(s,encoding='utf-8')
py_compile.compile(str(SERVER),doraise=True)
print('ARCHIVE_BUTTONS_LAST_WORD_PASS')
print('server.py syntax: PASS')
print('controls: archive-upload + archive-search rebound independently')
