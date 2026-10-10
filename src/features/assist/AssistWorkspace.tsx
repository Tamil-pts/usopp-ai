import {useCallback,useEffect,useState} from 'react';
import {Bot,BrainCircuit,MessageSquare} from 'lucide-react';
import {Chatbot} from './Chatbot';
import {LearningCenter} from './LearningCenter';
import {RuleLogicEvidence} from '../rules/RuleLogicEvidence';
import {RuleConversation} from './RuleConversation';
import {apiJson,categoryFor,FEEDBACK_LABELS} from '../rules/library';

export function AssistWorkspace({result,comparisonResult,projectPath,projectFiles,projectName,machineDepartment='All',departments,ruleResults,revision,onSaved,finding,onSourceSaved,onOpenFeature}:{result:any;comparisonResult?:any;projectPath:string;projectFiles:File[];projectName:string;machineDepartment?:string;departments?:string[];ruleResults:any;revision:number;onSaved:()=>void;finding:any;onSourceSaved?:(path:string,name:string)=>void;onOpenFeature?:(feature:string)=>void}){
 const [tab,setTab]=useState('chat');const [learning,setLearning]=useState<any>({});const [answer,setAnswer]=useState('');const [busy,setBusy]=useState(false);const [comment,setComment]=useState('');const [message,setMessage]=useState('');const [draft,setDraft]=useState<any>(null);
 const refresh=useCallback(()=>{void Promise.all([apiJson('/api/rules/learning'),apiJson('/api/rules/features')]).then(([learningData,featureData])=>setLearning({...learningData,featureFiles:featureData.features||[],pipeline:featureData.pipeline||{}})).catch(e=>setMessage(e.message))},[]);
 const teach=()=>{if(!finding)return;const rule=finding.result.ruleDefinition||finding.rule||{id:finding.result.id,name:finding.result.name,kind:'exact_logic_declaration'};setDraft({version:'4.59',rules:[{...rule,enabled:false}]});setTab('configure')};
 const consumeDraft=useCallback(()=>setDraft(null),[]);
 useEffect(()=>{if(tab==='learning')refresh()},[tab,refresh]);
 useEffect(()=>{
  if(!finding)return;
  let active=true;teach();setBusy(true);setAnswer('');setComment('');setMessage('');
  if(finding.result?.configureOnly){setBusy(false);setAnswer('Review the prefilled rule, run its draft test, then save and enable it.');return}
  apiJson('/api/assist',{question:'Explain this rule result, its evidence, likely cause and corrective action.',learnResult:true,context:{projectPath:finding.projectPath,projectName:finding.projectName,result:finding.result,ruleVersion:finding.rule?.version,category:categoryFor(finding.rule)}})
   .then(data=>{if(active){setAnswer(data.answer||'No explanation returned.');refresh()}}).catch(e=>{if(active)setAnswer(e.message)}).finally(()=>{if(active)setBusy(false)});
  return()=>{active=false};
 },[finding,refresh]);
 const feedback=async(label:string)=>{
  if(!finding)return;setBusy(true);setMessage('');
  try{const r=finding.result;const data=await apiJson('/api/rules/feedback',{ruleId:r.id,ruleVersion:finding.rule?.version,projectName:finding.projectName,resultStatus:r.status,label,comment:comment.trim()||(label==='Correct'?answer:''),evidence:r.evidence,actual:r.actual,expected:r.expected,recommendations:r.recommendations,sourceFiles:r.sourceFiles,ruleDefinition:finding.rule||{},category:categoryFor(finding.rule)});setMessage('Engineer feedback saved to the KnowHub.');refresh();if(data.draftConfig){setDraft(data.draftConfig);setTab('configure')}}catch(e:any){setMessage(e.message)}finally{setBusy(false)}
 };
 return <div className="assistantWorkspace"><div className="pageHead assistantPageHeading"><div><div className="eyebrow">uSOPp WORK HUB</div><h1>{tab==='chat'?'Engineering assistant':tab==='configure'?'Rule configuration':'KnowHub'}</h1><p>{tab==='chat'?<>{projectName||'Your engineering workspace'}<span aria-hidden="true"> · </span>{machineDepartment==='All'?'PLC logic, project changes and validation':machineDepartment}</>:'Configure engineering rules and review approved project knowledge.'}</p></div></div>
  <div className="ruleWorkspaceTabs" role="tablist" aria-label="Assist workspace">{[['chat','Chat',MessageSquare],['configure','Rule configuration',Bot],['learning','KnowHub',BrainCircuit]].map(([key,label,Icon]:any)=><button role="tab" aria-selected={tab===key} key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}><Icon size={15}/>{label}</button>)}</div>
  {message&&<div className="ruleMessage" role="status">{message}</div>}
  <div hidden={tab!=='chat'}>{finding&&<section className="card findingDiscussion"><div className="widgetHead"><b>Chopper / {finding.result.id} / {finding.result.status}</b><span>{finding.projectName}</span></div><p>{busy&&!answer?'Chopper is examining the evidence...':answer}</p><button className="btn primary" onClick={teach}>Teach / configure this rule</button><details><summary>Finding evidence</summary><pre>{JSON.stringify(finding.result.evidence,null,2)}</pre></details><label>Engineer explanation or correction<textarea className="textInput" value={comment} onChange={e=>setComment(e.target.value)} placeholder="Record an approved explanation or correction."/></label><div className="actions">{FEEDBACK_LABELS.map(label=><button className="btn" key={label} disabled={busy||!answer||(['Incorrect','Partially correct'].includes(label)&&!comment.trim())} onClick={()=>feedback(label)}>{label}</button>)}</div></section>}<Chatbot comparisonResult={comparisonResult} result={result} projectPath={projectPath} projectName={projectName} ruleResults={ruleResults} onSourceSaved={onSourceSaved} onOpenFeature={feature=>{if(feature==='learning'||feature==='configure')setTab(feature);else onOpenFeature?.(feature)}}/></div>
  <div hidden={tab!=='configure'}>{finding&&<details className="card"><summary>Finding to teach: {finding.result.id} / {finding.result.status}</summary><RuleLogicEvidence item={finding.result}/></details>}<RuleConversation revision={revision} onSaved={onSaved} draft={draft} onDraftConsumed={consumeDraft} projectPath={finding?.projectPath||projectPath} projectFiles={finding?.projectPath?[]:projectFiles} projectName={projectName} departments={departments}/></div>
  <div hidden={tab!=='learning'}><LearningCenter data={learning} onRefresh={refresh} revision={revision} machineDepartment={machineDepartment} departments={departments} onRulesChanged={onSaved} onEditRule={rule=>{setDraft({version:"4.52",rules:[rule]});setTab("configure")}}/></div>
 </div>;
}
