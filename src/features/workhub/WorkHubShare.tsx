import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Copy,ExternalLink,LoaderCircle,MessageSquare,Settings2,X} from 'lucide-react';
import {hub,type HubRow} from './projectApi';
import './projects.css';

export function openNotificationSettings(){window.dispatchEvent(new Event('workhub-open-settings'));}

async function copyText(value:string){
  try{if(navigator.clipboard){await navigator.clipboard.writeText(value);return;}}catch{}
  const previous=document.activeElement as HTMLElement|null,area=document.createElement('textarea');
  area.value=value;area.style.position='fixed';area.style.opacity='0';area.setAttribute('aria-hidden','true');
  document.body.appendChild(area);area.select();
  try{if(!document.execCommand('copy'))throw new Error('Select the message below and press Ctrl+C to copy it.');}
  finally{area.remove();previous?.focus();}
}

export function WorkHubShare({itemId,notificationId,compact=false}:{itemId:string;notificationId?:string;compact?:boolean}){
  const [open,setOpen]=useState(false),[data,setData]=useState<HubRow|null>(null),[body,setBody]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const message=useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{
    if(!open)return;let disposed=false;setData(null);setBody('');setError('');setNotice('');
    const path=notificationId?'/notifications/'+notificationId+'/share':'/items/'+itemId+'/share';
    void hub(path).then(result=>{if(!disposed){setData(result);setBody(result.message);}}).catch(error=>{if(!disposed)setError(error.message);});
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')setOpen(false);};window.addEventListener('keydown',escape);
    return()=>{disposed=true;window.removeEventListener('keydown',escape);};
  },[open,itemId,notificationId]);
  const copy=async()=>{setNotice('');setError('');try{await copyText(body);setNotice('Message copied. Paste it into the Teams group and select Send.');}catch(error){setError((error as Error).message);message.current?.focus();message.current?.select();}};
  return <>
    <button className={'btn'+(compact?' wh-share-compact':'')} onClick={()=>setOpen(true)}><MessageSquare size={14}/>Share in Teams</button>
    {open&&createPortal(<div className="wh-backdrop"><section className="wh-dialog" role="dialog" aria-modal="true" aria-label="Share work in Teams">
      <header><h2>Share work in Teams</h2><button className="btn" aria-label="Close Teams sharing" onClick={()=>setOpen(false)}><X size={18}/></button></header>
      <div className="wh-form"><p>Review the message, then copy it and open your existing group chat. Paste and send in Teams. This action does not send automatically or approve the work.</p>
        {!data&&!error&&<p><LoaderCircle size={16} className="spin"/>Preparing message...</p>}
        {data&&<>
          <label>Message<textarea className="textInput" ref={message} rows={12} maxLength={10000} value={body} onChange={event=>setBody(event.target.value)}/></label>
          {data.localAddress&&<p className="wh-muted">This review link uses localhost. Set the office WorkHub address in Settings so colleagues can open the project from their computers.</p>}
          {data.chatUrl?<a className="btn primary wh-share-open" href={data.chatUrl} target="_blank" rel="noopener noreferrer" onClick={()=>void copy()}><ExternalLink size={15}/>Copy &amp; open Teams</a>:<p>No group chat link is saved. Add a shared group or your own group in Settings.</p>}
          <div className="actions"><button className="btn" disabled={!body.trim()} onClick={()=>void copy()}><Copy size={15}/>Copy message</button><button className="btn" onClick={()=>{setOpen(false);openNotificationSettings();}}><Settings2 size={15}/>Notification settings</button></div>
        </>}
        {error&&<p role="alert" className="wh-error">{error}</p>}{notice&&<p role="status" className="wh-success">{notice}</p>}
      </div>
    </section></div>,document.body)}
  </>;
}
