import {useAccount} from '../account/AuthProvider';
import {visibleModules} from '../../shared/workspaceModules';
import {assistantTasks,startAssistantTask,suggestedTask,type AssistantTask} from './taskActions';
import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Bot,Expand,RotateCcw,Send,X} from 'lucide-react';
import {requestChopper} from './chopperRequest';
import {ChopperReply} from './ChopperReply';
import {SpeechInput} from './SpeechInput';
import {FEATURES} from '../../shared/features';
import {useProjectIntelligence,ContextUsage} from './ProjectIntelligence';
import './chopper-quick-help.css';
import {openDashboardBuilder,isWorkHubDashboardRequest} from '../workhub/dashboards/bridge';

type WindowContext={page:string;label:string;projectName?:string;projectPath?:string;details?:Record<string,unknown>;findings?:any[];counts?:Record<string,number>};
type Message={role:'user'|'assistant';text:string;scope:string;source?:string;evidence?:any[];contextUsage?:any;retrieval?:any;taskId?:string;taskPrompt?:string};
export function ChopperQuickHelp({context,onOpenChat,placement='floating'}:{context:WindowContext;onOpenChat:()=>void;placement?:'floating'|'top'}){
 const {user}=useAccount();const modules=visibleModules(user);
 const [mode,setMode]=useState('tasks'),[taskSearch,setTaskSearch]=useState('');
 const [open,setOpen]=useState(false),[question,setQuestion]=useState(''),[messages,setMessages]=useState<Message[]>([]);
 const [busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[error,setError]=useState('');
 const intelligence=useProjectIntelligence(open?context.projectPath||'':'');
 const launcher=useRef<HTMLButtonElement>(null),input=useRef<HTMLTextAreaElement>(null),scroll=useRef<HTMLDivElement>(null),controller=useRef<AbortController|null>(null),lock=useRef(false);
 const close=()=>{setOpen(false);launcher.current?.focus()};
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{if(!open)return;input.current?.focus();const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!(event.target instanceof Element&&event.target.closest('dialog[open]'))){event.preventDefault();close()}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[open]);
 useEffect(()=>{if(scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight},[messages,progress,open]);
 function start(task:AssistantTask,prompt=question){try{if(startAssistantTask(task,modules,prompt)){setMessages(current=>[...current,{role:'assistant',scope:context.label,text:'Continue with '+task.name+' in its workspace. Complete the draft or select inputs there.',source:'workspace-action'}]);close();}}catch(e){setError((e as Error).message);}}
 async function ask(text=question,guideOnly=false){
  text=text.trim();if(!text||lock.current)return;setMode('chat');lock.current=true;setBusy(true);setError('');setQuestion('');setProgress('Preparing help…');
  const scope=context.label,abort=new AbortController();controller.current=abort;
  const history=messages.slice(-6).map(message=>({role:message.role,content:`[${message.scope}] ${message.text.slice(0,1600)}`}));
  setMessages(current=>[...current.slice(-29),{role:'user',text,scope}]);
  try{
   const task=!guideOnly?suggestedTask(text):undefined;if(task){setMode('chat');setMessages(current=>[...current,{role:'assistant',scope,text:task.description+' Use the action below to start.',taskId:task.id,taskPrompt:text}]);return;}
   if(!guideOnly&&isWorkHubDashboardRequest(text)){
    openDashboardBuilder(text);setMessages(current=>[...current,{role:'assistant',scope,text:'I opened My Dashboard in WorkHub. Review the proposed widget and layout settings there, apply them to the editor, then save when ready.',source:'dashboard-builder'}]);close();return;
   }
   const status=await requestChopper({task:guideOnly?'Window assistant':'Chopper conversation',guideOnly,question:text.slice(0,4000),history,context:{offlineOnly:true,availableTasks:assistantTasks.filter(t=>modules.includes(t.module)).map(t=>({id:t.id,name:t.name,description:t.description})),taskExecutionPolicy:'Answers are advice. Do not claim files were created, saved, approved or PLC actions executed without an actual tool result.',intelligenceProjectId:intelligence.state?.projectId,applicationFeatures:FEATURES,currentWindow:{page:context.page,details:context.details,findings:context.findings},projectName:context.projectName,counts:context.counts}},abort.signal,value=>setProgress(value.stage||'Preparing answer…'));
   if(abort.signal.aborted)return;const data=status.result;
   setMessages(current=>[...current,{role:'assistant',scope,text:data.answer||'Open full Chat for a detailed project analysis.',source:data.source,evidence:[...(data.evidence||[]),...(data.helpEvidence||[])],contextUsage:data.contextUsage,retrieval:data.retrieval}]);
  }catch(reason){if(!abort.signal.aborted)setError(reason instanceof Error?reason.message:'Chopper is unavailable.')}
  finally{if(!abort.signal.aborted){setBusy(false);setProgress('');lock.current=false}}
 }
 return <><button type="button" ref={launcher} className={'btn chopperQuickLauncher '+(open?'selected':'')} title="Ask Chopper or start a task" aria-label="Open Chopper chat" aria-haspopup="dialog" aria-expanded={open} aria-controls="chopper-quick-help" onClick={()=>open?close():setOpen(true)}><Bot size={20}/><span>{placement==='top'?'Chopper / Start a task':'Chopper'}</span>{busy&&<i className="chopperBusyDot"/>}</button>{open&&createPortal(<section id="chopper-quick-help" role="dialog" aria-modal="false" aria-labelledby="chopper-quick-title" className={'chopperQuickPanel'+(placement==='top'?' topCentered':'')}>
  <header><span className="chopperQuickAvatar"><Bot size={22}/></span><div><h2 id="chopper-quick-title">Chopper</h2><p>Create, compare, analyze and get help</p></div><button className="btn" title="Open full Chat" aria-label="Open full Chopper Chat" onClick={()=>{close();onOpenChat()}}><Expand size={16}/></button><button className="btn" aria-label="Close Chopper chat" onClick={close}><X size={18}/></button></header>
  <div className="chopperQuickContext"><span>Current window</span><b>{context.label}</b>{context.details?.target!=null&&<small>{String(context.details.target)}</small>}</div>
  <div className="chopperTaskTabs"><button type="button" className="btn" aria-pressed={mode==='tasks'} onClick={()=>setMode('tasks')}>Start a task</button><button type="button" className="btn" aria-pressed={mode==='chat'} onClick={()=>setMode('chat')}>Ask Chopper</button></div>
  {mode==='tasks'&&<div className="chopperTaskCatalog"><label>Find a task<input aria-label="Find Chopper task" value={taskSearch} onChange={e=>setTaskSearch(e.target.value)} placeholder="FRD, flowchart, compare, validation?"/></label><div>{assistantTasks.filter(task=>modules.includes(task.module)&&(!user.isDemo||task.module!=='workhub')&&(task.name+' '+task.description+' '+task.category).toLowerCase().includes(taskSearch.toLowerCase())).map(task=><button type="button" key={task.id} onClick={()=>start(task)}><small>{task.category}</small><strong>{task.name}</strong><span>{task.description}</span></button>)}</div><small>Tasks open existing editors and tools. Save, submit and review using their normal controls.</small></div>}
  <div hidden={mode!=='chat'} className="chopperQuickMessages" ref={scroll} role="log" aria-label="Chopper conversation" aria-live="polite">
   {!messages.length&&<div className="chopperQuickWelcome"><Bot size={28}/><h3>How can I help?</h3><p>Ask about this page or your engineering work.</p></div>}
   {messages.map((message,index)=><article key={index} className={'chopperQuickMessage '+message.role}><small>{message.role==='assistant'?'Chopper':'You'} · {message.scope}</small><ChopperReply text={message.text}/>{message.taskId&&assistantTasks.find(t=>t.id===message.taskId)&&<button type="button" className="btn primary" onClick={()=>start(assistantTasks.find(t=>t.id===message.taskId)!,message.taskPrompt)}>Start this task</button>}<ContextUsage usage={message.contextUsage} retrieval={message.retrieval}/>{message.evidence?.length? <details><summary>View evidence ({message.evidence.length})</summary>{message.evidence.map((item,i)=><div key={i}><b>{item.sourceId?`[${item.sourceId}] `:''}{item.file}{item.line?`:${item.line}`:''}</b><pre>{item.excerpt}</pre></div>)}</details>:null}{message.source==='local-window-guide'&&<small>Workflow guide · deterministic results remain in the workspace.</small>}</article>)}
   {busy&&<p className="chopperQuickProgress" role="status">{progress}</p>}
  </div>
  {error&&<p className="chopperQuickError" role="alert">{error}</p>}
  <div className="chopperQuickSuggestions"><button className="btn" disabled={busy} onClick={()=>void ask('Explain how to use this window, step by step.',true)}>Window guide</button><button className="btn" disabled={busy} onClick={()=>void ask('Explain the current reported findings and the next action. Do not infer a pass or failure without evidence.')}>Explain findings</button><button className="btn" disabled={busy||!messages.length} title="Clear this help conversation" aria-label="Clear Chopper help conversation" onClick={()=>{setMessages([]);setError('')}}><RotateCcw size={14}/></button></div>
  <form onSubmit={event=>{event.preventDefault();void ask()}}><label className="chopperQuickInputLabel" htmlFor="chopper-quick-question">Ask Chopper</label><div><textarea ref={input} id="chopper-quick-question" rows={2} maxLength={4000} value={question} placeholder="Ask about this action or window…" onChange={event=>setQuestion(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();void ask()}}}/><SpeechInput disabled={busy} maxLength={4000-question.length-(question.trim()?1:0)} onText={text=>{setQuestion(current=>current.trim()?current+'\n'+text:text);setError('');requestAnimationFrame(()=>input.current?.focus());}}/><button className="btn primary" disabled={busy||!question.trim()} aria-label="Send question"><Send size={18}/></button></div><small>Ask for a task or an evidence-based answer. Review generated drafts and results in the workspace.</small></form>
 </section>,document.body)}</>;
}
