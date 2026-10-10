import {useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowUpRight,Bot,BrainCircuit,Cpu,Paperclip,Plus,Search,Send,Sparkles,X} from 'lucide-react';
import {normalizeResult} from '../validation/normalizeResult';
import {ValidationSourceEditor,type SourceSelection} from '../validation/ValidationSourceEditor';
import {FEATURES} from '../../shared/features';
import {readChatAttachment,looksLikeLog,copyChatText,type ChatAttachment} from './chatFiles';
import {ChatLogReply,type ChatLogData} from './ChatLogReply';
import {decodeCollectedLog} from './logDecoder';
import './chopper-chat.css';
import {useAccount} from '../account/AuthProvider';
import {stageBrowserProject} from '../validation/api';
import {requestChopper} from './chopperRequest';
import {CHAT_PROMPTS} from './chatPrompts';

type Evidence={file:string;line?:number;excerpt?:string};
type HelpEvidence=Evidence&{id:string;sourceId:string;title:string;helpSet:string;truncated?:boolean};
type Choice={label:string;action:string};
type ChatMessage={role:'user'|'assist';text:string;source?:string;evidence?:Evidence[];helpEvidence?:HelpEvidence[];logs?:ChatLogData[];choices?:Choice[];elapsedSeconds?:number;review?:boolean};
const GREETING='Hi, I am Chopper, your uSOPp assistant. Ask about ByteMap, MetaWorks, DataInspect, MatchView, LogicScan or KnowHub. Attach a log and its metadata, or paste the log here, and I will show the decoded values in this chat. A selected project is optional.';
const SHORTCUTS=[['decode','Log decoder'],['home','WorkHub'],['validation','ByteMap'],['metadata','MetaWorks'],['plc','DataInspect'],['compare','MatchView'],['rules','LogicScan'],['results','ResultView'],['learning','KnowHub'],['settings','Settings / AI models']] as const;

export function Chatbot({result,comparisonResult,projectPath,projectName,ruleResults,onSourceSaved,onOpenFeature}:{result:any;comparisonResult?:any;projectPath:string;projectName:string;ruleResults:any;onSourceSaved?:(path:string,name:string)=>void;onOpenFeature?:(feature:string)=>void}) {
 const {user}=useAccount();const admin=user.role==='admin';
 const [projectId,setProjectId]=useState(''),[attachmentMenu,setAttachmentMenu]=useState(false);
 const projectPicker=useRef<HTMLInputElement>(null);
 const [question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[reading,setReading]=useState(false),[learningCount,setLearningCount]=useState(0);
 const [messages,setMessages]=useState<ChatMessage[]>([{role:'assist',text:GREETING}]),[attachments,setAttachments]=useState<ChatAttachment[]>([]);
 const [modelLabel,setModelLabel]=useState('Checking connection...'),[source,setSource]=useState<SourceSelection|null>(null),[sourceNotice,setSourceNotice]=useState(''),[copyNotice,setCopyNotice]=useState('');
 const picker=useRef<HTMLInputElement>(null),messageEnd=useRef<HTMLDivElement>(null),composer=useRef<HTMLTextAreaElement>(null),generation=useRef(0),controller=useRef<AbortController|null>(null);
 const lock=useRef(false),pendingDecode=useRef(false);
 const projects=attachments.filter(a=>a.kind==='project');
 const attachedProject=projects.find(a=>a.id===projectId);
 const effectiveProjectPath=attachedProject?.projectPath||projectPath;
 const effectiveProjectName=attachedProject?.projectName||projectName;
 const sessionId=attachedProject?undefined:result?.sessionId||ruleResults?.sessionId;
 const [progress,setProgress]=useState<any>(null);
 const [comparisonFocus,setComparisonFocus]=useState(false);
 const refreshModel=async()=>{
  try {
   const response=await fetch('/api/assist/model');const data=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(data.detail||'Restart the updated application.');
   if(!['local','embedded','ollama','api'].includes(data.provider))throw new Error('Restart the updated application to load Chopper settings.');
   setModelLabel(data.provider==='local'?'Local tools':`${data.provider==='embedded'?'Chopper local model':data.provider==='ollama'?'Ollama':'API model'} · ${data.model||'No model selected'}`);
  }catch(error){setModelLabel(`Unavailable: ${error instanceof Error?error.message:'check the server connection'}`);}
 };
 useEffect(()=>{if(admin)void refreshModel();fetch('/api/rules/learning/model').then(r=>r.ok?r.json():{recordCount:0}).then(data=>setLearningCount(Number(data.recordCount||0))).catch(()=>{});return()=>{generation.current++;controller.current?.abort();}},[]);
 useEffect(()=>{if(messages.length>1||busy||reading)messageEnd.current?.scrollIntoView({block:'nearest'});},[messages,busy,reading]);
 const reply=(text:string,choices?:Choice[])=>setMessages(current=>[...current,{role:'assist',text,choices}]);
 const newChat=()=>{generation.current++;controller.current?.abort();lock.current=false;pendingDecode.current=false;setBusy(false);setComparisonFocus(false);setProgress(null);setReading(false);setMessages([{role:'assist',text:GREETING}]);setQuestion('');setAttachments([]);setProjectId('');setAttachmentMenu(false);setCopyNotice('');};

 async function attachProject(files:File[]) {
  if(!files.length||lock.current)return;
  if(attachments.length>=10){reply('Remove an attachment before uploading another project.');return;}
  lock.current=true;setReading(true);setProgress({stage:'Uploading project files',current:0,total:files.length});const turn=generation.current;
  try {
   const name=files[0].webkitRelativePath.split('/')[0]||'Uploaded project';
   const staged=await stageBrowserProject({projectFiles:files,projectName:name},(current,total)=>{if(turn===generation.current)setProgress({stage:'Uploading project files',current,total})});
   if(turn!==generation.current)return;
   const item:ChatAttachment={id:crypto.getRandomValues(new Uint32Array(2)).join('-'),name,kind:'project',text:'',projectPath:staged.projectPath,projectName:staged.projectName,notice:`${staged.uploadedFiles} project files uploaded`};
   setAttachments(current=>[...current,item]);setProjectId(item.id);reply(`${name}: ${item.notice}. This project is now selected for your questions.`,[{label:'Explain machine functions',action:'understand'}]);
  }catch(error){if(turn===generation.current)reply(error instanceof Error?error.message:'Project upload failed.');}
  finally{if(turn===generation.current){lock.current=false;setReading(false);setProgress(null);}}
 }

 async function attach(files:File[]) {
  if(!files.length||lock.current)return;
  if(files.length+attachments.length>10){reply('Attach up to 10 files per chat. Remove an attachment or start a new chat to add more.');return;}
  lock.current=true;setReading(true);setProgress({stage:'Reading attachments'});const turn=generation.current;
  const added:ChatAttachment[]=[],notices:string[]=[];
  try {
   for(const file of files) {
    try {setProgress({stage:/\.zip$/i.test(file.name)?'Uploading project ZIP':'Reading attachment',name:file.name});const item=await readChatAttachment(file);added.push(item);notices.push(`${item.name}: ${item.kind==='metadata'?'metadata workbook':item.kind==='log'?'PLC log':item.kind==='project'?'project uploaded':item.kind==='unsupported'?'not readable':'readable document'}${item.notice?`\n${item.notice}`:''}`);}
    catch(error){notices.push(error instanceof Error?error.message:'Attachment could not be read.');}
   }
   if(turn!==generation.current)return;
   setAttachments(current=>[...current,...added]);const uploaded=added.filter(a=>a.kind==='project');if(uploaded.length)setProjectId(uploaded[uploaded.length-1].id);pendingDecode.current=added.some(a=>a.kind==='log'||a.kind==='metadata')||pendingDecode.current;
   reply(notices.join('\n\n'),added.some(a=>a.kind==='log'||a.kind==='metadata')?[{label:'Decode attached log',action:'decode'}]:undefined);
  }finally{if(turn===generation.current){lock.current=false;setReading(false);setProgress(null);}}
 }

 function showLogReply(files:ChatAttachment[],metadataId?:string) {
  const logs=files.filter(a=>a.kind==='log'),workbooks=files.filter(a=>a.kind==='metadata');
  if(!logs.length){reply('Attach the collected PLC log, or paste its complete lines here. Include the logged Group Code and decimal response buffer.',[{label:'Attach log',action:'attach'}]);return;}
  if(metadataId&&metadataId!=='frames-only'&&!workbooks.some(m=>m.id===metadataId)){reply('That workbook was removed. Attach it again or choose Log decoder to select the current metadata.',[{label:'Attach metadata',action:'attach'},{label:'Choose metadata',action:'decode'}]);return;}
  if(workbooks.length>1&&!metadataId){reply('Which metadata workbook matches these logs?',workbooks.map(m=>({label:m.name,action:`metadata:${m.id}`})));return;}
  const workbook=metadataId==='frames-only'?undefined:workbooks.find(m=>m.id===metadataId)||workbooks[0];
  if(!workbook&&metadataId!=='frames-only') {
   reply('I have the log. Attach its metadata XLSX / CSV to map bytes to parameter names and values. I can also check request failures without metadata.',[{label:'Attach metadata',action:'attach'},{label:'Check requests only',action:'frames-only'}]);return;
  }
  const data=logs.map(log=>({text:log.text,logName:log.name,metadata:workbook?.metadata||[],metadataName:workbook?.name||''}));
  setMessages(current=>[...current,{role:'assist',text:'Here are the recorded PLC readings. Choose a Group Code and capture time, then copy the table or switch to simple text.',source:'Local log decoder',logs:data}]);pendingDecode.current=false;
 }

 async function ask(textOverride?:string,selectedCapture?:Record<string,unknown>,focusOverride?:boolean) {
  if(lock.current)return;
  const text=(textOverride??question).trim()||(attachments.length?'Review my attachments.':'');if(!text)return;
  let files=attachments;
  setQuestion('');setCopyNotice('');setMessages(current=>[...current,{role:'user',text:looksLikeLog(text)?`Decode pasted PLC log (${text.length.toLocaleString()} characters).`:text}]);
  if(text.length>20*1024*1024){reply('Paste a log smaller than 20 MB.');return;}
  if(looksLikeLog(text)) {
   files=[...attachments.filter(a=>a.id!=='pasted-log'),{id:'pasted-log',name:'Pasted log',kind:'log',text}];setAttachments(files);pendingDecode.current=true;
  }
  if(!selectedCapture&&files.some(a=>a.kind==='log')&&(pendingDecode.current||/\b(decode|raw|table|log decoder)\b/i.test(text))) {showLogReply(files);return;}
  if(/\b(decode|log)\b/i.test(text)&&!files.some(a=>a.kind==='log')&&!files.some(a=>a.kind==='document')){showLogReply(files);return;}
  lock.current=true;setBusy(true);setProgress({stage:'Preparing project context',elapsedSeconds:0});const turn=generation.current;const abort=new AbortController();controller.current=abort;
  try {
   const normalized=result?normalizeResult(result):null;
   const latestLog=[...messages].reverse().find(m=>m.logs)?.logs;
   const requestedGroup=text.match(/\b(?:GC|group\s*(?:code)?)\s*(\d+)/i)?.[1];
   const captures=selectedCapture?[selectedCapture]:latestLog?.flatMap(log=>decodeCollectedLog(log.text,log.metadata).captures.filter(c=>!requestedGroup||c.groupCode===Number(requestedGroup)).map(c=>({groupCode:c.groupCode,asset:c.asset,timestamp:c.timestamp,status:c.status,resultCode:c.resultCode,issues:c.issues,logErrors:c.logErrors,payloadLength:c.payloadLength,expectedLength:c.expectedLength,values:c.values.slice(0,80).map(v=>({tagCode:v.tagCode,parameter:v.parameter,offset:v.offset,dataType:v.dataType,value:v.formattedValue,qualityIssue:v.qualityIssue}))}))).slice(0,40);
   let remaining=40000;
   const documents=files.map(file=>{const preview=file.kind==='document'?file.text.slice(0,Math.min(remaining,20000)):'';remaining-=preview.length;return {name:file.name,kind:file.kind,notice:file.notice,text:preview,previewTruncated:preview.length<file.text.length,metadataParameters:file.metadata?.length};});
   const status=await requestChopper({task:'uSOPp feature and engineering assistant',question:text.slice(0,20000),history:messages.slice(1).slice(-12).map(m=>({role:m.role==='assist'?'assistant':'user',content:m.text.slice(0,8000)})),context:{comparisonFocus:focusOverride??comparisonFocus,comparisonSessionId:comparisonResult?.sessionId,projectPath:effectiveProjectPath,projectName:effectiveProjectName||result?.projectName||'',applicationFeatures:FEATURES,attachments:documents,logSummary:captures?{captures}:undefined,validationResult:result,ruleResults,counts:normalized?.counts||{},score:normalized?.score??null}},abort.signal,status=>{if(turn===generation.current)setProgress(status)});
   const data=status.result;
   if(turn===generation.current)setMessages(current=>[...current,{role:'assist',text:[data.modelNotice,data.answer||'No answer returned.'].filter(Boolean).join('\n'),source:data.source,evidence:data.evidence||[],helpEvidence:data.helpEvidence||[],elapsedSeconds:status.elapsedSeconds,review:data.semanticReviewRequired}]);
  }catch(error){if(turn===generation.current&&!abort.signal.aborted)reply(error instanceof Error?error.message:'Chopper is unavailable.');}
  finally{if(turn===generation.current){lock.current=false;setBusy(false);}}
 }

 function choose(action:string) {
  if(lock.current)return;
  if(action.startsWith('suggest:')){setQuestion(action.slice(8));composer.current?.focus();return;}
  if(action==='understand'){setComparisonFocus(false);void ask('Explain the machine functions and operating sequence of the selected project, with source evidence and active task scope.',undefined,false);return;}
  if(action==='differences'){setComparisonFocus(true);void ask('What are the major differences between the two MatchView projects? Categorise variables, logic, ladder, HMI layout and behaviour, hardware and configuration.',undefined,true);return;}
  if(action==='attach'){picker.current?.click();return;}
  if(action==='decode'||action==='frames-only'||action.startsWith('metadata:')) {
   setMessages(current=>[...current,{role:'user',text:action==='frames-only'?'Check recorded requests without metadata.':'Decode my log with metadata.'}]);
   showLogReply(attachments,action==='frames-only'?'frames-only':action.startsWith('metadata:')?action.slice(9):undefined);return;
  }
  if(action.startsWith('open:')){onOpenFeature?.(action.slice(5));return;}
  if(action==='home'){reply('WorkHub is the starting point for every uSOPp feature. Select a project in ByteMap to inspect packets or generate metadata. Administrators can open stored test history, review results and reuse archived projects.',[{label:'Open WorkHub',action:'open:home'}]);return;}
  if(action==='results'){reply('ResultView presents the results of your validation or comparison run. In LogicScan, export the complete run as HTML / PDF with its project and engineer cover details. MatchView reports use the same cover flow. Importable metadata XLSX / CSV keeps its data format.',[{label:'Open LogicScan results',action:'open:rules'},{label:'Open MatchView',action:'open:compare'}]);return;}
  if(action==='settings'&&!admin){reply('Settings lets you change your password and workspace appearance. Contact your administrator for shared Chopper configuration.',[{label:'Open Settings',action:'open:settings'}]);return;}
  if(action==='settings'){reply('Settings controls your password, theme and common configuration. An administrator can choose local tools, Ollama or a compatible model API for Chopper. Use the installed Ollama model name and http://127.0.0.1:11434 when Ollama runs on this application computer, then Save & check connection. Log decoding and feature guides work without a model.',[{label:'Open Settings',action:'open:settings'}]);return;}
  if(action==='learning'){reply('KnowHub holds approved engineering learning and the Rule Library. Review a finding, record an engineer explanation, and save approved alternatives. Draft rules need review and a draft check before enabling them.',[{label:'Open KnowHub',action:'open:learning'}]);return;}
  if(action==='metadata'){reply('MetaWorks generates the SpinConnect metadata workbook from your selected Automation Studio project. In ByteMap, open MetaWorks, review parameter names, payload offsets, datatypes and Sheet2 mappings, then export the workbook. Confirm the active configuration and workbook version before decoding logs.',[{label:'Open ByteMap / MetaWorks',action:'open:validation'}]);return;}
  const feature=FEATURES[action as keyof typeof FEATURES];
  if(feature)reply(`${feature.name}\n${feature.purpose}\n\n${feature.steps.map((step,i)=>`${i+1}. ${step}`).join('\n')}\n\nRecommended next step: ${feature.recommendation}`,[{label:`Open ${feature.name}`,action:`open:${action}`},{label:'Ask a question',action:`prompt:${feature.name}`}]);
  else if(action.startsWith('prompt:'))setQuestion(`Help me with ${action.slice(7)}: `);
 }

 const contextLabel=effectiveProjectName||result?.projectName||'No project selected';
 const showWelcome=messages.length===1&&messages[0].text===GREETING&&!busy&&!reading;
 return <div className="chopperInterface">
  {source&&sessionId&&<ValidationSourceEditor sessionId={sessionId} selection={source} datatypes={result?.datatypes||[]} onClose={()=>setSource(null)} onSaved={()=>{setSource(null);setSourceNotice('Source saved with backup. Run ByteMap / LogicScan again to refresh findings.');onSourceSaved?.(result?.projectPath||ruleResults?.projectPath||projectPath,projectName)}}/>}
  {admin&&<details className="chopperConnectionBar"><summary>Chopper connection: {modelLabel}</summary><div className="actions"><button className="btn" onClick={()=>void refreshModel()}>Refresh connection</button><small>Local tools work without a model. Configure optional Ollama / API models in Settings.</small></div></details>}
  {sourceNotice&&<p role="status">{sourceNotice}</p>}
  <div className="chopperWorkspace card">
   <aside className="chopperSidebar"><button className="btn primary newChat" onClick={newChat}><Plus size={14}/> New chat</button>
    <div className="chopperSideSection"><span>PROJECT KNOWLEDGE</span><button disabled={busy||reading||!effectiveProjectPath} onClick={()=>choose("understand")}>Understand this project</button><button disabled={busy||reading||!comparisonResult?.sessionId} onClick={()=>choose("differences")}>Explain MatchView changes</button><small>{comparisonResult?`${comparisonResult.baseName} vs ${comparisonResult.newName}`:"Run MatchView to explain two projects."}</small></div><div className="chopperSideSection"><span>uSOPp TOOLS</span>{SHORTCUTS.map(([key,label])=><button key={key} disabled={busy||reading} onClick={()=>choose(key)}><Search size={13}/>{key==='settings'&&!admin?'Settings':label}</button>)}</div>
    <details className="chopperSideSection"><summary>Optional project context</summary><label><input type="checkbox" checked={comparisonFocus} disabled={!comparisonResult?.sessionId||busy||reading} onChange={e=>setComparisonFocus(e.target.checked)}/> Follow-up questions use MatchView</label><label>Project for this chat<select value={projectId} disabled={busy||reading} onChange={e=>setProjectId(e.target.value)}><option value="">{projectName||'Selected ByteMap / LogicScan project'}</option>{projects.map(a=><option key={a.id} value={a.id}>{a.projectName||a.name}</option>)}</select></label><b>{contextLabel}</b><small>{effectiveProjectPath||'Chat and log decoding do not require a project.'}</small></details>
    <div className="chopperLearningBadge"><BrainCircuit size={16}/><div><b>{learningCount}</b><span>learning records</span></div></div>
   </aside>
   <section className="chopperChat"><header><span className="chopperAvatar"><Bot size={22}/></span><div><b>Chopper</b><span>All uSOPp features in one chat</span></div><i><Sparkles size={12}/>{admin?'Local tools + optional AI':'Project assistant'}</i></header>
    <div className="chopperContextBanner"><Cpu size={20}/><span>{effectiveProjectPath?<>Project context · <b>{contextLabel}</b></>:'Ready for your questions. Attach a project or paste a PLC log to add context.'}</span></div>
    <div className={`chopperMessages${showWelcome?' isWelcome':''}`} role="log" aria-live="polite">
     {showWelcome&&<section className="chopperWelcome" aria-labelledby="chopperWelcomeHeading"><Bot className="chopperWelcomeIcon" size={48} strokeWidth={1.7}/><span className="chopperWelcomeEyebrow">CHOPPER · ENGINEERING ASSISTANT</span><h2 id="chopperWelcomeHeading">Your engineering thinking partner.</h2><p>{effectiveProjectPath?<>Explore <strong>{contextLabel}</strong>, trace its logic and understand findings with source evidence.</>:'Explain PLC logic, review project differences and investigate validation findings. Add a project or log whenever you need source context.'}</p><div className="chopperWelcomePrompts">
      <button className="btn" onClick={()=>choose('suggest:Trace the motor start and stop logic and its interlocks in the selected project. Cite source files and show what can prevent the motor from running.')}>Explain the motor interlock <ArrowUpRight size={16}/></button>
      <button className="btn" onClick={()=>comparisonResult?.sessionId?choose('differences'):onOpenFeature?.('compare')}>Review the project differences <ArrowUpRight size={16}/></button>
      <button className="btn" onClick={()=>choose('suggest:Explain the latest ByteMap or LogicScan validation finding, including expected and actual values, source evidence and the corrective action.')}>Investigate a validation finding <ArrowUpRight size={16}/></button>
     </div><button className="btn chopperExplore" onClick={()=>onOpenFeature?.('home')}>Explore your work hub <ArrowRight size={19}/></button></section>}
     {!showWelcome&&messages.map((message,index)=><div className={'chopperMessage '+message.role+(message.logs?' withLog':'')} key={index}>
     {message.role==='assist'&&<span className="messageAvatar"><Bot size={15}/></span>}<div><p>{message.text}</p>
      {message.logs?.map((log,i)=><ChatLogReply key={i} data={log} busy={busy||reading} onExplain={capture=>void ask(`Explain this selected GC ${capture.groupCode} capture, its decoded readings and next actions.`,capture)}/>)}
      {message.choices&&<div className="chatFriendlyChoices">{message.choices.map(choice=><button className="btn" key={choice.action} disabled={busy||reading} onClick={()=>choose(choice.action)}>{choice.label}</button>)}</div>}
      {message.role==='assist'&&!message.logs&&<button className="chatCopy" aria-label="Copy Chopper reply" onClick={()=>void copyChatText(message.text).then(ok=>setCopyNotice(ok?'Reply copied.':'Select the reply and copy it manually.'))}>Copy reply</button>}
      {message.source&&<div className="assistSource">Source: {admin?message.source:message.source==='ollama'||message.source==='api'||message.source==='embedded'?'Chopper':message.source}{message.elapsedSeconds!==undefined&&` | Completed in ${message.elapsedSeconds}s`}{message.review&&" | Source references checked; explanation requires engineer review"}</div>}
      {!!message.evidence?.length&&<div className="assistEvidenceList">{message.evidence.map((item,i)=><details key={`${item.file}:${i}`}><summary>{item.file}{item.line?` : line ${item.line}`:''}</summary><pre>{item.excerpt||'No excerpt returned.'}</pre><button className="btn" disabled={!sessionId} onClick={()=>setSource({path:item.file,line:item.line||1})}>Open source / edit</button>{!sessionId&&<small>Run ByteMap or LogicScan once to enable source editing.</small>}</details>)}</div>}
      {!!message.helpEvidence?.length&&<div className="assistEvidenceList">{message.helpEvidence.map(item=><details key={item.id}><summary>[{item.sourceId}] {item.title} · Reference help</summary><p>{item.helpSet} · {item.file}</p><pre>{item.excerpt}</pre>{item.truncated&&<small>Indexed topic truncated; consult the original manual.</small>}<small>Documentation explains the format or library. Confirm compatibility with the project runtime.</small><button className="btn" onClick={()=>onOpenFeature?.('learning')}>Open KnowHub / B&amp;R help index</button></details>)}</div>}
     </div></div>)}
     {(busy||reading)&&<div className="chopperTyping"><Bot size={15}/><span>{reading?`${progress?.stage||'Reading attachments'}${progress?.name?` | ${progress.name}`:''}${progress?.total?` | ${progress.current}/${progress.total} files`:''}`:`${progress?.stage||'Processing'} | ${progress?.elapsedSeconds||0}s elapsed${progress?.total?` | ${progress.current}/${progress.total} files`:''}${progress?.estimatedStageRemainingSeconds!==undefined?` | about ${progress.estimatedStageRemainingSeconds}s remaining in this stage`:' | completion time depends on project size and model speed'}`}</span></div>}<div ref={messageEnd}/>
    </div>
    <div className="chopperAttachments">{attachments.map(item=><div className="chatAttachment" key={item.id}><Paperclip size={13}/><span title={item.notice}>{item.name}<small>{item.kind}</small></span><button aria-label={`Remove ${item.name}`} disabled={busy||reading} onClick={()=>{setAttachments(current=>current.filter(a=>a.id!==item.id));if(projectId===item.id)setProjectId('');pendingDecode.current=true;}}><X size={14}/></button></div>)}</div>
    <div className="chatFriendlyChoices chatPromptSuggestions" aria-label="Suggested Chopper questions">{CHAT_PROMPTS.slice(0,4).map(item=><button className="btn" disabled={busy||reading} key={item.title} onClick={()=>choose(`suggest:${item.prompt}`)}>{item.title}</button>)}<button className="btn" onClick={()=>onOpenFeature?.("help")}>How to chat</button></div><div className="chopperComposer unifiedComposer">
     <input type="file" multiple hidden ref={projectPicker} {...({webkitdirectory:'',directory:''} as any)} onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';void attachProject(files);}}/>
     <input type="file" multiple hidden ref={picker} onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';void attach(files);}}/>
     <button className="btn chatAttachButton" title="Attach files, a project ZIP or a project folder" aria-label="Attach files to Chopper" disabled={busy||reading} aria-expanded={attachmentMenu} onClick={()=>setAttachmentMenu(value=>!value)}><Paperclip size={20}/></button>{attachmentMenu&&<div className="chatAttachmentMenu"><button className="btn" onClick={()=>{setAttachmentMenu(false);picker.current?.click()}}>Files / project ZIP</button><button className="btn" onClick={()=>{setAttachmentMenu(false);projectPicker.current?.click()}}>Project folder</button></div>}
     <textarea ref={composer} aria-label="Message Chopper" value={question} disabled={busy||reading} onChange={e=>setQuestion(e.target.value)} placeholder="Ask Chopper, paste a PLC log, or attach files..." onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void ask();}}}/>
     <button className="btn primary" disabled={busy||reading||(!question.trim()&&!attachments.length)} onClick={()=>void ask()}><Send size={14}/> Send</button>
     <small role="status">{copyNotice||'Logs decode locally. Readable attachment previews are shared with the selected model when you send a question. Shift + Enter adds a line.'}</small>
    </div>
   </section>
  </div>
 </div>;
}
