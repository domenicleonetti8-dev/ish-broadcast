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

let busy=false,armed=false,muted=false,stream=null,context=null,source=null,processor=null;
let sampleRate=16000,noiseFloor=.008,speech=false,speechChunks=[],preRoll=[],silenceFrames=0,submittingAmbient=false;
let wakeContinuationUntil=0,activationPromise=null,reacquireTimer=null,desiredArmed=true,explicitlyDisarmed=false;
const PRE_ROLL=7,SILENCE_FRAMES=10,MAX_SPEECH_FRAMES=190,WAKE_CONTINUATION_MS=6500,REACQUIRE_DELAY_MS=900;
const DESIRED_KEY='eira2.voice.desiredArmed';

function setMode(text,mode='idle'){status.textContent=text;status.dataset.mode=mode;if(core)core.dataset.mode=mode}
function append(role,text){const clean=String(text||'').trim();if(!clean)return;const row=document.createElement('div');row.className=`eiraTurn ${role}`;const who=document.createElement('div');who.className='eiraTurnWho';who.textContent=role==='user'?'YOU':'EIRA';const body=document.createElement('div');body.className='eiraTurnText';body.textContent=clean;row.append(who,body);transcript.appendChild(row);transcript.scrollTop=transcript.scrollHeight}
function rms(samples){let sum=0;for(let i=0;i<samples.length;i++){const v=samples[i];sum+=v*v}return Math.sqrt(sum/Math.max(1,samples.length))}
function flatten(parts){let n=0;for(const p of parts)n+=p.length;const out=new Float32Array(n);let o=0;for(const p of parts){out.set(p,o);o+=p.length}return out}
function resample16k(samples,fromRate){if(fromRate===16000)return samples;const ratio=fromRate/16000,length=Math.max(1,Math.round(samples.length/ratio)),out=new Float32Array(length);for(let i=0;i<length;i++){const pos=i*ratio,left=Math.floor(pos),right=Math.min(samples.length-1,left+1),f=pos-left;out[i]=samples[left]*(1-f)+samples[right]*f}return out}
function pcm16(samples){const out=new ArrayBuffer(samples.length*2),view=new DataView(out);for(let i=0;i<samples.length;i++){const s=Math.max(-1,Math.min(1,samples[i]));view.setInt16(i*2,s<0?s*0x8000:s*0x7fff,true)}return out}
function rememberDesired(value){desiredArmed=Boolean(value);try{sessionStorage.setItem(DESIRED_KEY,desiredArmed?'1':'0')}catch(_){}}
function permissionName(error){return String(error?.name||'')}
function isPermissionError(error){return ['NotAllowedError','SecurityError','PermissionDeniedError'].includes(permissionName(error))}
function liveTracks(){return (stream?.getAudioTracks?.()||[]).filter(t=>t.readyState==='live')}
function resetSpeech(){speech=false;speechChunks=[];preRoll=[];silenceFrames=0;wakeContinuationUntil=0}

async function postText(text){if(busy)return;const clean=String(text||'').trim();if(!clean)return;busy=true;send.disabled=true;input.disabled=true;append('user',clean);setMode('THINKING…','thinking');try{const response=await fetch('/v1/text',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify({text:clean,source:'iphone_text'})});const payload=await response.json().catch(()=>({}));if(!response.ok||!payload.ok)throw new Error(payload.error||`HTTP ${response.status}`);append('eira',payload.response||payload.reply||payload.text||'');setMode(armed&&!muted?'AMBIENT LISTENING ACTIVE':payload.verified?'VERIFIED RESPONSE':'RESPONSE RECEIVED',armed&&!muted?'listening':'ready')}catch(error){setMode(`COMMUNICATION ERROR: ${error.message||error}`,'error')}finally{busy=false;send.disabled=false;input.disabled=false;input.focus()}}
form.addEventListener('submit',event=>{event.preventDefault();const text=input.value;input.value='';postText(text)});

async function submitAmbient(parts){if(submittingAmbient||busy||muted||!armed||!parts.length)return;const samples=flatten(parts);if(samples.length<Math.max(1,sampleRate*.18))return;submittingAmbient=true;setMode('TRANSCRIBING…','transcribing');try{const body=pcm16(resample16k(samples,sampleRate));const continuation=Date.now()<wakeContinuationUntil;const endpoint=continuation?'/v1/listen?sample_rate=16000&channels=1&sample_width=2':'/v1/ambient?sample_rate=16000&channels=1&sample_width=2';if(continuation)wakeContinuationUntil=0;const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/octet-stream'},cache:'no-store',body});const payload=await response.json().catch(()=>({}));if(!response.ok||!payload.ok)throw new Error(payload.error||`HTTP ${response.status}`);if(continuation){if(payload.utterance)append('user',payload.utterance);if(payload.response)append('eira',payload.response);setMode(muted?'MICROPHONE MUTED':'AMBIENT LISTENING ACTIVE',muted?'muted':'listening');return}if(payload.invoked){if(payload.utterance)append('user',payload.utterance);if(payload.awaiting_utterance){wakeContinuationUntil=Date.now()+WAKE_CONTINUATION_MS;setMode('WAKE WORD HEARD — KEEP TALKING','listening')}else if(payload.response){append('eira',payload.response);setMode('AMBIENT LISTENING ACTIVE','listening')}}else if(!busy&&!muted){setMode('AMBIENT LISTENING ACTIVE','listening')}}catch(error){wakeContinuationUntil=0;setMode(`AMBIENT VOICE ERROR: ${error.message||error}`,'error')}finally{submittingAmbient=false}}

function audioFrame(samples){if(!armed||muted)return;const level=rms(samples);if(!speech)noiseFloor=Math.max(.002,Math.min(.04,noiseFloor*.985+level*.015));const startThreshold=Math.max(.018,noiseFloor*2.7),holdThreshold=Math.max(.010,noiseFloor*1.55);const copy=new Float32Array(samples);preRoll.push(copy);if(preRoll.length>PRE_ROLL)preRoll.shift();if(!speech&&level>=startThreshold){speech=true;speechChunks=preRoll.map(x=>new Float32Array(x));silenceFrames=0;setMode(Date.now()<wakeContinuationUntil?'WAKE WORD ACTIVE — LISTENING…':'HEARING SPEECH…','listening');return}if(!speech)return;speechChunks.push(copy);if(level<holdThreshold)silenceFrames++;else silenceFrames=0;if(silenceFrames>=SILENCE_FRAMES||speechChunks.length>=MAX_SPEECH_FRAMES){const segment=speechChunks;speech=false;speechChunks=[];silenceFrames=0;preRoll=[];submitAmbient(segment)}}

async function releaseHardware({clearIntent=false}={}){if(clearIntent){rememberDesired(false);explicitlyDisarmed=true}armed=false;resetSpeech();clearTimeout(reacquireTimer);reacquireTimer=null;try{processor?.disconnect()}catch(_){}try{source?.disconnect()}catch(_){}try{processor&&(processor.onaudioprocess=null)}catch(_){}for(const track of stream?.getTracks?.()||[]){try{track.onended=null;track.stop()}catch(_){}}if(context){try{context.onstatechange=null}catch(_){}await context.close().catch(()=>{})}stream=context=source=processor=null;mic.classList.remove('active');mic.textContent=desiredArmed?'RECONNECTING':'ACTIVATE EIRA';mute.disabled=!desiredArmed}

function scheduleReacquire(reason='stream_interrupted'){if(!desiredArmed||explicitlyDisarmed||document.visibilityState==='hidden')return;clearTimeout(reacquireTimer);setMode(`RECONNECTING MICROPHONE… ${reason}`,'reconnecting');reacquireTimer=setTimeout(()=>ensureActive(reason).catch(()=>{}),REACQUIRE_DELAY_MS)}

async function buildAudioGraph(){context=new (window.AudioContext||window.webkitAudioContext)();context.onstatechange=()=>{if(!desiredArmed||explicitlyDisarmed)return;const state=context?.state;if(state==='suspended'||state==='interrupted'){context.resume().catch(()=>scheduleReacquire(`audio_${state}`))}else if(state==='closed'){scheduleReacquire('audio_closed')}};await context.resume();sampleRate=context.sampleRate;source=context.createMediaStreamSource(stream);processor=context.createScriptProcessor(4096,1,1);processor.onaudioprocess=e=>audioFrame(e.inputBuffer.getChannelData(0));source.connect(processor);processor.connect(context.destination)}

async function activate({reason='activate'}={}){if(armed&&liveTracks().length&&context&&context.state!=='closed')return true;if(activationPromise)return activationPromise;activationPromise=(async()=>{if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){setMode('IPHONE MICROPHONE REQUIRES HTTPS','permission');if(hint)hint.textContent='Open this EIRA page through HTTPS to use continuous voice.';return false}rememberDesired(true);explicitlyDisarmed=false;setMode(reason==='activate'?'ACTIVATING MICROPHONE…':'RECONNECTING MICROPHONE…',reason==='activate'?'activating':'reconnecting');await releaseHardware({clearIntent:false});try{stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});for(const track of stream.getAudioTracks()){track.enabled=!muted;track.onended=()=>scheduleReacquire('track_ended')}await buildAudioGraph();armed=true;mic.classList.add('active');mic.textContent='LISTENING';mute.disabled=false;mute.classList.toggle('active',muted);mute.textContent=muted?'UNMUTE':'MUTE';if(hint)hint.textContent=muted?'Microphone is armed but muted.':'Ambient listening is local and continuous. Say “Eira …” when you want a response.';setMode(muted?'MICROPHONE MUTED':'AMBIENT LISTENING ACTIVE',muted?'muted':'listening');return true}catch(error){armed=false;stream=context=source=processor=null;if(isPermissionError(error)){setMode('MICROPHONE PERMISSION NEEDED','permission');mic.classList.remove('active');mic.textContent='ALLOW MICROPHONE';mute.disabled=true;if(hint)hint.textContent='Safari requires microphone permission or a user gesture. Tap ALLOW MICROPHONE once; EIRA will auto-rearm after that.'}else{setMode(`MICROPHONE ERROR: ${error.message||error}`,'error');scheduleReacquire(permissionName(error)||'activation_failed')}return false}})();try{return await activationPromise}finally{activationPromise=null}}

async function ensureActive(reason='ensure'){if(!desiredArmed||explicitlyDisarmed)return false;if(armed&&liveTracks().length&&context){if(context.state==='suspended'||context.state==='interrupted')await context.resume().catch(()=>{});if(context.state==='running')return true}return activate({reason})}

function setMuted(next){if(!desiredArmed)return;muted=Boolean(next);for(const track of stream?.getAudioTracks?.()||[])track.enabled=!muted;mute.classList.toggle('active',muted);mute.textContent=muted?'UNMUTE':'MUTE';resetSpeech();setMode(muted?'MICROPHONE MUTED':'AMBIENT LISTENING ACTIVE',muted?'muted':'listening');if(!muted)ensureActive('unmute').catch(()=>{})}

mic.addEventListener('click',async()=>{if(desiredArmed&&armed){await releaseHardware({clearIntent:true});setMode('MICROPHONE INACTIVE','idle');if(hint)hint.textContent='Voice is intentionally disarmed. Tap ACTIVATE EIRA to arm it again.';return}rememberDesired(true);explicitlyDisarmed=false;await ensureActive('activate')});
mute.addEventListener('click',()=>setMuted(!muted));
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){ensureActive('visibility_return').catch(()=>{})}else if(desiredArmed){releaseHardware({clearIntent:false}).catch(()=>{})}});
window.addEventListener('pageshow',()=>{ensureActive('pageshow').catch(()=>{})});
window.addEventListener('focus',()=>{ensureActive('focus').catch(()=>{})});
window.addEventListener('online',()=>{ensureActive('online').catch(()=>{})});
window.addEventListener('pagehide',()=>{if(desiredArmed)releaseHardware({clearIntent:false}).catch(()=>{})});

try{const saved=sessionStorage.getItem(DESIRED_KEY);desiredArmed=saved===null?true:saved==='1'}catch(_){desiredArmed=true}
explicitlyDisarmed=!desiredArmed;
setMode(desiredArmed?'ACTIVATING MICROPHONE…':'MICROPHONE INACTIVE',desiredArmed?'activating':'idle');
if(desiredArmed){queueMicrotask(()=>ensureActive('page_load').catch(()=>{}))}
})();
