import {useAccount} from '../account/AuthProvider';
import {visibleModules} from '../../shared/workspaceModules';
import {assistantTasks,startAssistantTask,suggestedTask,type AssistantTask} from './taskActions';
import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Bot,Expand,RotateCcw,Send,X,Paperclip,FolderUp,FileUp,Maximize2,Minimize2,Minus,Plus,Sparkles} from 'lucide-react';
import {requestChopper} from './chopperRequest';
import {ChopperReply} from './ChopperReply';
import {SpeechInput} from './SpeechInput';
import {FEATURES} from '../../shared/features';
import {useProjectIntelligence,ContextUsage} from './ProjectIntelligence';
import {ChopperActionCard} from './ChopperActionCard';
import {stageBrowserProject} from '../validation/api';
import {readChatAttachment,type ChatAttachment} from './chatFiles';
import {navigateRoute} from '../../shared/navigation';
import './chopper-quick-help.css';
import {openDashboardBuilder,isWorkHubDashboardRequest} from '../workhub/dashboards/bridge';

type WindowContext={page:string;label:string;projectName?:string;projectPath?:string;details?:Record<string,unknown>;findings?:any[];counts?:Record<string,number>};
type Message={role:'user'|'assistant';text:string;scope:string;source?:string;evidence?:any[];contextUsage?:any;retrieval?:any;taskId?:string;taskPrompt?:string;actionCard?:any};

export function ChopperQuickHelp({context,onOpenChat,placement='floating'}:{context:WindowContext;onOpenChat:()=>void;placement?:'floating'|'top'}){
 const {user}=useAccount();const modules=visibleModules(user);
 const [mode,setMode]=useState('tasks'),[taskSearch,setTaskSearch]=useState('');
 const [open,setOpen]=useState(false),[question,setQuestion]=useState(''),[messages,setMessages]=useState<Message[]>([]);
 const [busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[error,setError]=useState('');
 const [actionState,setActionState]=useState<any>(null);
 const [attachments,setAttachments]=useState<ChatAttachment[]>([]);
 const [attachmentMenu,setAttachmentMenu]=useState(false);
 const [maximized,setMaximized]=useState(false);
 const [minimized,setMinimized]=useState(false);

 const projectPicker=useRef<HTMLInputElement>(null);
 const filePicker=useRef<HTMLInputElement>(null);
 const intelligence=useProjectIntelligence(open?context.projectPath||'':'');
 const launcher=useRef<HTMLButtonElement>(null),input=useRef<HTMLTextAreaElement>(null),scroll=useRef<HTMLDivElement>(null),controller=useRef<AbortController|null>(null),lock=useRef(false);
 const close=()=>{setOpen(false);setMinimized(false);launcher.current?.focus()};
 const newChat=()=>{setMessages([]);setError('');setAttachments([]);setActionState(null);setQuestion('');setProgress('');};

 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{const openExternal=()=>{setOpen(true);setMinimized(false)};window.addEventListener('usopp-open-chopper',openExternal);return()=>window.removeEventListener('usopp-open-chopper',openExternal)},[]);
useEffect(()=>{if(!open)return;input.current?.focus();const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!(event.target instanceof Element&&event.target.closest('dialog[open]'))){event.preventDefault();close()}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[open]);
 useEffect(()=>{if(scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight},[messages,progress,open]);

 async function attachProject(files:File[]){
  if(!files.length||lock.current)return;
  lock.current=true;setBusy(true);setProgress('Uploading project folder…');setError('');
  try{
   const name=files[0].webkitRelativePath?.split('/')[0]||'Uploaded project';
   const staged=await stageBrowserProject({projectFiles:files,projectName:name});
   const item:ChatAttachment={id:crypto.getRandomValues(new Uint32Array(2)).join('-'),name,kind:'project',text:'',projectPath:staged.projectPath,projectName:staged.projectName,notice:`${staged.uploadedFiles} files`};
   setAttachments(curr=>[...curr,item]);
   setMessages(curr=>[...curr,{role:'assistant',scope:context.label,text:`Project folder uploaded: **${name}** (${staged.uploadedFiles} files). You can now ask to validate, compare, or analyze it.`}]);
   setMode('chat');
  }catch(e){setError((e as Error).message);}
  finally{lock.current=false;setBusy(false);setProgress('');}
 }

 async function attachFiles(files:File[]){
  if(!files.length||lock.current)return;
  lock.current=true;setBusy(true);setProgress('Reading files…');setError('');
  try{
   const added:ChatAttachment[]=[];
   for(const file of files){
    const item=await readChatAttachment(file);
    added.push(item);
   }
   setAttachments(curr=>[...curr,...added]);
   setMessages(curr=>[...curr,{role:'assistant',scope:context.label,text:`Attached ${added.length} file(s): ${added.map(a=>a.name).join(', ')}.`}]);
   setMode('chat');
  }catch(e){setError((e as Error).message);}
  finally{lock.current=false;setBusy(false);setProgress('');}
 }

 function start(task:AssistantTask,prompt=question){
  setMode('chat');
  const taskMap:Record<string,string>={
   frd: 'Create an new project and FRD',
   mom: 'Create meeting minutes and MOM',
   test: 'Create validation report and test cases',
   fat: 'Create FAT document and quality report',
   closure: 'Create project closure report',
   flowchart: 'Create flowchart and infographic',
   mindmap: 'Create mind map and subsystem breakdown',
   project: 'Create new project pack',
   compare: 'Compare two projects in MatchView',
   validation: 'Validate project in ByteMap',
  };
  const command = taskMap[task.id] || `Create ${task.name}`;
  void ask(command);
 }

 async function ask(text=question,guideOnly=false){
  text=text.trim();if(!text||lock.current)return;setMode('chat');lock.current=true;setBusy(true);setError('');setQuestion('');setProgress('Preparing help…');
  const scope=context.label,abort=new AbortController();controller.current=abort;
  const history=messages.slice(-6).map(message=>({role:message.role,content:`[${message.scope}] ${message.text.slice(0,1600)}`}));
  setMessages(current=>[...current.slice(-29),{role:'user',text,scope}]);
  try{
   if(!guideOnly&&!actionState&&isWorkHubDashboardRequest(text)){
    openDashboardBuilder(text);setMessages(current=>[...current,{role:'assistant',scope,text:'I opened My Dashboard in WorkHub. Review the proposed widget and layout settings there, apply them to the editor, then save when ready.',source:'dashboard-builder'}]);close();return;
   }
   const documents=attachments.map(a=>({name:a.name,kind:a.kind,projectPath:a.projectPath,projectName:a.projectName,text:a.text?.slice(0,10000)||''}));
   const status=await requestChopper({
    task:guideOnly?'Window assistant':'Chopper conversation',
    guideOnly,
    _actionState:actionState,
    attachments:documents,
    question:text.slice(0,4000),
    history,
    context:{
     offlineOnly:true,
     availableTasks:assistantTasks.filter(t=>modules.includes(t.module)).map(t=>({id:t.id,name:t.name,description:t.description})),
     taskExecutionPolicy:'Execute requested actions using Chopper Command Layer cards.',
     intelligenceProjectId:intelligence.state?.projectId,
     applicationFeatures:FEATURES,
     attachments:documents,
     projectPath:attachments.find(a=>a.kind==='project')?.projectPath||context.projectPath,
     projectName:attachments.find(a=>a.kind==='project')?.projectName||context.projectName,
     currentWindow:{page:context.page,details:context.details,findings:context.findings},
     counts:context.counts
    }
   },abort.signal,value=>setProgress(value.stage||'Preparing answer…'));

   if(abort.signal.aborted)return;
   const data=status.result;
   const actionCard=data?.type?.startsWith('action-')?data:undefined;
   if(data?._actionState)setActionState(data._actionState);
   else if(data?.type==='action-summary'||data?.type==='action-cancelled'||data?.type==='action-error'){
    setActionState(null);
    if(data?.type==='action-summary'){
     if(data.actionId==='bytecheck')window.dispatchEvent(new CustomEvent('usopp-adopt-validation',{detail:data}));
     else if(data.actionId==='matchview')window.dispatchEvent(new CustomEvent('usopp-adopt-compare',{detail:data}));
    }
   }

   setMessages(current=>[...current,{
    role:'assistant',
    scope,
    text:data.answer||'Open full Chat for a detailed project analysis.',
    source:data.source,
    actionCard,
    evidence:[...(data.evidence||[]),...(data.helpEvidence||[])],
    contextUsage:data.contextUsage,
    retrieval:data.retrieval
   }]);
  }catch(reason){if(!abort.signal.aborted)setError(reason instanceof Error?reason.message:'Chopper is unavailable.')}
  finally{if(!abort.signal.aborted){setBusy(false);setProgress('');lock.current=false}}
 }

 return <><button type="button" ref={launcher} className={'btn chopperQuickLauncher '+(open?'selected':'')} title="Ask Chopper or start a task" aria-label="Open Chopper chat" aria-haspopup="dialog" aria-expanded={open} aria-controls="chopper-quick-help" onClick={()=>open?close():setOpen(true)}><Bot size={20}/><span>{placement==='top'?'Chopper / Start a task':'Chopper'}</span>{busy&&<i className="chopperBusyDot"/>}</button>{open&&createPortal(minimized ? (
   <button type="button" className="chopperHexagonWidget" onClick={()=>setMinimized(false)} title="Chopper is minimized — click to restore" aria-label="Restore Chopper">
    <div className="chopperHexagonInner">
     <Bot size={24}/>
     {busy&&<span className="chopperHexBusyDot"/>}
    </div>
    <span className="chopperHexBadge">Chopper</span>
   </button>
  ) : (<section id="chopper-quick-help" role="dialog" aria-modal="false" aria-labelledby="chopper-quick-title" className={'chopperQuickPanel'+(placement==='top'?' topCentered':'')+(maximized?' isMaximized':'')}>
   <header>
    <span className="chopperQuickAvatar"><Bot size={22}/></span>
    <div><h2 id="chopper-quick-title">Chopper</h2><p>Create, compare, analyze and get help</p></div>
    <div className="chopperHeaderActions">
     <button type="button" className="btn chopperNewChatBtn" title="Start a fresh conversation" aria-label="New chat" onClick={newChat}><Plus size={14}/><span>New</span></button>
     <button type="button" className="btn" title="Minimize panel" aria-label="Minimize" onClick={()=>setMinimized(true)}><Minus size={15}/></button>
     <button type="button" className="btn" title={maximized?'Restore size':'Maximize window'} aria-label={maximized?'Restore':'Maximize'} onClick={()=>setMaximized(m=>!m)}>{maximized?<Minimize2 size={15}/>:<Maximize2 size={15}/>}</button>
     <button type="button" className="btn" title="Open full Chat" aria-label="Open full Chopper Chat" onClick={()=>{close();onOpenChat()}}><Expand size={15}/></button>
     <button type="button" className="btn" aria-label="Close Chopper chat" onClick={close}><X size={17}/></button>
    </div>
   </header>
   <>
  <div className="chopperQuickContext"><span>Current window</span><b>{context.label}</b>{context.details?.target!=null&&<small>{String(context.details.target)}</small>}</div>
  <div className="chopperTaskTabs"><button type="button" className="btn" aria-pressed={mode==='tasks'} onClick={()=>setMode('tasks')}>Start a task</button><button type="button" className="btn" aria-pressed={mode==='chat'} onClick={()=>setMode('chat')}>Ask Chopper</button></div>
  {mode==='tasks'&&<div className="chopperTaskCatalog">
   <div className="chopperQuickUploadShortcuts">
    <button type="button" className="btn actionUploadDirectBtn" onClick={()=>projectPicker.current?.click()}><FolderUp size={14}/> Upload project folder</button>
    <button type="button" className="btn actionUploadDirectBtn" onClick={()=>filePicker.current?.click()}><FileUp size={14}/> Upload files / workbook</button>
   </div>
   <label>Find a task<input aria-label="Find Chopper task" value={taskSearch} onChange={e=>setTaskSearch(e.target.value)} placeholder="FRD, flowchart, compare, validation?"/></label>
   <div>{assistantTasks.filter(task=>modules.includes(task.module)&&(!user.isDemo||task.module!=='workhub')&&(task.name+' '+task.description+' '+task.category).toLowerCase().includes(taskSearch.toLowerCase())).map(task=><button type="button" key={task.id} onClick={()=>start(task)}><small>{task.category}</small><strong>{task.name}</strong><span>{task.description}</span></button>)}</div>
   <small>Select a task or upload files. Chopper will execute the action directly in chat.</small>
  </div>}
  <div hidden={mode!=='chat'} className="chopperQuickMessages" ref={scroll} role="log" aria-label="Chopper conversation" aria-live="polite">
   {!messages.length&&<div className="chopperQuickWelcome"><Bot size={28}/><h3>How can I help?</h3><p>Upload a project folder or files, ask to validate or compare, or create projects and documents.</p></div>}
   {messages.map((message,index)=><article key={index} className={'chopperQuickMessage '+message.role}><small>{message.role==='assistant'?'Chopper':'You'} · {message.scope}</small>{message.actionCard?<ChopperActionCard card={message.actionCard} onAnswer={ans=>void ask(ans)} onOpenFeature={feature=>{close();const target=feature==='workhub'?'home':feature;if(target&&target!=='chatbot'){navigateRoute({page:target});}else{onOpenChat();}}} onUploadFolder={()=>projectPicker.current?.click()} onUploadFile={()=>filePicker.current?.click()} disabled={busy}/>:<ChopperReply text={message.text}/>}{message.taskId&&assistantTasks.find(t=>t.id===message.taskId)&&<button type="button" className="btn primary" onClick={()=>start(assistantTasks.find(t=>t.id===message.taskId)!,message.taskPrompt)}>Start this task</button>}<ContextUsage usage={message.contextUsage} retrieval={message.retrieval}/>{message.evidence?.length? <details><summary>View evidence ({message.evidence.length})</summary>{message.evidence.map((item,i)=><div key={i}><b>{item.sourceId?`[${item.sourceId}] `:''}{item.file}{item.line?`:${item.line}`:''}</b><pre>{item.excerpt}</pre></div>)}</details>:null}{message.source==='local-window-guide'&&<small>Workflow guide · deterministic results remain in the workspace.</small>}</article>)}
   {busy&&(
    <div className="chopperBusyAnimationBox" role="status">
     <div className="chopperCubeWrapper">
      <div className="chopperCube">
       <div className="cubeFace cubeFront"/>
       <div className="cubeFace cubeBack"/>
       <div className="cubeFace cubeRight"/>
       <div className="cubeFace cubeLeft"/>
       <div className="cubeFace cubeTop"/>
       <div className="cubeFace cubeBottom"/>
      </div>
      <div className="chopperRobotPulse">
       <Bot size={18} className="chopperMascotFlip"/>
      </div>
     </div>
     <div className="chopperBusyText">
      <strong>Chopper is executing…</strong>
      <p>{progress||'Analyzing projects, checking logic and generating cards…'}</p>
     </div>
    </div>
   )}
  </div>
  {error&&<p className="chopperQuickError" role="alert">{error}</p>}
  {attachments.length>0&&<div className="chopperQuickAttachments">{attachments.map(att=><span key={att.id} className="quickAttachChip"><Paperclip size={12}/>{att.name}<button type="button" onClick={()=>setAttachments(curr=>curr.filter(a=>a.id!==att.id))}><X size={12}/></button></span>)}</div>}
  <div className="chopperQuickSuggestions"><button className="btn" disabled={busy} onClick={()=>void ask('Explain how to use this window, step by step.',true)}>Window guide</button><button className="btn" disabled={busy} onClick={()=>void ask('Explain the current reported findings and the next action. Do not infer a pass or failure without evidence.')}>Explain findings</button><button className="btn" disabled={busy||!messages.length} title="Clear this help conversation" aria-label="Clear Chopper help conversation" onClick={newChat}><RotateCcw size={14}/></button></div>
  <form onSubmit={event=>{event.preventDefault();void ask()}}><label className="chopperQuickInputLabel" htmlFor="chopper-quick-question">Ask Chopper</label>
   <input type="file" multiple hidden ref={projectPicker} {...({webkitdirectory:'',directory:''} as any)} onChange={e=>{const f=Array.from(e.target.files||[]);e.target.value='';void attachProject(f);}}/>
   <input type="file" multiple hidden ref={filePicker} onChange={e=>{const f=Array.from(e.target.files||[]);e.target.value='';void attachFiles(f);}}/>
   <div>
    <button type="button" className="btn chatAttachButton" title="Upload project folder or files" aria-label="Upload files or folder" disabled={busy} onClick={()=>setAttachmentMenu(v=>!v)}><Paperclip size={16}/></button>
    {attachmentMenu&&<div className="chopperQuickAttachMenu"><button type="button" className="btn" onClick={()=>{setAttachmentMenu(false);projectPicker.current?.click();}}><FolderUp size={14}/> Upload project folder</button><button type="button" className="btn" onClick={()=>{setAttachmentMenu(false);filePicker.current?.click();}}><FileUp size={14}/> Upload files / workbooks</button></div>}
    <textarea ref={input} id="chopper-quick-question" rows={2} maxLength={4000} value={question} placeholder="Ask Chopper to execute a task, validate, or compare…" onChange={event=>setQuestion(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();void ask()}}}/>
    <SpeechInput disabled={busy} maxLength={4000-question.length-(question.trim()?1:0)} onText={text=>{setQuestion(current=>current.trim()?current+'\n'+text:text);setError('');requestAnimationFrame(()=>input.current?.focus());}}/>
    <button className="btn primary" disabled={busy||(!question.trim()&&!attachments.length)} aria-label="Send question"><Send size={18}/></button>
   </div>
   <small>Ask for a task or upload files. Chopper will execute the action and show the summary card.</small>
  </form>
   </>
  </section>),document.body)}</>;
}
