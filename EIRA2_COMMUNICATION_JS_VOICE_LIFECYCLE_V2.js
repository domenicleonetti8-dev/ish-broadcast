(() => {
'use strict';

const form=document.getElementById('eiraTalkForm');
const input=document.getElementById('eiraTalkInput');
const send=document.getElementById('eiraTalkSend');
const mic=document.getElementById('eiraMic');
const mute=document.getElementById('eiraMute');
const status=document.getElementById('eiraTalkStatus');
const transcript=document.getElementById('eiraTranscript');
const core=document.getElementById('voiceCore');
const hint=document.getElementById('ambientHint');
if(!form||!input||!send||!mic||!mute||!status||!transcript)return;

const INTENT_KEY='eira.voice.armed.v2';
let busy=false,armed=false,arming=false,muted=false,stream=null,context=null,source=null,processor=null,rearmTimer=null;
let sampleRate=16000,noiseFloor=.008,speech=false,speechChunks=[],preRoll=[],silenceFrames=0,submittingAmbient=false;
let wakeContinuationUntil=0;
const PRE_ROLL=7,SILENCE_FRAMES=10,MAX_SPEECH_FRAMES=190,WAKE_CONTINUATION_MS=6500,REARM_DELAY_MS=650;

function setMode(text,mode='idle'){
  status.textContent=text;status.dataset.mode=mode;if(core)core.dataset.mode=mode;
}
function append(role,text){
  const clean=String(text||'').trim();if(!clean)return;
  const row=document.createElement('div');row.className=`eiraTurn ${role}`;
  const who=document.createElement('div');who.className='eiraTurnWho';who.textContent=role==='user'?'YOU':'EIRA';
  const body=document.createElement('div');body.className='eiraTurnText';body.textContent=clean;
  row.append(who,body);transcript.appendChild(row);transcript.scrollTop=transcript.scrollHeight;
}
function rms(samples){let sum=0;for(let i=0;i<samples.length;i++){const v=samples[i];sum+=v*v}return Math.sqrt(sum/Math.max(1,samples.length))}
function flatten(parts){let n=0;for(const p of parts)n+=p.length;const out=new Float32Array(n);let o=0;for(const p of parts){out.set(p,o);o+=p.length}return out}
function resample16k(samples,fromRate){
  if(fromRate===16000)return samples;const ratio=fromRate/16000,length=Math.max(1,Math.round(samples.length/ratio)),out=new Float32Array(length);
  for(let i=0;i<length;i++){const pos=i*ratio,left=Math.floor(pos),right=Math.min(samples.length-1,left+1),f=pos-left;out[i]=samples[left]*(1-f)+samples[right]*f}return out;
}
function pcm16(samples){const out=new ArrayBuffer(samples.length*2),view=new DataView(out);for(let i=0;i<samples.length;i++){const s=Math.max(-1,Math.min(1,samples[i]));view.setInt16(i*2,s<0?s*0x8000:s*0x7fff,true)}return out}
function rememberedIntent(){
  try{return localStorage.getItem(INTENT_KEY)!=='0'}catch(_){return true}
}
function rememberIntent(value){
  try{localStorage.setItem(INTENT_KEY,value?'1':'0')}catch(_){}
}
function resetSpeechState(){
  speech=false;speechChunks=[];preRoll=[];silenceFrames=0;wakeContinuationUntil=0;
}
function liveTrack(){
  const tracks=stream?.getAudioTracks?.()||[];
  return tracks.find(track=>track.readyState==='live')||null;
}
function streamHealthy(){
  return Boolean(stream&&liveTrack()&&context&&context.state!=='closed'&&source&&processor);
}
async function releaseAudio({keepIntent=true}={}){
  if(rearmTimer){clearTimeout(rearmTimer);rearmTimer=null}
  resetSpeechState();
  try{processor?.disconnect()}catch(_){}
  try{source?.disconnect()}catch(_){}
  for(const track of stream?.getTracks?.()||[]){try{track.onended=null;track.stop()}catch(_){}}
  if(context){try{await context.close()}catch(_){}}
  stream=context=source=processor=null;
  armed=false;arming=false;
  if(!keepIntent)rememberIntent(false);
}
function scheduleRearm(reason='reconnecting'){
  if(!rememberedIntent()||muted||document.visibilityState==='hidden')return;
  if(rearmTimer)clearTimeout(rearmTimer);
  setMode('MICROPHONE RECONNECTING…','reconnecting');
  rearmTimer=setTimeout(()=>{rearmTimer=null;ensureArmed(reason).catch(()=>{})},REARM_DELAY_MS);
}
function attachLifecycleGuards(){
  for(const track of stream?.getAudioTracks?.()||[]){
    track.onended=()=>{if(rememberedIntent()&&!muted){releaseAudio({keepIntent:true}).finally(()=>scheduleRearm('track-ended'))}};
  }
  if(context){
    context.onstatechange=()=>{
      if(!rememberedIntent()||muted)return;
      if(context.state==='suspended'&&document.visibilityState==='visible'){
        context.resume().catch(()=>scheduleRearm('context-suspended'));
      }else if(context.state==='closed'){
        scheduleRearm('context-closed');
      }
    };
  }
}
function renderArmedState(){
  mic.classList.add('active');mic.textContent=muted?'ARMED':'LISTENING';mute.disabled=false;
  mute.classList.toggle('active',muted);mute.textContent=muted?'UNMUTE':'MUTE';
  if(hint)hint.textContent=muted?'Listening is paused. The microphone remains armed and will resume when unmuted.':'Ambient listening is local and continuous. Say “Eira …” when you want a response.';
  setMode(muted?'MICROPHONE MUTED':'AMBIENT LISTENING ACTIVE',muted?'muted':'listening');
}

async function postText(text){
  if(busy)return;const clean=String(text||'').trim();if(!clean)return;
  busy=true;send.disabled=true;input.disabled=true;append('user',clean);setMode('THINKING…','thinking');
  try{
    const response=await fetch('/v1/text',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify({text:clean})});
    const payload=await response.json().catch(()=>({}));if(!response.ok||!payload.ok)throw new Error(payload.error||`HTTP ${response.status}`);
    append('eira',payload.response||payload.result?.response||payload.result?.text||'');
    setMode(armed&&!muted?'AMBIENT LISTENING ACTIVE':payload.verified?'VERIFIED RESPONSE':'RESPONSE RECEIVED',armed&&!muted?'listening':'ready');
  }catch(error){setMode(`COMMUNICATION ERROR: ${error.message||error}`,'error')}
  finally{busy=false;send.disabled=false;input.disabled=false;input.focus()}
}
form.addEventListener('submit',event=>{event.preventDefault();const text=input.value;input.value='';postText(text)});

async function submitAmbient(parts){
  if(submittingAmbient||busy||muted||!armed||!parts.length)return;
  const samples=flatten(parts);if(samples.length<Math.max(1,sampleRate*.18))return;
  submittingAmbient=true;
  try{
    const body=pcm16(resample16k(samples,sampleRate));
    const continuation=Date.now()<wakeContinuationUntil;
    const endpoint=continuation?'/v1/listen?sample_rate=16000&channels=1&sample_width=2':'/v1/ambient?sample_rate=16000&channels=1&sample_width=2';
    if(continuation)wakeContinuationUntil=0;
    const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/octet-stream'},cache:'no-store',body});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok||!payload.ok)throw new Error(payload.error||`HTTP ${response.status}`);
    if(continuation){
      if(payload.utterance)append('user',payload.utterance);
      if(payload.response)append('eira',payload.response);
      setMode('AMBIENT LISTENING ACTIVE','listening');
      return;
    }
    if(payload.invoked){
      if(payload.utterance)append('user',payload.utterance);
      if(payload.awaiting_utterance){wakeContinuationUntil=Date.now()+WAKE_CONTINUATION_MS;setMode('WAKE WORD HEARD — KEEP TALKING','listening')}
      else if(payload.response){append('eira',payload.response);setMode('AMBIENT LISTENING ACTIVE','listening')}
    }else if(!busy&&!muted){setMode('AMBIENT LISTENING ACTIVE','listening')}
  }catch(error){
    wakeContinuationUntil=0;
    setMode(`AMBIENT VOICE ERROR: ${error.message||error}`,'error');
    if(rememberedIntent()&&!muted&&!streamHealthy())scheduleRearm('submit-failure');
  }finally{submittingAmbient=false}
}

function audioFrame(samples){
  if(!armed||muted)return;
  const level=rms(samples);
  if(!speech)noiseFloor=Math.max(.002,Math.min(.04,noiseFloor*.985+level*.015));
  const startThreshold=Math.max(.018,noiseFloor*2.7),holdThreshold=Math.max(.010,noiseFloor*1.55);
  const copy=new Float32Array(samples);
  preRoll.push(copy);if(preRoll.length>PRE_ROLL)preRoll.shift();
  if(!speech&&level>=startThreshold){speech=true;speechChunks=preRoll.map(x=>new Float32Array(x));silenceFrames=0;setMode(Date.now()<wakeContinuationUntil?'WAKE WORD ACTIVE — LISTENING…':'HEARING SPEECH…','listening');return}
  if(!speech)return;
  speechChunks.push(copy);
  if(level<holdThreshold)silenceFrames++;else silenceFrames=0;
  if(silenceFrames>=SILENCE_FRAMES||speechChunks.length>=MAX_SPEECH_FRAMES){const segment=speechChunks;speech=false;speechChunks=[];silenceFrames=0;preRoll=[];setMode(Date.now()<wakeContinuationUntil?'WAKE WORD ACTIVE — LISTENING…':'AMBIENT LISTENING ACTIVE','listening');submitAmbient(segment)}
}

async function ensureArmed(reason='automatic'){
  if(arming)return;
  if(!rememberedIntent())return;
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
    setMode('IPHONE MICROPHONE REQUIRES HTTPS','error');
    if(hint)hint.textContent='Open this same EIRA page through HTTPS.';
    return;
  }
  if(streamHealthy()){
    armed=true;
    const track=liveTrack();if(track)track.enabled=!muted;
    if(context.state==='suspended'&&document.visibilityState==='visible')await context.resume().catch(()=>{});
    renderArmedState();return;
  }
  arming=true;setMode(reason==='automatic'?'ACTIVATING MICROPHONE…':'MICROPHONE RECONNECTING…','activating');
  try{
    await releaseAudio({keepIntent:true});
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    context=new (window.AudioContext||window.webkitAudioContext)();
    try{await context.resume()}catch(_){}
    sampleRate=context.sampleRate;
    source=context.createMediaStreamSource(stream);
    processor=context.createScriptProcessor(4096,1,1);
    processor.onaudioprocess=e=>audioFrame(e.inputBuffer.getChannelData(0));
    source.connect(processor);processor.connect(context.destination);
    armed=true;arming=false;
    const track=liveTrack();if(track)track.enabled=!muted;
    attachLifecycleGuards();renderArmedState();
  }catch(error){
    armed=false;arming=false;stream=context=source=processor=null;
    const name=String(error?.name||'');
    if(name==='NotAllowedError'||name==='SecurityError'){
      setMode('MICROPHONE PERMISSION NEEDED','permission');
      if(hint)hint.textContent='Tap LISTENING once to grant microphone access. After permission is granted, EIRA will re-arm automatically on future resumes.';
    }else{
      setMode(`MICROPHONE RECONNECTING: ${error?.message||error}`,'reconnecting');
      scheduleRearm('activation-failure');
    }
  }
}
async function activateFromGesture(){
  rememberIntent(true);
  await ensureArmed('gesture');
}
function setMuted(next){
  if(!rememberedIntent())rememberIntent(true);
  muted=Boolean(next);resetSpeechState();
  const track=liveTrack();if(track)track.enabled=!muted;
  if(muted){
    renderArmedState();
  }else{
    ensureArmed('unmute').catch(()=>scheduleRearm('unmute'));
  }
}
async function handleVisibleResume(){
  if(!rememberedIntent()||muted)return;
  if(context?.state==='suspended')await context.resume().catch(()=>{});
  if(!streamHealthy())await ensureArmed('resume');
  else{armed=true;renderArmedState()}
}
mic.addEventListener('click',()=>{activateFromGesture().catch(error=>setMode(`MICROPHONE ERROR: ${error.message||error}`,'error'))});
mute.addEventListener('click',()=>setMuted(!muted));
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')handleVisibleResume().catch(()=>scheduleRearm('visibility'))});
window.addEventListener('pageshow',()=>{handleVisibleResume().catch(()=>scheduleRearm('pageshow'))});
window.addEventListener('focus',()=>{handleVisibleResume().catch(()=>scheduleRearm('focus'))});
window.addEventListener('pagehide',()=>{resetSpeechState();if(context?.state==='running')context.suspend().catch(()=>{})});
window.addEventListener('beforeunload',()=>{for(const track of stream?.getTracks?.()||[]){try{track.onended=null}catch(_){}}});

rememberIntent(true);
setMode('ACTIVATING MICROPHONE…','activating');
ensureArmed('automatic').catch(()=>scheduleRearm('initial'));
})();