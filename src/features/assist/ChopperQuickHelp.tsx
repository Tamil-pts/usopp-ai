import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Bot,Expand,RotateCcw,Send,X} from 'lucide-react';
import {requestChopper} from './chopperRequest';
import {ChopperReply} from './ChopperReply';
import {FEATURES} from '../../shared/features';
import {useProjectIntelligence,ContextUsage} from './ProjectIntelligence';
import './chopper-quick-help.css';
import {openDashboardBuilder,isWorkHubDashboardRequest} from '../workhub/dashboards/bridge';

type WindowContext={page:string;label:string;projectName?:string;projectPath?:string;details?:Record<string,unknown>;findings?:any[];counts?:Record<string,number>};
type Message={role:'user'|'assistant';text:string;scope:string;source?:string;evidence?:any[];contextUsage?:any;retrieval?:any};
export function ChopperQuickHelp({context,onOpenChat,placement='floating'}:{context:WindowContext;onOpenChat:()=>void;placement?:'floating'|'top'}){
 const [open,setOpen]=useState(false),[question,setQuestion]=useState(''),[messages,setMessages]=useState<Message[]>([]);
 const [busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[error,setError]=useState('');
 const intelligence=useProjectIntelligence(open?context.projectPath||'':'');
 const launcher=useRef<HTMLButtonElement>(null),input=useRef<HTMLTextAreaElement>(null),scroll=useRef<HTMLDivElement>(null),controller=useRef<AbortController|null>(null),lock=useRef(false);
 const close=()=>{setOpen(false);launcher.current?.focus()};
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{if(!open)return;input.current?.focus();const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();close()}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[open]);
 useEffect(()=>{if(scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight},[messages,progress,open]);
 async function ask(text=question,guideOnly=false){
  text=text.trim();if(!text||lock.current)return;lock.current=true;setBusy(true);setError('');setQuestion('');setProgress('Preparing help…');
  const scope=context.label,abort=new AbortController();controller.current=abort;
  const history=messages.slice(-6).map(message=>({role:message.role,content:`[${message.scope}] ${message.text.slice(0,1600)}`}));
  setMessages(current=>[...current.slice(-29),{role:'user',text,scope}]);
  try{
   if(!guideOnly&&isWorkHubDashboardRequest(text)){
    openDashboardBuilder(text);setMessages(current=>[...current,{role:'assistant',scope,text:'I opened My Dashboard in WorkHub. Review the proposed widget and layout settings there, apply them to the editor, then save when ready.',source:'dashboard-builder'}]);close();return;
   }
   const status=await requestChopper({task:guideOnly?'Window assistant':'Chopper conversation',guideOnly,question:text.slice(0,4000),history,context:{offlineOnly:true,intelligenceProjectId:intelligence.state?.projectId,applicationFeatures:FEATURES,currentWindow:{page:context.page,details:context.details,findings:context.findings},projectName:context.projectName,counts:context.counts}},abort.signal,value=>setProgress(value.stage||'Preparing answer…'));
   if(abort.signal.aborted)return;const data=status.result;
   setMessages(current=>[...current,{role:'assistant',scope,text:data.answer||'Open full Chat for a detailed project analysis.',source:data.source,evidence:[...(data.evidence||[]),...(data.helpEvidence||[])],contextUsage:data.contextUsage,retrieval:data.retrieval}]);
  }catch(reason){if(!abort.signal.aborted)setError(reason instanceof Error?reason.message:'Chopper is unavailable.')}
  finally{if(!abort.signal.aborted){setBusy(false);setProgress('');lock.current=false}}
 }
 return <><button type="button" ref={launcher} className={'btn chopperQuickLauncher '+(open?'selected':'')} title="How can I help?" aria-label="Open Chopper chat" aria-haspopup="dialog" aria-expanded={open} aria-controls="chopper-quick-help" onClick={()=>open?close():setOpen(true)}><Bot size={20}/><span>{placement==='top'?'How can I help?':'Chopper'}</span>{busy&&<i className="chopperBusyDot"/>}</button>{open&&createPortal(<section id="chopper-quick-help" role="dialog" aria-modal="false" aria-labelledby="chopper-quick-title" className={'chopperQuickPanel'+(placement==='top'?' topCentered':'')}>
  <header><span className="chopperQuickAvatar"><Bot size={22}/></span><div><h2 id="chopper-quick-title">Chopper</h2><p>Chat and step-by-step guidance</p></div><button className="btn" title="Open full Chat" aria-label="Open full Chopper Chat" onClick={()=>{close();onOpenChat()}}><Expand size={16}/></button><button className="btn" aria-label="Close Chopper chat" onClick={close}><X size={18}/></button></header>
  <div className="chopperQuickContext"><span>Current window</span><b>{context.label}</b>{context.details?.target!=null&&<small>{String(context.details.target)}</small>}</div>
  <div className="chopperQuickMessages" ref={scroll} role="log" aria-label="Chopper conversation" aria-live="polite">
   {!messages.length&&<div className="chopperQuickWelcome"><Bot size={28}/><h3>How can I help?</h3><p>Ask about this page or your engineering work.</p></div>}
   {messages.map((message,index)=><article key={index} className={'chopperQuickMessage '+message.role}><small>{message.role==='assistant'?'Chopper':'You'} · {message.scope}</small><ChopperReply text={message.text}/><ContextUsage usage={message.contextUsage} retrieval={message.retrieval}/>{message.evidence?.length? <details><summary>View evidence ({message.evidence.length})</summary>{message.evidence.map((item,i)=><div key={i}><b>{item.sourceId?`[${item.sourceId}] `:''}{item.file}{item.line?`:${item.line}`:''}</b><pre>{item.excerpt}</pre></div>)}</details>:null}{message.source==='local-window-guide'&&<small>Workflow guide · deterministic results remain in the workspace.</small>}</article>)}
   {busy&&<p className="chopperQuickProgress" role="status">{progress}</p>}
  </div>
  {error&&<p className="chopperQuickError" role="alert">{error}</p>}
  <div className="chopperQuickSuggestions"><button className="btn" disabled={busy} onClick={()=>void ask('Explain how to use this window, step by step.',true)}>Window guide</button><button className="btn" disabled={busy} onClick={()=>void ask('Explain the current reported findings and the next action. Do not infer a pass or failure without evidence.')}>Explain findings</button><button className="btn" disabled={busy||!messages.length} title="Clear this help conversation" aria-label="Clear Chopper help conversation" onClick={()=>{setMessages([]);setError('')}}><RotateCcw size={14}/></button></div>
  <form onSubmit={event=>{event.preventDefault();void ask()}}><label className="chopperQuickInputLabel" htmlFor="chopper-quick-question">Ask Chopper</label><div><textarea ref={input} id="chopper-quick-question" rows={2} maxLength={4000} value={question} placeholder="Ask about this action or window…" onChange={event=>setQuestion(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();void ask()}}}/><button className="btn primary" disabled={busy||!question.trim()} aria-label="Send question"><Send size={18}/></button></div><small>Replies explain the supplied context. Chopper does not run PLC actions from this window.</small></form>
 </section>,document.body)}</>;
}
