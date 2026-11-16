import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Mic,Square,Upload,X} from 'lucide-react';
import './speech-input.css';

type Job={id:string;status:string;error?:string;result?:{text:string;notice:string;segments?:{uncertain:boolean}[]}};
async function responseData(response:Response){const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Speech recognition failed.');return data;}

export function SpeechInput({disabled,onText,maxLength}:{disabled:boolean;onText:(text:string)=>void;maxLength?:number}){
 const [open,setOpen]=useState(false),[language,setLanguage]=useState('auto'),[state,setState]=useState(''),[error,setError]=useState(''),[text,setText]=useState(''),[notice,setNotice]=useState(''),[ready,setReady]=useState(false),[recording,setRecording]=useState(false);
 const dialog=useRef<HTMLDialogElement>(null),picker=useRef<HTMLInputElement>(null),recorder=useRef<MediaRecorder|null>(null),stream=useRef<MediaStream|null>(null),abort=useRef<AbortController|null>(null),job=useRef(''),timer=useRef<ReturnType<typeof setTimeout>|null>(null),active=useRef(false),mounted=useRef(true),epoch=useRef(0);
 const stop=()=>{if(timer.current)clearTimeout(timer.current);timer.current=null;if(recorder.current?.state==='recording')recorder.current.stop();stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;};
 const forget=()=>{if(job.current){void fetch(`/api/assist/speech/transcriptions/${job.current}`,{method:'DELETE'}).catch(()=>{});job.current='';}};
 const close=()=>{epoch.current++;active.current=false;abort.current?.abort();stop();forget();setRecording(false);setState('');setOpen(false);};
 useEffect(()=>{mounted.current=true;return()=>{epoch.current++;mounted.current=false;active.current=false;abort.current?.abort();stop();forget();};},[]);
 useEffect(()=>{if(!open)return;dialog.current?.showModal();active.current=true;const controller=new AbortController();abort.current=controller;setReady(false);setError('');setText('');setNotice('');
  void fetch('/api/assist/speech/status',{signal:controller.signal}).then(responseData).then(data=>{setReady(data.ready);if(!data.ready)setError('Local speech recognition is not configured. Ask the server administrator to install the multilingual speech model.');}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
 },[open]);
 async function transcribe(file:File){
  if(file.size>20*1024*1024){setError('Choose audio smaller than 20 MB.');return;}
  const currentEpoch=epoch.current;setError('');setText('');setNotice('');setState('Uploading recording');forget();const controller=new AbortController();abort.current=controller;
  try{const body=new FormData();body.append('file',file);body.append('language',language);
   let value:Job=await responseData(await fetch('/api/assist/speech/transcriptions',{method:'POST',body,signal:controller.signal}));job.current=value.id;
   if(!active.current){forget();return;}
   while(active.current){
    if(value.status==='failed')throw new Error(value.error||'Transcription failed.');
    if(value.status==='cancelled')break;
    if(value.status==='ready'){setText(value.result?.text||'');setNotice((value.result?.segments?.some(s=>s.uncertain)?'Some words may be uncertain. ':'')+(value.result?.notice||'Review this transcript before using it.'));break;}
    setState(value.status==='queued'?'Waiting for local recognition':value.status==='loading'?'Reading audio locally':'Transcribing locally');
    await new Promise(resolve=>setTimeout(resolve,700));if(controller.signal.aborted)break;
    value=await responseData(await fetch(`/api/assist/speech/transcriptions/${value.id}`,{signal:controller.signal,cache:'no-store'}));
   }
  }catch(e){if(active.current&&e instanceof Error&&e.name!=='AbortError')setError(e.message);}
  finally{if(mounted.current&&currentEpoch===epoch.current)setState('');}
 }
 async function record(){
  setError('');if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){setError('Microphone recording needs HTTPS or localhost and a supported browser. You can upload an audio file instead.');return;}
  const currentEpoch=epoch.current;
  try{const source=await navigator.mediaDevices.getUserMedia({audio:true});if(!active.current||currentEpoch!==epoch.current){source.getTracks().forEach(t=>t.stop());return;}stream.current=source;
   const type=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(t=>MediaRecorder.isTypeSupported(t));const capture=new MediaRecorder(source,type?{mimeType:type}:undefined);recorder.current=capture;const chunks:BlobPart[]=[];let size=0;
   capture.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);size+=e.data.size;if(size>20*1024*1024)stop();}};
   capture.onerror=()=>{active.current=false;stop();setError('Recording failed. Close this dialog and try an audio upload.');setRecording(false);};
   capture.onstop=()=>{source.getTracks().forEach(t=>t.stop());if(!active.current||currentEpoch!==epoch.current)return;if(timer.current)clearTimeout(timer.current);setRecording(false);const mime=capture.mimeType;void transcribe(new File(chunks,`recording.${mime.includes('mp4')?'m4a':mime.includes('ogg')?'ogg':'webm'}`,{type:mime}));};
   capture.start(1000);setRecording(true);timer.current=setTimeout(stop,120000);
  }catch(e){setError(e instanceof Error?e.message:'Microphone access was denied. Upload a recording instead.');}
 }
 const busy=!!state||recording;
 return <><button type="button" className="btn chatSpeechButton" aria-label="Speech to text" title="Tamil, English, Hindi or Tanglish speech to text" disabled={disabled} onClick={()=>setOpen(true)}><Mic size={17}/></button>{open&&createPortal(<dialog className="chopperSpeechDialog" ref={dialog} aria-labelledby="speechTitle" onCancel={e=>{e.preventDefault();close();}}>
  <header><div><h2 id="speechTitle">Speak to Chopper</h2><p>Record or upload, review the text, then use it in your message.</p></div><button type="button" className="btn" aria-label="Close speech input" onClick={close}><X size={18}/></button></header>
  <label>Speech language<select aria-label="Speech language" value={language} disabled={busy} onChange={e=>setLanguage(e.target.value)}><option value="auto">Auto detect</option><option value="ta">Tamil / தமிழ்</option><option value="en">English</option><option value="hi">Hindi / हिन्दी</option><option value="tanglish">Tanglish / Tamil + English</option></select></label>
  <div className="speechActions"><button type="button" className="btn primary" disabled={!ready||!!state} onClick={()=>recording?stop():void record()}>{recording?<Square size={16}/>:<Mic size={16}/>} {recording?'Stop recording':'Record audio'}</button><button type="button" className="btn" disabled={!ready||busy} onClick={()=>picker.current?.click()}><Upload size={16}/>Upload audio</button><input ref={picker} type="file" hidden accept=".wav,.mp3,.webm,.ogg,.m4a,.mp4,.flac" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void transcribe(file);}}/></div>
  <small>WAV, MP3, WebM, M4A, OGG, FLAC · up to 20 MB / 5 minutes. Microphone recordings stop after 2 minutes.</small>
  {recording&&<p role="status">Recording… Press Stop recording when finished.</p>}{state&&<p role="status">{state}…</p>}{error&&<p className="speechError" role="alert">{error}</p>}
  <label>Review transcript<textarea aria-label="Review speech transcript" value={text} disabled={busy} onChange={e=>setText(e.target.value)} placeholder="Your transcript will appear here. Check names, numbers and PLC tags." rows={6}/></label>
  {notice&&<p role="status">{notice}</p>}{maxLength!==undefined&&text.length>maxLength&&<p className="speechError" role="alert">Shorten the transcript to {Math.max(0,maxLength)} characters to fit the remaining message space.</p>}
  <p className="speechPrivacy">Audio is processed by the local server and deleted after processing. Temporary transcripts expire after 24 hours. Tanglish can contain Tamil script. Using text adds it to your draft; you choose when to send.</p>
  <footer><button type="button" className="btn" onClick={close}>Cancel</button><button type="button" className="btn primary" disabled={busy||!text.trim()||(maxLength!==undefined&&text.length>maxLength)} onClick={()=>{onText(text.trim());close();}}>Use transcript</button></footer>
 </dialog>,document.body)}</>;
}
