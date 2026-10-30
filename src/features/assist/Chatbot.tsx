import {useEffect,useRef,useState} from 'react';
import {Activity,ArrowRight,ArrowUpRight,BarChart3,Bot,BrainCircuit,CheckSquare,Code2,Columns2,Cpu,GitBranch,Maximize2,MessageSquare,Minimize2,Network,Paperclip,Plus,Search,Send,Settings2,Sparkles,Stethoscope,Workflow,X} from 'lucide-react';
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
import {openDashboardBuilder,isWorkHubDashboardRequest} from '../workhub/dashboards/bridge';
import questionSuite from './chopperQuestionSuite.json';
import {ChopperFunctionFlow,flowConversationText,type ChopperFlowData} from './ChopperFunctionFlow';
import {ChopperReply} from './ChopperReply';
import {ProjectIntelligence,useProjectIntelligence,ContextUsage} from './ProjectIntelligence';
import {ChopperReportSummary,type ReportAnalysis} from './ChopperReportSummary';
import {ChopperPerformanceDashboard,type ReportSection} from './ChopperPerformanceDashboard';
import {useReportDashboard} from './reportDashboard';
import {MachineFunctionAnalysis} from './MachineFunctionAnalysis';

type Evidence={file:string;line?:number;excerpt?:string;sourceId?:string};
type HelpEvidence=Evidence&{id:string;sourceId:string;title:string;helpSet:string;truncated?:boolean};
type Choice={label:string;action:string};
type WorkbenchCategory=typeof questionSuite.categories[number];
const WORKBENCH_ICONS={workflow:Workflow,stethoscope:Stethoscope,cpu:Cpu,code:Code2,network:Network,checklist:CheckSquare};
type ChatMessage={role:'user'|'assist';text:string;historyText?:string;source?:string;evidence?:Evidence[];helpEvidence?:HelpEvidence[];logs?:ChatLogData[];functionFlow?:ChopperFlowData;machineAnalysis?:any;machineAnalysisProjectId?:string;reportAnalysis?:ReportAnalysis;choices?:Choice[];elapsedSeconds?:number;review?:boolean;trainingExampleId?:string;contextUsage?:any;modelNotice?:string;retrieval?:any};
const GREETING='Hi, I am Chopper, your uSOPp.ai assistant. Ask about ByteMap, MetaWorks, DataInspect, MatchView, LogicScan or KnowHub. Attach a log and its metadata, or paste the log here, and I will show the decoded values in this chat. A selected project is optional.';
const SHORTCUTS=[['decode','Log decoder'],['home','WorkHub'],['validation','ByteMap'],['metadata','MetaWorks'],['plc','DataInspect'],['compare','MatchView'],['rules','LogicScan'],['results','ResultView'],['learning','KnowHub'],['settings','Settings / My profile']] as const;

export function Chatbot({result,comparisonResult,projectPath,projectName,ruleResults,onSourceSaved,onOpenFeature}:{result:any;comparisonResult?:any;projectPath:string;projectName:string;ruleResults:any;onSourceSaved?:(path:string,name:string)=>void;onOpenFeature?:(feature:string)=>void}) {
 const {user}=useAccount();const admin=user.role==='admin';
 const [projectId,setProjectId]=useState(''),[attachmentMenu,setAttachmentMenu]=useState(false);
 const projectPicker=useRef<HTMLInputElement>(null);
 const [question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[reading,setReading]=useState(false),[learningCount,setLearningCount]=useState(0);
 const [activeWorkbenchCategory,setActiveWorkbenchCategory]=useState<WorkbenchCategory['id']>(questionSuite.categories[0].id),[investigationMode,setInvestigationMode]=useState<'auto'|'deep'>('auto');
 const [messages,setMessages]=useState<ChatMessage[]>([{role:'assist',text:GREETING}]),[attachments,setAttachments]=useState<ChatAttachment[]>([]);
 const reports=attachments.filter(item=>item.kind==='report');const reportManager=useReportDashboard(attachments,user.username);
 const [reportView,setReportView]=useState<'split'|'chat'|'dashboard'>('split'),[reportSection,setReportSection]=useState<ReportSection>('overview'),[reportExpanded,setReportExpanded]=useState(false),[reportTools,setReportTools]=useState(false);
 useEffect(()=>{if(!reportExpanded)return;const before=document.body.style.overflow;document.body.style.overflow='hidden';const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setReportExpanded(false)};window.addEventListener('keydown',close);return()=>{document.body.style.overflow=before;window.removeEventListener('keydown',close)}},[reportExpanded]);
 const [source,setSource]=useState<SourceSelection|null>(null),[sourceNotice,setSourceNotice]=useState(''),[copyNotice,setCopyNotice]=useState('');
 const picker=useRef<HTMLInputElement>(null),messageEnd=useRef<HTMLDivElement>(null),flowReplyStart=useRef<HTMLDivElement>(null),composer=useRef<HTMLTextAreaElement>(null),generation=useRef(0),controller=useRef<AbortController|null>(null);
 const lock=useRef(false),pendingDecode=useRef(false);
 const projects=attachments.filter(a=>a.kind==='project');
 const attachedProject=projects.find(a=>a.id===projectId);
 const effectiveProjectPath=attachedProject?.projectPath||projectPath;
 const intelligence=useProjectIntelligence(effectiveProjectPath);
 const effectiveProjectName=attachedProject?.projectName||projectName;
 const sessionId=attachedProject?undefined:result?.sessionId||ruleResults?.sessionId;
 const [progress,setProgress]=useState<any>(null);
 const [comparisonFocus,setComparisonFocus]=useState(false);
 useEffect(()=>{fetch('/api/rules/learning/model').then(r=>r.ok?r.json():{recordCount:0}).then(data=>setLearningCount(Number(data.recordCount||0))).catch(()=>{});return()=>{generation.current++;controller.current?.abort();}},[]);
 useEffect(()=>{if(messages[messages.length-1]?.functionFlow&&!busy&&!reading)flowReplyStart.current?.scrollIntoView({block:'start'});else if(messages.length>1||busy||reading)messageEnd.current?.scrollIntoView({block:'nearest'});},[messages,busy,reading]);
 const reply=(text:string,choices?:Choice[])=>setMessages(current=>[...current,{role:'assist',text,choices}]);
 const newChat=()=>{generation.current++;controller.current?.abort();lock.current=false;pendingDecode.current=false;setBusy(false);setComparisonFocus(false);setProgress(null);setReading(false);setMessages([{role:'assist',text:GREETING}]);setQuestion('');setAttachments([]);setProjectId('');setAttachmentMenu(false);setCopyNotice('');reportManager.reset();setReportSection('overview');setReportView('split');setReportExpanded(false);};

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
    try {setProgress({stage:/\.zip$/i.test(file.name)?'Uploading project ZIP':'Reading attachment',name:file.name});const item=await readChatAttachment(file);added.push(item);notices.push(`${item.name}: ${item.kind==='report'?'report ready for analysis':item.kind==='metadata'?'metadata workbook':item.kind==='log'?'PLC log':item.kind==='project'?'project uploaded':item.kind==='unsupported'?'not readable':'readable document'}${item.notice?`\n${item.notice}`:''}`);}
    catch(error){notices.push(error instanceof Error?error.message:'Attachment could not be read.');}
   }
   if(turn!==generation.current)return;
   setAttachments(current=>[...current,...added]);const uploaded=added.filter(a=>a.kind==='project');if(uploaded.length)setProjectId(uploaded[uploaded.length-1].id);pendingDecode.current=added.some(a=>a.kind==='log'||a.kind==='metadata')||pendingDecode.current;
   const reportChoices=added.some(a=>a.kind==='report')?[{label:'Analyze reports',action:'suggest:Analyze the attached reports and summarize the main machine results.'},{label:'Highest production',action:'suggest:Which machine has the highest production kg?'},{label:'Highest stoppage and reasons',action:'suggest:Which machine has the highest total stoppage duration and what are its reasons?'}]:undefined;
   reply(notices.join('\n\n'),reportChoices||(added.some(a=>a.kind==='log'||a.kind==='metadata')?[{label:'Decode attached log',action:'decode'}]:undefined));
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
  if(/^(?:guide me|how (?:do i|to) use (?:this |the )?app|step by step guide)/i.test(text)){setQuestion('');choose('coach');return;}
  let files=attachments;
  setQuestion('');setCopyNotice('');setMessages(current=>[...current,{role:'user',text:looksLikeLog(text)?`Decode pasted PLC log (${text.length.toLocaleString()} characters).`:text}]);
  if(!user.isDemo&&isWorkHubDashboardRequest(text)){reply('I opened My Dashboard in WorkHub. Review the draft, apply it to the editor and save when ready.');openDashboardBuilder(text);return;}
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
   const captures=selectedCapture?[selectedCapture]:latestLog?.flatMap(log=>decodeCollectedLog(log.text,log.metadata).captures.filter(c=>!requestedGroup||c.groupCode===Number(requestedGroup)).map(c=>({groupCode:c.groupCode,protocol:c.protocol,...(c.protocol==='ybs'?{responseBytes:c.responseBytes,machineId:c.requestBytes?.[1],requestLine:c.requestLine,responseLine:c.responseLine}:{}),asset:c.asset,timestamp:c.timestamp,status:c.status,resultCode:c.resultCode,issues:c.issues,logErrors:c.logErrors,payloadLength:c.payloadLength,expectedLength:c.expectedLength,values:c.values.slice(0,80).map(v=>({tagCode:v.tagCode,parameter:v.parameter,offset:v.offset,dataType:v.dataType,value:v.formattedValue,qualityIssue:v.qualityIssue}))}))).slice(0,40);
   let remaining=40000;
   const documents=files.map(file=>{const preview=file.kind==='document'?file.text.slice(0,Math.min(remaining,20000)):'';remaining-=preview.length;return {name:file.name,kind:file.kind,reportId:file.reportId,notice:file.notice,text:preview,previewTruncated:preview.length<file.text.length,metadataParameters:file.metadata?.length};});
   const reportQuery=[...messages].reverse().find(message=>message.reportAnalysis)?.reportAnalysis;
   const now=new Date();const reportToday=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
   const status=await requestChopper({task:'uSOPp.ai feature and engineering assistant',question:text.slice(0,20000),history:messages.slice(1).slice(-12).map(m=>({role:m.role==='assist'?'assistant':'user',content:(m.historyText||m.text).slice(0,8000)})),context:{offlineOnly:true,intelligenceProjectId:intelligence.state?.projectId,investigationMode,comparisonFocus:focusOverride??comparisonFocus,comparisonSessionId:comparisonResult?.sessionId,projectPath:effectiveProjectPath,projectName:effectiveProjectName||result?.projectName||'',applicationFeatures:FEATURES,attachments:documents,reportToday,reportDashboard:reportManager.controls,reportQuery:reportQuery?{kind:reportQuery.kind,scope:reportQuery.scope,focusMachine:reportQuery.focusMachine,fields:reportQuery.fields,groupBy:reportQuery.groupBy,plan:reportQuery.plan}:undefined,logSummary:captures?{captures,selectedCapture:Boolean(selectedCapture)}:undefined,validationResult:result,ruleResults,counts:normalized?.counts||{},score:normalized?.score??null}},abort.signal,status=>{if(turn===generation.current)setProgress(status)});
   const data=status.result;if(turn===generation.current){reportManager.receive(data.reportAnalysis?.dashboard);if(data.reportAnalysis?.dashboard?.query)setReportSection(data.reportAnalysis.dashboard.query.section==='overview'?'overview':'question');}
   if(turn===generation.current)setMessages(current=>[...current,{role:'assist',text:[data.answer||'No answer returned.',data.trainingDraftNotice].filter(Boolean).join('\n'),historyText:data.functionFlow?.view?flowConversationText(data.functionFlow.view):undefined,source:data.source,evidence:data.evidence||[],helpEvidence:data.helpEvidence||[],functionFlow:data.functionFlow,machineAnalysis:data.machineAnalysis,machineAnalysisProjectId:data.machineAnalysisProjectId,reportAnalysis:data.reportAnalysis,choices:data.choices,elapsedSeconds:status.elapsedSeconds,review:data.semanticReviewRequired,trainingExampleId:data.trainingExampleId,contextUsage:data.contextUsage,modelNotice:data.modelNotice,retrieval:data.retrieval}]);
  }catch(error){if(turn===generation.current&&!abort.signal.aborted)reply(error instanceof Error?error.message:'Chopper is unavailable.');}
  finally{if(turn===generation.current){lock.current=false;setBusy(false);}}
 }

 function choose(action:string) {
  if(lock.current)return;
  if(action==='coach'){reply('I can guide you one step at a time. What would you like to do first? You can ask another question at any point.',Object.entries(FEATURES).map(([key,feature])=>({label:feature.name,action:`coach:${key}:0`})));return;}
  if(action.startsWith('coach:')){
   const [,key,position]=action.split(':');const feature=FEATURES[key as keyof typeof FEATURES];const step=Number(position);if(!feature)return;
   reply(`${feature.name} · Step ${step+1} of ${feature.steps.length}\n\n${feature.steps[step]}\n\nTell me what you see or ask about this step. Use Next step when you are ready.`,[{label:`Open ${feature.name}`,action:`open:${key}`},...(step+1<feature.steps.length?[{label:'Next step',action:`coach:${key}:${step+1}`}]:[{label:'Choose another workflow',action:'coach'}])]);return;
  }
  if(action.startsWith('suggest:')){setQuestion(action.slice(8));composer.current?.focus();return;}
  if(action==='understand'){setComparisonFocus(false);void ask('Explain the machine functions and operating sequence of the selected project, with source evidence and active task scope.',undefined,false);return;}
  if(action==='flow'){void ask('Show a step-by-step function flow for a PLC routine in the selected project.',undefined,comparisonFocus||(!effectiveProjectPath&&!!comparisonResult?.sessionId));return;}
  if(action==='differences'){setComparisonFocus(true);void ask('What are the major differences between the two MatchView projects? Categorise variables, logic, ladder, HMI layout and behaviour, hardware and configuration.',undefined,true);return;}
  if(action==='attach'){picker.current?.click();return;}
  if(action==='decode'||action==='frames-only'||action.startsWith('metadata:')) {
   setMessages(current=>[...current,{role:'user',text:action==='frames-only'?'Check recorded requests without metadata.':'Decode my log with metadata.'}]);
   showLogReply(attachments,action==='frames-only'?'frames-only':action.startsWith('metadata:')?action.slice(9):undefined);return;
  }
  if(action.startsWith('open:')){onOpenFeature?.(action.slice(5));return;}
  if(action==='home'){reply('WorkHub is the starting point for every uSOPp.ai feature. Select a project in ByteMap to inspect SpinConnect packets or generate metadata. Use test history to review your saved results and reuse archived projects. Admin can also open user management.',[{label:'Open WorkHub',action:'open:home'}]);return;}
  if(action==='results'){reply('ResultView presents the results of your validation or comparison run. In LogicScan, export the complete run as HTML / PDF with its project and engineer cover details. MatchView reports use the same cover flow. Importable metadata XLSX / CSV keeps its data format.',[{label:'Open LogicScan results',action:'open:rules'},{label:'Open MatchView',action:'open:compare'}]);return;}
  if(action==='settings'&&!admin){reply('Open Settings → My profile to upload or remove your photo. To change your password, enter your current password, new password and confirmation, then save. You can also choose your theme and table preferences.',[{label:'Open My profile',action:'open:settings'}]);return;}
  if(action==='settings'){reply('Open Settings to upload or remove your profile photo, change your password, and choose your theme and table layout. Admin manages account access in WorkHub. Open Help for the complete steps.',[{label:'Open Settings',action:'open:settings'}]);return;}
  if(action==='learning'){reply('KnowHub holds approved engineering learning and the Rule Library. Review a finding, record an engineer explanation, and save approved alternatives. Draft rules need review and a draft check before enabling them.',[{label:'Open KnowHub',action:'open:learning'}]);return;}
  if(action==='metadata'){reply('MetaWorks generates the SpinConnect metadata workbook from your selected Automation Studio project. In ByteMap, open MetaWorks, review parameter names, payload offsets, datatypes and Sheet2 mappings, then export the workbook. Confirm the active configuration and workbook version before decoding logs.',[{label:'Open ByteMap / MetaWorks',action:'open:validation'}]);return;}
  const feature=FEATURES[action as keyof typeof FEATURES];
  if(feature)reply(`${feature.name}\n${feature.purpose}\n\n${feature.steps.map((step,i)=>`${i+1}. ${step}`).join('\n')}\n\nRecommended next step: ${feature.recommendation}`,[{label:`Open ${feature.name}`,action:`open:${action}`},{label:'Ask a question',action:`prompt:${feature.name}`}]);
  else if(action.startsWith('prompt:'))setQuestion(`Help me with ${action.slice(7)}: `);
 }

 const contextLabel=effectiveProjectName||result?.projectName||'No project selected';
 // Keep the investigation landing screen visible while a project or files are
 // being attached. Upload notices are represented by the attachment chips;
 // switch to the conversation layout only after the user sends a question.
 const showWelcome=!messages.some(message=>message.role==='user')&&!busy&&!reading;
 const selectedWorkbenchCategory=questionSuite.categories.find(category=>category.id===activeWorkbenchCategory)||questionSuite.categories[0];
 const indexStatus=intelligence.state?.ready?'Project indexed':intelligence.state?.running?'Indexing project':effectiveProjectPath?'Checking project index':'No project selected';
 const WorkbenchCategoryIcon=WORKBENCH_ICONS[selectedWorkbenchCategory.icon as keyof typeof WORKBENCH_ICONS];
 return <div className={`chopperInterface${reports.length?' hasReports':''}${reportExpanded?' reportExpanded':''}${reportTools?' showReportTools':''}`}>
  {source&&sessionId&&<ValidationSourceEditor sessionId={sessionId} selection={source} datatypes={result?.datatypes||[]} onClose={()=>setSource(null)} onSaved={()=>{setSource(null);setSourceNotice('Source saved with backup. Run ByteMap / LogicScan again to refresh findings.');onSourceSaved?.(result?.projectPath||ruleResults?.projectPath||projectPath,projectName)}}/>}
  {sourceNotice&&<p role="status">{sourceNotice}</p>}
  <div className={`chopperWorkspace card${showWelcome?' chopperWelcomeWorkspace':''}`}>
   <aside className="chopperSidebar"><button className="btn primary newChat" onClick={newChat}><Plus size={14}/> New chat</button><button className="btn" disabled={busy||reading} onClick={()=>choose('coach')}>Guide me step by step</button>
    <div className="chopperSideSection chopperInvestigationNav" role="group" aria-label="Investigation categories"><span>INVESTIGATION</span>{questionSuite.categories.map(category=>{const Icon=WORKBENCH_ICONS[category.icon as keyof typeof WORKBENCH_ICONS];return <button type="button" key={category.id} className={activeWorkbenchCategory===category.id?'active':''} aria-pressed={activeWorkbenchCategory===category.id} onClick={()=>setActiveWorkbenchCategory(category.id)}><Icon size={14}/>{category.label}</button>})}</div>
    <div className="chopperSideSection"><span>PROJECT KNOWLEDGE</span><button disabled={busy||reading||!effectiveProjectPath} onClick={()=>choose("understand")}>Understand this project</button><button disabled={busy||reading||(!effectiveProjectPath&&!comparisonResult?.sessionId)} onClick={()=>choose('flow')}>Routine function flow</button><button disabled={busy||reading||!comparisonResult?.sessionId} onClick={()=>choose("differences")}>Explain MatchView changes</button><small>{comparisonResult?`${comparisonResult.baseName} vs ${comparisonResult.newName}`:"Run MatchView to explain two projects."}</small></div><div className="chopperSideSection"><span>uSOPp.ai TOOLS</span>{SHORTCUTS.map(([key,label])=><button key={key} disabled={busy||reading} onClick={()=>choose(key)}><Search size={13}/>{key==='settings'&&!admin?'Settings':label}</button>)}</div>
    <details className="chopperSideSection chopperFaq"><summary>FAQ - Quick answers</summary><div className="chopperFaqList">
     <details className="chopperFaqPrompts"><summary><WorkbenchCategoryIcon size={12}/> Suggested questions - {selectedWorkbenchCategory.label}<span>{selectedWorkbenchCategory.tests.length}</span></summary><div className="chopperFaqPromptList">{selectedWorkbenchCategory.tests.map(test=><button type="button" key={test.id} title={`Expected: ${test.expected}`} onClick={()=>choose(`suggest:${test.question}`)}><span>{test.id}</span><span>{test.question}</span><ArrowUpRight size={12}/></button>)}</div><details className="chopperFaqWording"><summary>Wording variations<span>{questionSuite.wordingVariationTests.length} prompts</span></summary><div>{questionSuite.wordingVariationTests.map(test=><button type="button" key={test.id} onClick={()=>choose(`suggest:${test.question}`)}><span>{test.id}</span>{test.question}</button>)}</div></details></details>
     <details><summary>How do I ask about a project?</summary><p>Select or attach a project, then ask a question or choose one of the suggested prompts.</p></details><details><summary>How do I decode a PLC log?</summary><p>Open Log decoder, attach the collected log and its matching metadata workbook, then select a Group Code and capture.</p></details><details><summary>Can Chopper change PLC code?</summary><p>Chopper explains source and suggests edits for review. It does not apply code changes automatically.</p></details><details><summary>Why are some findings unresolved?</summary><p>Unsupported formats, missing libraries, inactive tasks or unavailable source can limit what static analysis can confirm.</p></details>
    </div></details>
    <details className="chopperSideSection"><summary>Optional project context</summary><label><input type="checkbox" checked={comparisonFocus} disabled={!comparisonResult?.sessionId||busy||reading} onChange={e=>setComparisonFocus(e.target.checked)}/> Follow-up questions use MatchView</label><label>Project for this chat<select value={projectId} disabled={busy||reading} onChange={e=>setProjectId(e.target.value)}><option value="">{projectName||'Selected ByteMap / LogicScan project'}</option>{projects.map(a=><option key={a.id} value={a.id}>{a.projectName||a.name}</option>)}</select></label><b>{contextLabel}</b><small>{effectiveProjectPath||'Chat and log decoding do not require a project.'}</small></details>
    <div className="chopperLearningBadge"><BrainCircuit size={16}/><div><b>{learningCount}</b><span>learning records</span></div></div>
   </aside>
   <div className="chopperWorkArea">
   {!!reports.length&&<div className="chopperReportViewBar"><span><BarChart3 size={16}/><b>Performance workspace</b> · {reports.length} reports</span><div className="reportViewButtons"><button className={`btn ${reportView==='chat'?'active':''}`} onClick={()=>setReportView('chat')}><MessageSquare size={13}/>Chat</button><button className={`btn ${reportView==='split'?'active':''}`} onClick={()=>setReportView('split')}><Columns2 size={13}/>Split</button><button className={`btn ${reportView==='dashboard'?'active':''}`} onClick={()=>setReportView('dashboard')}><BarChart3 size={13}/>Dashboard</button><button className="btn" aria-label="Show engineering tools" aria-pressed={reportTools} onClick={()=>setReportTools(value=>!value)}><Settings2 size={13}/></button><button className="btn" aria-label={reportExpanded?'Restore report workspace':'Expand report workspace'} onClick={()=>setReportExpanded(value=>!value)}>{reportExpanded?<Minimize2 size={14}/>:<Maximize2 size={14}/>}</button></div></div>}
   <div className={`chopperAnalysisLayout${reports.length?` view-${reportView}`:''}`}>
   <section className="chopperChat"><header><span className="chopperAvatar"><Bot size={22}/></span><div><b>Chopper</b><span>{reports.length?'Your mill performance assistant':'All uSOPp.ai features in one chat'}</span></div><i><Sparkles size={12}/>Engineering assistant</i></header>
    {!showWelcome&&<div className="chopperContextBanner"><Cpu size={20}/><span>{effectiveProjectPath?<>Project context · <b>{contextLabel}</b></>:'Ready for your questions. Attach a report, project or PLC log to add context.'}</span></div>}
    {reports.length?<details className="reportEngineeringContext"><summary>Project context</summary><ProjectIntelligence project={intelligence}/></details>:<div className={showWelcome?'workbenchIndexDetails':''}><ProjectIntelligence project={intelligence}/></div>}
    <div className={`chopperMessages${showWelcome?' isWelcome':''}`} role="log" aria-live="polite">
     {showWelcome&&<section className="chopperReferenceWelcome" aria-labelledby="chopperWelcomeHeading">
      <header className="chopperReferenceTop"><div className="chopperReferenceBrand"><span className="chopperReferenceAvatar"><Bot size={17}/></span><div><b>Chopper AI</b><small>PLC Engineering Assistant</small></div></div><span className={`chopperProjectStatus${intelligence.state?.ready?' isReady':''}`}><Activity size={12}/>{indexStatus}</span></header>
      <div className="chopperReferenceControls"><label>Active engineering project<select aria-label="Active engineering project" value={projectId} disabled={busy||reading} onChange={event=>setProjectId(event.target.value)}><option value="">{effectiveProjectPath?`${contextLabel} (current project)`:'Select or attach a project'}</option>{projects.map(item=><option key={item.id} value={item.id}>{item.projectName||item.name}</option>)}</select></label><div className="chopperModeControl"><span>Investigation mode</span><div role="group" aria-label="Investigation mode"><button type="button" aria-pressed={investigationMode==='auto'} className={investigationMode==='auto'?'active':''} onClick={()=>setInvestigationMode('auto')}>Auto</button><button type="button" aria-pressed={investigationMode==='deep'} className={investigationMode==='deep'?'active':''} onClick={()=>setInvestigationMode('deep')}>Deep</button></div></div></div>
      <div className="chopperReferenceHero"><Bot size={26}/><h2 id="chopperWelcomeHeading">What would you like to investigate?</h2><p>Ask about PLC logic, machine functions, alarms, runtime faults, code review or engineering documents.</p></div>
      <p className="chopperWorkbenchHint">{effectiveProjectPath?<>Selected project: <b>{contextLabel}</b>. Answers use indexed evidence where available.</>:'Select a project or attach a PLC project to get source-linked answers. You can also ask general questions without a project.'}</p>
     </section>}
     {!showWelcome&&messages.map((message,index)=><div className={'chopperMessage '+message.role+(message.logs?' withLog':'')+(message.functionFlow?' withFlow':'')} key={index} ref={message.functionFlow&&index===messages.length-1?flowReplyStart:undefined}>
     {message.role==='assist'&&<span className="messageAvatar"><Bot size={15}/></span>}<div>{message.reportAnalysis&&<ChopperReportSummary data={message.reportAnalysis} compact={!!reports.length}/>} {message.role==='assist'?<ChopperReply text={message.reportAnalysis?.summary||message.text} onReference={id=>{
      const sourceIndex=message.evidence?.findIndex((item,i)=>(item.sourceId||`S${i+1}`)===id)??-1;
      const helpIndex=message.helpEvidence?.findIndex(item=>item.sourceId===id)??-1;
      const target=sourceIndex>=0?document.getElementById(`chopper-evidence-${index}-${sourceIndex}`):helpIndex>=0?document.getElementById(`chopper-help-${index}-${helpIndex}`):null;
      if(target instanceof HTMLDetailsElement){target.open=true;target.scrollIntoView({behavior:'smooth',block:'nearest'});}
     }}/>:<p>{message.text}</p>}
      {message.logs?.map((log,i)=><ChatLogReply key={i} data={log} busy={busy||reading} onExplain={capture=>void ask(`Explain this selected GC ${capture.groupCode} capture, its decoded readings and next actions.`,capture)}/>)}
      {message.functionFlow&&<ChopperFunctionFlow data={message.functionFlow} onOpened={opened=>setMessages(current=>current.map((item,i)=>i===index&&item.functionFlow?{...item,text:`Working sequence for ${opened.selectedPath}.`,historyText:flowConversationText(opened.view),functionFlow:{...item.functionFlow,...opened}}:item))}/>}
      {message.machineAnalysis&&<MachineFunctionAnalysis data={message.machineAnalysis} projectId={message.machineAnalysisProjectId} onReference={id=>{const sourceIndex=message.evidence?.findIndex((item,i)=>(item.sourceId||`S${i+1}`)===id)??-1;const target=sourceIndex>=0?document.getElementById(`chopper-evidence-${index}-${sourceIndex}`):null;if(target instanceof HTMLDetailsElement){target.open=true;target.scrollIntoView({behavior:'smooth',block:'nearest'});}}}/>}
      {message.choices&&<div className="chatFriendlyChoices">{message.choices.map(choice=><button className="btn" key={choice.action} disabled={busy||reading} onClick={()=>choose(choice.action)}>{choice.label}</button>)}</div>}
      {message.reportAnalysis?.summary&&<details className="chopperReportDetail"><summary>Full calculation & worksheet references</summary><ChopperReply text={message.text}/></details>}
      {message.role==='assist'&&!message.logs&&<button className="chatCopy" aria-label="Copy Chopper reply" onClick={()=>void copyChatText(message.text).then(ok=>setCopyNotice(ok?'Reply copied.':'Select the reply and copy it manually.'))}>Copy reply</button>}
      {message.modelNotice&&<p className="chopperModelNotice" role="status">{message.modelNotice}</p>}
      <ContextUsage usage={message.contextUsage} retrieval={message.retrieval}/>
      {!!message.retrieval?.coverage?.remainingSections&&<button className="btn" disabled={busy||reading} onClick={()=>void ask(message.retrieval.question||messages.slice(0,index).reverse().find(item=>item.role==='user')?.text||'Explain the complete machine working sequence')}>Continue saved analysis</button>}
      {message.source&&<div className="assistSource">Source: {message.source==='local-function-flow'?'PLC source function flow':message.source==='ollama'||message.source==='api'||message.source==='embedded'?'Chopper':message.source}{message.elapsedSeconds!==undefined&&` | Completed in ${message.elapsedSeconds}s`}{message.review&&" | Source references checked; explanation requires engineer review"}</div>}
      {message.trainingExampleId&&<button className="chatCopy" onClick={()=>onOpenFeature?.('learning')}>Training draft saved · Review in KnowHub</button>}
      {!!message.evidence?.length&&<div className="assistEvidenceList">{message.evidence.map((item,i)=><details id={`chopper-evidence-${index}-${i}`} key={`${item.file}:${i}`}><summary>[{item.sourceId||`S${i+1}`}] {item.file}{item.line?` : line ${item.line}`:''}</summary><pre>{item.excerpt||'No excerpt returned.'}</pre><button className="btn" disabled={!sessionId} onClick={()=>setSource({path:item.file,line:item.line||1})}>Open source / edit</button>{!sessionId&&<small>Run ByteMap or LogicScan once to enable source editing.</small>}</details>)}</div>}
      {!!message.helpEvidence?.length&&<div className="assistEvidenceList">{message.helpEvidence.map((item,i)=><details id={`chopper-help-${index}-${i}`} key={item.id}><summary>[{item.sourceId}] {item.title} · Reference help</summary><p>{item.helpSet} · {item.file}</p><pre>{item.excerpt}</pre>{item.truncated&&<small>Indexed topic truncated; consult the original manual.</small>}<small>Documentation explains the format or library. Confirm compatibility with the project runtime.</small></details>)}</div>}
     </div></div>)}
     {(busy||reading)&&<div className="chopperTyping"><Bot size={15}/><span>{reading?`${progress?.stage||'Reading attachments'}${progress?.name?` | ${progress.name}`:''}${progress?.total?` | ${progress.current}/${progress.total} files`:''}`:`${progress?.stage||'Processing'} | ${progress?.elapsedSeconds||0}s elapsed${progress?.total?` | ${progress.current}/${progress.total} files`:''}${progress?.estimatedStageRemainingSeconds!==undefined?` | about ${progress.estimatedStageRemainingSeconds}s remaining in this stage`:' | preparing your answer'}`}</span></div>}<div ref={messageEnd}/>
    </div>
    <div className="chopperAttachments">{attachments.map(item=><div className="chatAttachment" key={item.id}><Paperclip size={13}/><span title={item.notice}>{item.name}<small>{item.kind}</small></span><button aria-label={`Remove ${item.name}`} disabled={busy||reading} onClick={()=>{setAttachments(current=>current.filter(a=>a.id!==item.id));if(projectId===item.id)setProjectId('');pendingDecode.current=true;}}><X size={14}/></button></div>)}</div>
    {busy&&<ContextUsage usage={progress?.contextUsage} retrieval={progress?.retrieval}/>}
    {!showWelcome&&<div className="chatFriendlyChoices chatPromptSuggestions" aria-label="Suggested Chopper questions">{(reports.length?[{title:'Performance overview',prompt:'Give a performance overview of the uploaded reports.'},{title:'Daily trend',prompt:'Show the daily production trend.'},{title:'Stoppage reasons',prompt:'Which machine has the highest total stoppage duration and what are its reasons?'}]:selectedWorkbenchCategory.tests.slice(0,5).map(test=>({title:test.id,prompt:test.question}))).map(item=><button className="btn" disabled={busy||reading} key={item.title} onClick={()=>choose(item.title==='Function flow'?'flow':`suggest:${item.prompt}`)}>{item.title}</button>)}<button className="btn" onClick={()=>onOpenFeature?.("help")}>How to chat</button></div>}<div className="chopperComposer unifiedComposer">
     <input type="file" multiple hidden ref={projectPicker} {...({webkitdirectory:'',directory:''} as any)} onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';void attachProject(files);}}/>
     <input type="file" multiple hidden ref={picker} onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';void attach(files);}}/>
     <button className="btn chatAttachButton" title="Attach files, a project ZIP or a project folder" aria-label="Attach files to Chopper" disabled={busy||reading} aria-expanded={attachmentMenu} onClick={()=>setAttachmentMenu(value=>!value)}><Paperclip size={16}/>{showWelcome&&<span>Attach</span>}</button>{attachmentMenu&&<div className="chatAttachmentMenu"><button className="btn" onClick={()=>{setAttachmentMenu(false);picker.current?.click()}}>Files / project ZIP</button><button className="btn" onClick={()=>{setAttachmentMenu(false);projectPicker.current?.click()}}>Project folder</button></div>}
     <textarea ref={composer} aria-label="Message Chopper" value={question} disabled={busy||reading} onChange={e=>setQuestion(e.target.value)} placeholder={reports.length?"Compare report fields, machines, dates, shifts or lots in your own words...":showWelcome?"Describe the PLC behavior you want to investigate...":"Ask about a report, paste a PLC log, or attach files..."} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void ask();}}}/>
     <button className="btn primary" disabled={busy||reading||(!question.trim()&&!attachments.length)} onClick={()=>void ask()}><Send size={14}/> {showWelcome?'Ask Chopper':'Send'}</button>
     <small role="status">{copyNotice||'Attach your reports, metadata or logs and ask a question. Shift + Enter adds a line.'}</small>
    </div>
   </section>
   {!!reports.length&&<ChopperPerformanceDashboard manager={reportManager} section={reportSection} onSection={setReportSection} onAsk={text=>{setReportView('split');void ask(text)}} disabled={busy||reading}/>}
   </div></div>
  </div>
 </div>;
}
