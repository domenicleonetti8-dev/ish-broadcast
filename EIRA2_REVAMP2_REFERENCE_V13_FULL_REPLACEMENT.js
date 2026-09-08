'use strict';

const $ = s => document.querySelector(s);
const log = $('#log');
const canvas = $('#brain');
const ctx = canvas.getContext('2d');

let state = {active:false, muted:false};
let mic = null, audioCtx = null, analyser = null, vadRAF = 0;
let pcmNode = null, pcmFrames = [], voiceBusy = false, speechFrames = 0, silenceSince = 0, recordStarted = 0, cooldownUntil = 0;
let neural = {nodes:[], fibers:[], activity:[]};
let topology = {graph:new Map(), cores:[], activity:new Map(), pathEdges:new Set(), pathNodes:new Map(), canonical:new Set(), routes:[]};
let screenNodes = [], selectedId = null, drag = null;
let rot = {x:-0.08, y:0.18};
let autoAngle = 0;

const CORE_VALUES = new Set(['core','kernel','supervisor','spine','registry','orchestrator','brain_core','neural_core','system_core']);
const CORE_ID_RE = /(?:^|[._:\/-])(core|kernel|supervisor|spine)(?:$|[._:\/-])/i;
const esc = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function add(w,t,k='eira'){
  const p=document.createElement('p');
  p.className='msg '+k;
  p.innerHTML=`<span class="who">${esc(w)}</span>${esc(t)}`;
  log.appendChild(p); log.scrollTop=log.scrollHeight;
}

async function req(u,o={}){
  const r=await fetch(u,{cache:'no-store',...o}); let j={};
  try{j=await r.json()}catch{}
  if(!r.ok) throw Error(j.error||`${r.status} ${r.statusText}`);
  return j;
}

function updateState(){
  const label=!state.active?'INACTIVE':state.muted?'MUTED':voiceBusy?'TRANSCRIBING':'LISTENING';
  $('#activePill').textContent=label;
  $('#activateBtn').textContent=state.active?'DEACTIVATE EIRA':'ACTIVATE EIRA';
  $('#muteBtn').textContent=state.muted?'UNMUTE':'MUTE';
  document.body.classList.toggle('listening',state.active&&!state.muted);
  document.body.classList.toggle('muted',state.muted);
}

function renderBridges(b){
  const box=$('#runtime'); box.innerHTML='';
  Object.entries(b||{}).forEach(([k,v])=>{
    const d=document.createElement('div'); d.className='r '+(v.healthy?'ok':'bad');
    d.innerHTML=`<b>${v.healthy?'●':'○'} ${esc(k.replaceAll('_',' ').toUpperCase())}</b><span>${esc(v.detail||'')}</span>`;
    box.appendChild(d);
  });
}

async function health(){
  try{
    const r=await fetch('/health',{cache:'no-store'}),j=await r.json();
    state=j.runtime||state; updateState(); renderBridges(j.bridges);
    $('#statusDot').classList.toggle('ok',!!j.ok);
    $('#headline').textContent=j.ok?`SERVER QUALIFIED · :${j.port||8782}`:'SERVER PARTIALLY READY';
  }catch{$('#headline').textContent='SERVER UNREACHABLE'}
}

async function submitText(text,source='text'){
  const clean=String(text||'').trim(); if(!clean)return null;
  add(source==='voice'?'You · voice':'You',clean,'me');
  const j=await req('/v1/text',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:clean,source})});
  const r=j.result||j, answer=r.text||r.reply||r.response||JSON.stringify(r);
  add('Eira',answer); return r;
}

async function acquireMic(){
  if(mic&&mic.active)return mic;
  if(!window.isSecureContext)throw Error('Microphone requires HTTPS on iPhone Safari');
  mic=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
  audioCtx=new (window.AudioContext||window.webkitAudioContext)(); await audioCtx.resume();
  const src=audioCtx.createMediaStreamSource(mic); analyser=audioCtx.createAnalyser(); analyser.fftSize=1024; analyser.smoothingTimeConstant=.32; src.connect(analyser);
  return mic;
}
function applyMute(){if(mic)mic.getAudioTracks().forEach(t=>t.enabled=!state.muted)}

function packPCM16(frames,inputRate){
  let total=frames.reduce((n,a)=>n+a.length,0),src=new Float32Array(total),o=0;
  for(const a of frames){src.set(a,o);o+=a.length}
  const ratio=inputRate/16000,outLen=Math.max(1,Math.floor(src.length/ratio)),buf=new ArrayBuffer(outLen*2),dv=new DataView(buf);
  for(let i=0;i<outLen;i++){
    const start=Math.floor(i*ratio),end=Math.max(start+1,Math.floor((i+1)*ratio)); let sum=0,n=0;
    for(let j=start;j<end&&j<src.length;j++){sum+=src[j];n++}
    const s=Math.max(-1,Math.min(1,n?sum/n:0)); dv.setInt16(i*2,s<0?s*32768:s*32767,true);
  }
  return buf;
}

function beginUtterance(){
  if(!mic||voiceBusy||state.muted||pcmNode)return;
  pcmFrames=[]; const src=audioCtx.createMediaStreamSource(mic); pcmNode=audioCtx.createScriptProcessor(4096,1,1);
  pcmNode.onaudioprocess=e=>pcmFrames.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  src.connect(pcmNode); pcmNode.connect(audioCtx.destination); recordStarted=performance.now(); silenceSince=0; document.body.classList.add('hearing');
}

async function finishUtterance(){
  if(!pcmNode)return; const node=pcmNode; pcmNode=null; try{node.disconnect()}catch{}
  document.body.classList.remove('hearing'); const frames=pcmFrames; pcmFrames=[]; if(!frames.length)return;
  voiceBusy=true; document.body.classList.add('transcribing'); updateState();
  try{
    const body=packPCM16(frames,audioCtx.sampleRate);
    const j=await req('/v1/listen?sample_rate=16000&channels=1&sample_width=2',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body});
    const transcript=String(j.utterance||j.text||'').trim(), r=j.result||j, answer=r.text||r.reply||r.response;
    if(transcript)add('You · voice',transcript,'me'); if(answer)add('Eira',answer);
  }catch(e){add('Voice path',e.message,'err')}
  finally{voiceBusy=false;document.body.classList.remove('transcribing');cooldownUntil=performance.now()+850;updateState()}
}

function vadLoop(){
  if(!state.active||!analyser){vadRAF=0;return}
  const a=new Uint8Array(analyser.fftSize); analyser.getByteTimeDomainData(a); let sum=0;
  for(const v of a){const x=(v-128)/128;sum+=x*x}
  const rms=Math.sqrt(sum/a.length),now=performance.now(),speaking=rms>.028;
  if(state.muted||voiceBusy||now<cooldownUntil){speechFrames=0}
  else if(pcmNode){if(speaking)silenceSince=0;else if(!silenceSince)silenceSince=now;if((silenceSince&&now-silenceSince>900&&now-recordStarted>350)||now-recordStarted>12000)finishUtterance()}
  else{speechFrames=speaking?speechFrames+1:0;if(speechFrames>=3){speechFrames=0;beginUtterance()}}
  vadRAF=requestAnimationFrame(vadLoop);
}
function startVAD(){cancelAnimationFrame(vadRAF);vadRAF=requestAnimationFrame(vadLoop)}
async function stopMic(){cancelAnimationFrame(vadRAF);vadRAF=0;if(pcmNode)await finishUtterance();if(mic){mic.getTracks().forEach(t=>t.stop());mic=null}if(audioCtx){await audioCtx.close().catch(()=>{});audioCtx=null}analyser=null;document.body.classList.remove('hearing','transcribing')}

$('#activateBtn').onclick=async()=>{try{if(!state.active){await acquireMic();state.active=true;state.muted=false;applyMute();updateState();startVAD()}else{await stopMic();state.active=false;state.muted=false;updateState()}}catch(e){add('Activation error',e.message,'err')}};
$('#muteBtn').onclick=()=>{try{if(!state.active)throw Error('Activate Eira first');state.muted=!state.muted;applyMute();updateState()}catch(e){add('Mute error',e.message,'err')}};
$('#form').onsubmit=async e=>{e.preventDefault();const i=$('#input'),text=i.value.trim();if(!text)return;i.value='';try{await submitText(text,'text')}catch(x){add('Conversation bridge',x.message,'err')}};
$('#inventBtn').onclick=()=>{location.href='/inventions/'};

// Real Apple Quick Look launcher. A rel=ar anchor with an image child is kept in the DOM;
// the visible APPLE AR control delegates directly to it under the user's click gesture.
const quickLook=document.createElement('a');
quickLook.id='eiraQuickLookAR';
quickLook.rel='ar';
quickLook.href='/inventions/usdz/eira2_brain.usdz';
quickLook.setAttribute('aria-label','Place EIRA V13 neural organism in Apple AR');
quickLook.style.position='fixed';quickLook.style.width='1px';quickLook.style.height='1px';quickLook.style.opacity='0.001';quickLook.style.pointerEvents='none';quickLook.style.overflow='hidden';
const quickLookImg=document.createElement('img');quickLookImg.alt='EIRA V13 AR';
quickLookImg.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';
quickLook.appendChild(quickLookImg);document.body.appendChild(quickLook);
$('#arBtn').onclick=()=>{quickLook.click()};

function dataOf(x){return x&&x.data!==undefined?x.data:x}
function explicitId(n){for(const k of ['id','node_id','name','path'])if(n?.[k]!=null&&String(n[k]).trim())return String(n[k]).trim();return null}
function id(n,i){return explicitId(n)||`n${i}`}
function ends(f){const a=f?.source??f?.from??f?.a??f?.source_id,b=f?.target??f?.to??f?.b??f?.target_id;return[a==null?null:String(a).trim(),b==null?null:String(b).trim()]}
function score(a){for(const k of ['activity','score','strength','level','weight','value']){const v=Number(a?.[k]);if(Number.isFinite(v))return Math.max(0,Math.min(1,v))}return 1}
function explicitCore(n){const nid=explicitId(n)||'';if(CORE_ID_RE.test(nid))return true;for(const k of ['role','type','kind','class','category','authority']){const v=n?.[k];if(typeof v==='string'&&CORE_VALUES.has(v.trim().toLowerCase()))return true;if(Array.isArray(v)&&v.some(x=>CORE_VALUES.has(String(x).trim().toLowerCase())))return true}return false}
function activityTargets(a){const out=[],push=v=>{if(typeof v==='string'&&v.trim())out.push(v.trim());else if(v&&typeof v==='object'){const x=explicitId(v);if(x)out.push(x)}};const direct=explicitId(a);if(direct)out.push(direct);for(const k of ['target','target_id','node','node_id'])push(a?.[k]);for(const k of ['targets','node_ids','participants','contributors','active_nodes'])if(Array.isArray(a?.[k]))a[k].forEach(push);return[...new Set(out)]}
function pathTo(target,g,starts){const q=[...starts],prev=new Map(),seen=new Set(starts);while(q.length){let cur=q.shift();if(cur===target){const p=[cur];while(prev.has(cur)){cur=prev.get(cur);p.push(cur)}return p.reverse()}for(const nx of g.get(cur)||[])if(!seen.has(nx)){seen.add(nx);prev.set(nx,cur);q.push(nx)}}return[]}

function rebuild(){
  const canonical=new Set(neural.nodes.map((n,i)=>id(n,i))),g=new Map(); canonical.forEach(n=>g.set(n,[]));
  for(const f of neural.fibers){const[a,b]=ends(f);if(a&&b&&canonical.has(a)&&canonical.has(b)){g.get(a).push(b);g.get(b).push(a)}}
  const cores=[];neural.nodes.forEach((n,i)=>{if(explicitCore(n))cores.push(id(n,i))});
  const activity=new Map(),pathEdges=new Set(),pathNodes=new Map(),routes=[];
  for(const a of neural.activity){const s=score(a);for(const target of activityTargets(a)){if(!canonical.has(target))continue;activity.set(target,Math.max(activity.get(target)||0,s));if(!cores.length)continue;const p=pathTo(target,g,cores);if(!p.length)continue;routes.push({target,strength:s,path:p,event:a});p.forEach((n,i)=>{pathNodes.set(n,Math.max(pathNodes.get(n)||0,s*(.35+.65*i/Math.max(1,p.length-1))));if(i)pathEdges.add([p[i-1],n].sort().join('\0'))})}}
  topology={graph:g,cores,activity,pathEdges,pathNodes,canonical,routes};
  $('#neurons').textContent=neural.nodes.length;$('#fibers').textContent=neural.fibers.length;
  $('#brainState').textContent=!neural.nodes.length?'WAITING FOR CANONICAL INVENTORY':!cores.length?'CANONICAL CORE MISSING · ROUTING BLOCKED':`V13 ORGANISM ONLINE · ${routes.length} LIVE ROUTE${routes.length===1?'':'S'}`;
}

function posFor(n,i,N){
  const x=Number(n.x),y=Number(n.y),z=Number(n.z);if([x,y,z].every(Number.isFinite))return{x,y,z};
  const t=(i+.5)/Math.max(1,N),phi=Math.acos(1-2*t),theta=Math.PI*(1+Math.sqrt(5))*i,r=.72+.23*((i*37)%17)/16;
  let px=r*Math.sin(phi)*Math.cos(theta),py=r*Math.cos(phi),pz=r*Math.sin(phi)*Math.sin(theta);
  px+=Math.sign(px||1)*.025*(1-Math.abs(py));return{x:px,y:py,z:pz};
}
function project(p,w,h){const cy=Math.cos(rot.y+autoAngle),sy=Math.sin(rot.y+autoAngle),cx=Math.cos(rot.x),sx=Math.sin(rot.x),x=p.x*cy-p.z*sy,z0=p.x*sy+p.z*cy,y=p.y*cx-z0*sx,z=p.y*sx+z0*cx,scale=Math.min(w,h)*.39*(1/(1.7-.35*z));return{x:w/2+x*scale,y:h/2+y*scale,z,scale}}
function bezier(A,B,u,bend){const mx=(A.x+B.x)/2,my=(A.y+B.y)/2-14*bend,om=1-u;return{x:om*om*A.x+2*om*u*mx+u*u*B.x,y:om*om*A.y+2*om*u*my+u*u*B.y}}

function draw(){
  const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2),w=rect.width,h=rect.height;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr)}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);autoAngle+=0.00018;
  const map=new Map(),N=neural.nodes.length;screenNodes=[];
  neural.nodes.forEach((n,i)=>{const p=project(posFor(n,i,N),w,h);map.set(id(n,i),p);screenNodes.push({id:id(n,i),n,x:p.x,y:p.y,z:p.z})});
  const t=performance.now()/1000;
  for(const f of neural.fibers){const[a,b]=ends(f),A=map.get(a),B=map.get(b);if(!A||!B)continue;const active=topology.pathEdges.has([a,b].sort().join('\0')),bend=((String(a).length+String(b).length)%3)-1;ctx.beginPath();ctx.moveTo(A.x,A.y);ctx.quadraticCurveTo((A.x+B.x)/2,(A.y+B.y)/2-14*bend,B.x,B.y);ctx.strokeStyle=active?'rgba(255,210,90,.92)':'rgba(74,210,255,.20)';ctx.lineWidth=active?2.15:.48;ctx.shadowBlur=active?14:0;ctx.shadowColor=active?'#ffd166':'transparent';ctx.stroke();ctx.shadowBlur=0}
  topology.routes.forEach((route,ri)=>{const p=route.path;if(p.length<2)return;const particles=Math.max(2,Math.min(9,Math.ceil(2+route.strength*7)));for(let pi=0;pi<particles;pi++){const phase=(t*(.32+.05*(ri%5))+pi*.21+ri*.11)%1,segments=p.length-1,scaled=phase*segments,si=Math.min(segments-1,Math.floor(scaled)),u=scaled-si,A=map.get(p[si]),B=map.get(p[si+1]);if(!A||!B)continue;const bend=((String(p[si]).length+String(p[si+1]).length)%3)-1,q=bezier(A,B,u,bend),colors=['#55efff','#ff65c5','#ffd166','#b98cff','#ffffff'],c=colors[(ri+pi)%colors.length];ctx.beginPath();ctx.arc(q.x,q.y,1.6+2.2*route.strength,0,Math.PI*2);ctx.fillStyle=c;ctx.shadowBlur=22+14*route.strength;ctx.shadowColor=c;ctx.fill();ctx.shadowBlur=0}});
  for(const s of screenNodes.sort((a,b)=>a.z-b.z)){const strength=Math.max(topology.activity.get(s.id)||0,topology.pathNodes.get(s.id)||0),core=topology.cores.includes(s.id),selected=s.id===selectedId;let r=core?4.2:1.15+(s.z+1)*.42;if(strength)r+=4*strength;if(selected)r+=3;const colors=['#55efff','#b98cff','#ff65c5','#ffd166','#ffffff'];const c=strength?colors[Math.abs(s.id.length)%colors.length]:core?'#ffd166':'#55efff';ctx.beginPath();ctx.arc(s.x,s.y,r,0,Math.PI*2);ctx.fillStyle=c;ctx.globalAlpha=strength?0.98:core?0.92:0.68;ctx.shadowBlur=strength?26:core?18:8;ctx.shadowColor=c;ctx.fill();ctx.globalAlpha=1;ctx.shadowBlur=0}
  requestAnimationFrame(draw);
}

function showNode(x,y){let best=null,dist=18;for(const s of screenNodes){const d=Math.hypot(s.x-x,s.y-y);if(d<dist){best=s;dist=d}}if(!best){$('#nodeLabel').classList.remove('show');return}selectedId=best.id;const l=$('#nodeLabel'),direct=topology.activity.get(best.id)||0,path=topology.pathNodes.get(best.id)||0,role=best.n.role||best.n.type||best.n.kind||best.n.class||'canonical neuron';l.innerHTML=`<b>${esc(best.id)}</b>${esc(role)} · direct ${direct.toFixed(2)} · routed ${path.toFixed(2)}`;l.style.left=Math.max(8,Math.min(canvas.clientWidth-300,best.x+12))+'px';l.style.top=Math.max(45,best.y-10)+'px';l.classList.add('show')}
function findCanonicalNode(query){const q=String(query||'').trim().toLowerCase();if(!q)return null;const list=neural.nodes.map((n,i)=>({id:id(n,i),n})),hit=list.find(x=>x.id.toLowerCase()===q)||list.find(x=>JSON.stringify(x.n).toLowerCase().includes(q)||x.id.toLowerCase().includes(q));if(!hit)return null;const s=screenNodes.find(x=>x.id===hit.id);if(s)showNode(s.x,s.y);return hit}
$('#findForm').onsubmit=e=>{e.preventDefault();const q=$('#nodeFind').value,hit=findCanonicalNode(q);if(!hit)add('Neuron finder',`No canonical neuron matches “${q}”.`,'err')};
canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,moved:false};canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>2)drag.moved=true;rot.y+=dx*.006;rot.x+=dy*.006;drag.x=e.clientX;drag.y=e.clientY;$('#nodeLabel').classList.remove('show')});
canvas.addEventListener('pointerup',e=>{if(drag&&!drag.moved){const r=canvas.getBoundingClientRect();showNode(e.clientX-r.left,e.clientY-r.top)}drag=null});

async function refreshNeural(){
  try{
    const [f,a]=await Promise.all([req('/api/neural/fibers'),req('/api/neural/activity')]);let nd=[],cursor='';
    do{const u='/api/neural/nodes'+(cursor?'?cursor='+encodeURIComponent(cursor):''),page=await req(u);nd.push(...(Array.isArray(page?.neurons)?page.neurons:[]));cursor=page?.next_cursor||''}while(cursor);
    neural.nodes=nd;const fd=dataOf(f),ad=dataOf(a);neural.fibers=Array.isArray(fd)?fd:fd?.fibers||fd?.edges||[];neural.activity=Array.isArray(ad)?ad:ad?.activity||ad?.events||ad?.nodes||[];rebuild();
  }catch{$('#brainState').textContent='NEURAL DATA UNAVAILABLE'}
}

window.addEventListener('pagehide',()=>stopMic());
health();refreshNeural();setInterval(health,5000);setInterval(refreshNeural,1200);requestAnimationFrame(draw);
