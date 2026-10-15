import {useEffect,useRef,useState} from 'react';
import {ArrowDown,Download,FileCode2,Info,Search} from 'lucide-react';
import {LadderDiagram} from './LadderDiagram';
import {WorkingExplanation,type WorkingExplanationData,type ExplanationParagraph} from './WorkingExplanation';
import './function-flow.css';

type Fact={text:string;line:number;endLine:number};
type Outcome={when:string[];actions:Fact[];line:number};
type CallExplanation={instance:string;name:string;kind:string;line:number;sourceFile:string;purpose:string;behavior:string[];parameters:{name:string;direction:string;dataType:string;description:string;value?:string}[];statuses:{name:string;value:string;description:string}[];handling:{condition:string;name:string;value:string;description:string}[];references:{title:string;file:string}[];notes:string[];declaration?:string;sequences?:(Sequence&{program:string})[]};
type Step={id:string;number:number;title:string;kind:string;when:string[];actions:Fact[];outcomes:Outcome[];inputConditions?:Outcome[];line:number;endLine:number;evidenceLines:number[];network?:any;disabled?:boolean;call?:{name:string;instance:string;line:number};settings?:{name:string;value:string;line:number}[];dataPath?:string[];explanations?:CallExplanation[]};
type Sequence={id:string;title:string;caption:string;arrowNote:string;steps:Step[];workingExplanation?:WorkingExplanationData};
type Variable={name:string;reads:number[];writes:number[]};
type Flow={sourceFile:string;language:string;lineBasis:string;notice:string;notices:string[];sections:{name:string;sequences:Sequence[];workingExplanation?:WorkingExplanationData}[];sourceLines:string[];variables:Variable[];calls:{name:string;instance:string;line:number;code:string;disabled?:boolean}[];routineInterface?:{name:string;type:string;direction:string;file:string;line:number}[]};
export type FunctionFlows={base:Flow|null;developed:Flow|null};
type FlowSide='base'|'developed';
export type FunctionFlowSelection={side:FlowSide;sectionIndex:number;sequenceIndex:number;stepIndex:number;search:string};

function Facts({items}:{items:Fact[]}){
 return items.length>0?<ul className="workingFacts">{items.map((item,index)=><li key={index}>{item.text}<small>L{item.line}{item.endLine!==item.line?`–${item.endLine}`:''}</small></li>)}</ul>:null;
}

function Outcomes({items}:{items:Outcome[]}){
 return <>{items.map((outcome,index)=><section className="workingOutcome" key={index}><div><b>When</b> <code>{outcome.when.join(' AND ')}</code></div><Facts items={outcome.actions}/>{!outcome.actions.length&&<small>No assignment in this branch.</small>}</section>)}</>;
}

function WorkingStep({step,selected,onSelect,showSource=true}:{step:Step;selected:boolean;onSelect:()=>void;showSource?:boolean}){
 return <article data-step-id={step.id} className={`workingStep ${step.kind} ${selected?'selected':''} ${step.disabled?'disabled':''}`}>
  <header><span className="flowStepNumber">{step.number}</span><h4>{step.title}</h4><button className="workingSourceButton" aria-label={`${showSource?'Show source':'Explain'} step ${step.number}: ${step.title}`} aria-pressed={selected} onClick={onSelect}>{showSource?<FileCode2 size={15}/>:<Info size={15}/>}</button></header>
  {step.disabled&&<p className="functionFlowWarning">Commented network — inactive.</p>}
  <div className="workingTrigger"><b>Trigger</b>{step.when.length?step.when.map((guard,index)=><code key={index}>{guard}</code>):<span>{step.kind==='rung'?'Follow the contacts and branches in this rung.':'At this source position in the task call.'}</span>}</div>
  {step.inputConditions&&<Outcomes items={step.inputConditions}/>}
  <Facts items={step.actions}/>
  <Outcomes items={step.outcomes}/>
  {step.explanations?.filter(item=>!step.call||item.instance!==step.call.instance).map((item,index)=><p className="workingCallPurpose" key={index}><b>{item.instance}{item.instance!==item.name?` / ${item.name}`:''}</b>{item.purpose||'Call binding needs further source or library information.'}</p>)}
  <button className="workingLineButton" onClick={onSelect}>{showSource?`View source: L${step.line}–L${step.endLine}`:'Explain this step'}</button>
 </article>;
}

function CallDetails({info}:{info:CallExplanation}){
 return <section className="workingCallExplanation">
  <h4>{info.instance}{info.instance!==info.name&&<small> / {info.name}</small>}</h4><span className="workingCallKind">{info.kind}{info.declaration?' · Declared instance':''}</span>
  {info.purpose&&<p>{info.purpose}</p>}
  {!!info.behavior.length&&<ul>{info.behavior.map((text,index)=><li key={index}>{text}</li>)}</ul>}
  {(['IN','IN_OUT','OUT'] as const).map(direction=>{
   const parameters=info.parameters.filter(param=>param.direction===direction);if(!parameters.length)return null;
   return <div className="workingCallParameters" key={direction}><h5>{direction==='OUT'?'Outputs':direction==='IN_OUT'?'Inputs / outputs':'Inputs used by this call'}</h5>{parameters.map((param,index)=><div key={index}><b>{param.name}</b><small>{param.dataType}</small>{param.value!==undefined&&<code>{param.value}</code>}<p>{param.description}</p>{param.value===undefined&&direction!=='OUT'&&<small>No explicit value was recovered for this input.</small>}</div>)}</div>;
  })}
  {!!info.handling.length&&<section className="workingStatusHandling"><h5>Status checks in this routine</h5>{info.handling.map((status,index)=><p key={index}><code>{status.condition}</code><span>{status.name} ({status.value}): {status.description}</span></p>)}</section>}
  {!!info.statuses.length&&<details><summary>Documented status codes ({info.statuses.length})</summary>{info.statuses.map((status,index)=><p key={index}><b>{status.name} · {status.value}</b><br/>{status.description}</p>)}</details>}
  {info.sequences?.map((sequence,index)=><details className="workingNestedSequence" key={index} open><summary>Inside {info.name} · {sequence.program}</summary><p>These steps run when the enclosing call executes, using its supplied inputs.</p>{sequence.workingExplanation&&<WorkingExplanation value={sequence.workingExplanation} compact/>}{sequence.steps.map(step=><article key={step.id}><h5>{step.number}. {step.title}</h5>{!!step.when.length&&<div className="workingTrigger"><b>When</b>{step.when.map((value,i)=><code key={i}>{value}</code>)}</div>}{step.inputConditions&&<Outcomes items={step.inputConditions}/>}<Facts items={step.actions}/><Outcomes items={step.outcomes}/>{step.explanations?.map((child,i)=><details key={i}><summary>{child.instance} · {child.kind}</summary><CallDetails info={child}/></details>)}</article>)}</details>)}
  {!!info.references.length&&<details className="workingHelpReferences"><summary>Explanation references</summary>{info.references.map((ref,index)=><p key={index}><b>{ref.title}</b><small>{ref.file}</small></p>)}{info.declaration&&<small>{info.declaration}</small>}</details>}
  {info.notes.filter(note=>!note.startsWith('Behavior from the supplied')).map((note,index)=><p className="workingExplanationNote" key={index}>{note}</p>)}
 </section>;
}

function SourcePanel({flow,step,side}:{flow:Flow;step:Step;side:'base'|'developed'}){
 const evidence=new Set(step.evidenceLines);
 const start=Math.max(1,Math.min(step.line,...step.evidenceLines));
 const end=Math.min(flow.sourceLines.length,Math.max(step.endLine,...step.evidenceLines));
 return <section className="workingSourcePanel">
  <div className="workingPanelTitle">{step.network?'PLC ladder logic':'PLC source logic'}</div>
  <div className="workingSourceMeta"><b>Step {step.number} · {step.title}</b><small>{flow.sourceFile}</small><small>{flow.lineBasis}</small></div>
  {step.network?<LadderDiagram network={step.network} side={side}/>:<pre className="workingSourceCode">{flow.sourceLines.slice(start-1,end).map((line,index)=><span key={index} className={evidence.has(start+index)?'evidence':''}><i>{start+index}</i>{line||' '}</span>)}</pre>}
  <p className="workingSourceHint">Select a step’s source icon to view the corresponding {step.network?'rung':'statements'}. Highlighted lines support its explanation.</p>
 </section>;
}

function StepDetails({step,variables,ladderSide}:{step:Step;variables:Variable[];ladderSide?:FlowSide}){
 const relevant=variables.filter(row=>row.reads.concat(row.writes).some(line=>(line>=step.line&&line<=step.endLine)||step.evidenceLines.includes(line)));
 return <aside className="workingDetailsPanel">
  <div className="workingPanelTitle">Step {step.number} · {step.explanations?.length?'Functions and blocks explained':'Data and variables'}</div>
  {step.network&&ladderSide&&<details className="workingLadderConnections"><summary>Rung connections</summary><LadderDiagram network={step.network} side={ladderSide}/></details>}
  {step.dataPath&&<div className="workingDataPath">{step.dataPath.map((value,index)=><div key={index}><div className="workingPathBox"><code>{value}</code></div>{index<step.dataPath!.length-1&&<div className="flowConnector"><ArrowDown size={19}/></div>}</div>)}<small>Names and direction from this step’s source.</small></div>}
  {step.explanations?.map((info,index)=><CallDetails key={`${info.instance}-${info.line}-${index}`} info={info}/>)}
  {step.call&&!step.explanations?.length&&<section className="workingBlock"><h5>Function / block call</h5><code>{step.call.instance}</code><span>{step.call.name} · L{step.call.line}</span></section>}
  {!!step.settings?.length&&<section className="workingSettings"><h5>Configured values</h5>{step.settings.map(setting=><div key={`${setting.name}-${setting.line}`}><span>{setting.name}</span><code>{setting.value}</code></div>)}</section>}
  <section className="workingVariables"><h5>Variables in this step</h5>{relevant.slice(0,12).map(row=><div key={row.name}><code>{row.name}</code><small>{row.reads.some(line=>line>=step.line&&line<=step.endLine)?'Read':''}{row.reads.some(line=>line>=step.line&&line<=step.endLine)&&row.writes.some(line=>line>=step.line&&line<=step.endLine)?' / ':''}{row.writes.some(line=>line>=step.line&&line<=step.endLine)?'Written':''}</small></div>)}{relevant.length>12&&<small>{relevant.length-12} more in the complete variable list below.</small>}</section>
 </aside>;
}

export function FunctionFlow({sessionId,path,baseLabel,newLabel}:{sessionId:string;path:string;baseLabel:string;newLabel:string}){
 const [data,setData]=useState<FunctionFlows|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();setData(null);setError('');
  fetch(`/api/local/compare/flow/${encodeURIComponent(sessionId)}?path=${encodeURIComponent(path)}`,{signal:controller.signal})
   .then(async response=>{const value=await response.json();if(!response.ok)throw Error(value.detail||'Function flow could not be read.');return value as FunctionFlows})
   .then(setData)
   .catch(e=>{if(e.name!=='AbortError')setError(e.message)});
  return()=>controller.abort();
 },[sessionId,path]);
 if(error)return <div className="functionFlowError" role="alert">{error}</div>;
 if(!data)return <div className="functionFlowLoading" role="status">Reading the routine’s working sequence…</div>;
 return <FunctionFlowView key={`${sessionId}/${path}`} data={data} baseLabel={baseLabel} newLabel={newLabel} downloadUrl={side=>`/api/local/compare/flow/${encodeURIComponent(sessionId)}/export?path=${encodeURIComponent(path)}&side=${side}`}/>;
}

export function FunctionFlowView({data,baseLabel,newLabel,downloadUrl,initialSelection,onSelectionChange,hideMissingSides=false,showSource=true}:{data:FunctionFlows;baseLabel:string;newLabel:string;downloadUrl?:(side:FlowSide)=>string;initialSelection?:FunctionFlowSelection;onSelectionChange?:(selection:FunctionFlowSelection)=>void;hideMissingSides?:boolean;showSource?:boolean}){
 const [side,setSide]=useState<FlowSide>(initialSelection&&data[initialSelection.side]?initialSelection.side:data.developed?'developed':'base');
 const [sectionIndex,setSectionIndex]=useState(initialSelection?.sectionIndex||0),[sequenceIndex,setSequenceIndex]=useState(initialSelection?.sequenceIndex||0),[stepIndex,setStepIndex]=useState(initialSelection?.stepIndex||0),[search,setSearch]=useState(initialSelection?.search||'');
 const onSelection=useRef(onSelectionChange);onSelection.current=onSelectionChange;
 const stepList=useRef<HTMLDivElement>(null);
 useEffect(()=>{onSelection.current?.({side,sectionIndex,sequenceIndex,stepIndex,search})},[side,sectionIndex,sequenceIndex,stepIndex,search]);
 const flow=data[side];
 const section=flow?.sections[Math.min(sectionIndex,flow.sections.length-1)];
 const sequence=section?.sequences?.[Math.min(sequenceIndex,section.sequences.length-1)];
 const step=sequence?.steps[Math.min(stepIndex,sequence.steps.length-1)];
 const variables=flow?.variables.filter(row=>row.name.toLowerCase().includes(search.toLowerCase()))||[];
 function selectWrittenStep(item:ExplanationParagraph){
  const laneIndex=section?.sequences.findIndex(lane=>lane.id===item.sequenceId)??-1;
  const selectedIndex=section?.sequences[laneIndex]?.steps.findIndex(step=>step.id===item.stepId)??-1;
  if(laneIndex<0||selectedIndex<0)return;
  setSequenceIndex(laneIndex);setStepIndex(selectedIndex);
  requestAnimationFrame(()=>Array.from(stepList.current?.querySelectorAll<HTMLElement>('[data-step-id]')||[]).find(element=>element.dataset.stepId===item.stepId)?.scrollIntoView({block:'nearest',behavior:'smooth'}));
 }
 return <div className="functionFlow">
  <div className="functionFlowToolbar">
   <div className="functionFlowSides">{(['base','developed'] as const).filter(value=>!hideMissingSides||data[value]).map(value=><button key={value} className={side===value?'selected':''} disabled={!data[value]} onClick={()=>{setSide(value);setSectionIndex(0);setSequenceIndex(0);setStepIndex(0)}}>{value==='base'?baseLabel:newLabel}</button>)}</div>
   {flow&&<><label>Program <select value={sectionIndex} onChange={event=>{setSectionIndex(Number(event.target.value));setSequenceIndex(0);setStepIndex(0)}}>{flow.sections.map((part,index)=><option key={index} value={index}>{part.name}</option>)}</select></label>{downloadUrl&&<a className="flowDownload" href={downloadUrl(side)}><Download size={14}/> Flow HTML</a>}</>}
  </div>
  {flow&&<>
   <div className="functionFlowIntro"><h3>Working sequence · {section?.name}</h3><small>{flow.language} · {flow.sourceFile} · {flow.lineBasis}</small>{flow.notices.map((notice,index)=><p className="functionFlowWarning" key={index}>{notice}</p>)}</div>
   {!!flow.routineInterface?.length&&<details className="flowRoutineInterface"><summary>Routine inputs and outputs</summary>{flow.routineInterface.map((param,index)=><div key={index}><b>{param.name}</b><code>{param.type}</code><small>{param.direction}</small></div>)}</details>}
   {section?.workingExplanation&&<WorkingExplanation key={`${side}-${sectionIndex}`} value={section.workingExplanation} selectedStepId={step?.id} onSelect={selectWrittenStep}/>}
   <div className="workingSequenceTabs" aria-label="Working sequences">{section?.sequences?.map((lane,index)=><button key={lane.id} aria-pressed={index===sequenceIndex} className={index===sequenceIndex?'selected':''} onClick={()=>{setSequenceIndex(index);setStepIndex(0)}}>{lane.title}<span>{lane.steps.length}</span></button>)}</div>
   {sequence&&step?<>
    <p className="workingSequenceCaption">{sequence.caption}</p>
    {!showSource&&<p className="workingSequenceCaption">Choose “Explain this step” to see input values, outputs, status meanings and the sequence inside a project function.</p>}
    <div className={`workingSequenceLayout ${showSource?'':'explanationOnly'}`}>
     {showSource&&<SourcePanel flow={flow} step={step} side={side}/>}
     <main className="workingSequenceSteps"><div className="workingPanelTitle">Working sequence · Step by step</div><div className="workingStepList" ref={stepList}>{sequence.steps.map((item,index)=><div key={item.id}><WorkingStep step={item} selected={item.id===step.id} showSource={showSource} onSelect={()=>setStepIndex(index)}/>{index<sequence.steps.length-1&&<div className="workingSequenceArrow"><ArrowDown size={24}/><small>Check the next trigger</small></div>}</div>)}</div><p className="workingSourceHint">{sequence.arrowNote}</p></main>
     <StepDetails step={step} variables={flow.variables} ladderSide={showSource?undefined:side}/>
    </div>
   </>:<p>No executable working steps were extracted from this program section.</p>}
   <p className="functionFlowNotice">{flow.notice}</p>
   <details className="flowAllVariables"><summary>All variables and source references ({flow.variables.length})</summary><label className="flowVariableSearch"><Search size={14}/><input aria-label="Filter flow variables" placeholder="Search variable name" value={search} onChange={event=>setSearch(event.target.value)}/></label><div className="flowVariableTable"><table><thead><tr><th>Variable</th><th>Read at lines</th><th>Written at lines</th></tr></thead><tbody>{variables.map(row=><tr key={row.name}><td><code>{row.name}</code></td><td>{row.reads.map(line=>`L${line}`).join(', ')||'—'}</td><td>{row.writes.map(line=>`L${line}`).join(', ')||'—'}</td></tr>)}</tbody></table></div></details>
   <details className="flowCalls"><summary>All function calls ({flow.calls.length})</summary>{flow.calls.map((call,index)=><div key={index}><code>{call.instance}{call.instance!==call.name?` / ${call.name}`:''}</code><small>L{call.line}{call.disabled?' · Commented network':''}</small>{showSource&&<code>{call.code}</code>}</div>)}</details>
  </>}
 </div>;
}
