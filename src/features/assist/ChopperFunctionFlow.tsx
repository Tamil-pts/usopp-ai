import {useEffect,useRef,useState} from 'react';
import {FileCode2,Maximize2,Search,X} from 'lucide-react';
import {FunctionFlowView,type FunctionFlows,type FunctionFlowSelection} from '../compare/FunctionFlow';
import './chopper-flow.css';

type FlowRequest={projectPath?:string;comparisonSessionId?:string};
type Routine={path:string;name:string;language:string};
type Catalog={projectLabel:string;baseLabel:string;newLabel:string;sourceKind:string;candidates:Routine[];total:number;matched:number;offset:number;limit:number;query:string};
type OpenFlow={view:FunctionFlows;snapshotId:string;selectedPath:string;baseLabel:string;newLabel:string};
export type ChopperFlowData=Catalog&Partial<OpenFlow>&{request:FlowRequest};

export function flowConversationText(view:FunctionFlows){
 return (['base','developed'] as const).flatMap(side=>{
  const flow=view[side];if(!flow)return [];
  return [`${side}: ${flow.sourceFile} (${flow.lineBasis})`,...flow.sections.flatMap(section=>[
   ...(section.workingExplanation?[section.workingExplanation.intro,...section.workingExplanation.paragraphs.map(item=>`${item.text} [${item.sourceFile}:${item.line}]`),...section.workingExplanation.notes]:[]),
   ...section.sequences.flatMap(sequence=>[
   `${section.name} / ${sequence.title}`,...sequence.steps.flatMap(step=>[
    `Step ${step.number}: ${step.title}. When: ${step.when.join(' AND ')||'At its source position'}.`,
    ...step.actions.map(item=>`${item.text} [${flow.sourceFile}:${item.line}]`),
    ...step.explanations?.flatMap(info=>[`${info.instance} / ${info.name}: ${info.purpose}`,...info.behavior,...info.parameters.map(param=>`${param.direction} ${param.name} (${param.dataType})${param.value!==undefined?` = ${param.value}`:''}: ${param.description}`),...info.handling.map(status=>`${status.condition}: ${status.name} ${status.value}: ${status.description}`),...info.references.map(ref=>`Reference: ${ref.file}`)])||[],
    ...step.outcomes.flatMap(outcome=>[`When ${outcome.when.join(' AND ')}:`,...outcome.actions.map(item=>`${item.text} [${flow.sourceFile}:${item.line}]`)])
   ])
  ])])];
 }).join('\n');
}

async function flowRequest<T>(action:'catalog'|'open',body:unknown,signal:AbortSignal):Promise<T>{
 const response=await fetch(`/api/assist/flow/${action}`,{method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await response.json().catch(()=>({}));
 if(response.status===404||response.status===405)throw Error(typeof data.detail==='string'&&data.detail!=='API endpoint not found'?data.detail:'Restart the updated development app to load Chopper function flows.');
 if(!response.ok)throw Error(data.detail||'The routine flow could not be read.');
 return data as T;
}

export function ChopperFunctionFlow({data,onOpened}:{data:ChopperFlowData;onOpened?:(opened:OpenFlow)=>void}){
 const [catalog,setCatalog]=useState<Catalog>(data),[query,setQuery]=useState(data.query||''),[offset,setOffset]=useState(0);
 const [opened,setOpened]=useState<OpenFlow|null>(data.view&&data.snapshotId&&data.selectedPath?data as OpenFlow:null);
 const [loading,setLoading]=useState(false),[searching,setSearching]=useState(false),[error,setError]=useState(''),[expanded,setExpanded]=useState(false);
 const [pickerOpen,setPickerOpen]=useState(!opened);
 const firstCatalog=useRef(true),activeRequest=useRef<AbortController|null>(null),dialog=useRef<HTMLDialogElement>(null),expandButton=useRef<HTMLButtonElement>(null);
 const viewSelection=useRef<FunctionFlowSelection|undefined>(undefined);
 useEffect(()=>()=>activeRequest.current?.abort(),[]);
 useEffect(()=>{
  if(firstCatalog.current){firstCatalog.current=false;return;}
  const abort=new AbortController();
  const timer=setTimeout(()=>{
   setSearching(true);setError('');
   flowRequest<Catalog>('catalog',{...data.request,query,offset,limit:data.limit},abort.signal)
    .then(setCatalog).catch(reason=>{if(reason.name!=='AbortError')setError(reason.message)})
    .finally(()=>{if(!abort.signal.aborted)setSearching(false)});
  },250);
  return()=>{clearTimeout(timer);abort.abort()};
 },[query,offset,data.request,data.limit]);
 useEffect(()=>{
  if(expanded&&!dialog.current?.open)dialog.current?.showModal();
  if(!expanded&&dialog.current?.open)dialog.current.close();
 },[expanded]);
 async function openRoutine(path:string){
  activeRequest.current?.abort();const abort=new AbortController();activeRequest.current=abort;
  setLoading(true);setError('');
  try{
   const value=await flowRequest<OpenFlow>('open',{...data.request,routinePath:path},abort.signal);
   if(!abort.signal.aborted){viewSelection.current=undefined;setOpened(value);setPickerOpen(false);onOpened?.(value)}
  }catch(reason:any){if(reason.name!=='AbortError')setError(reason.message)}
  finally{if(!abort.signal.aborted)setLoading(false)}
 }
 const activeFlow=opened?.view.developed||opened?.view.base;
 const initialSelection=viewSelection.current||{side:opened?.view.developed?'developed' as const:'base' as const,sectionIndex:Math.max(0,activeFlow?.sections.findIndex(section=>/^_?CYCLIC$/i.test(section.name))??0),sequenceIndex:0,stepIndex:0,search:''};
 const view=opened?<FunctionFlowView key={opened.snapshotId} data={opened.view} baseLabel={opened.baseLabel} newLabel={opened.newLabel} initialSelection={initialSelection} onSelectionChange={selection=>{viewSelection.current=selection}} hideMissingSides showSource={false} downloadUrl={side=>`/api/assist/flow/export/${encodeURIComponent(opened.snapshotId)}?side=${side}`}/>:null;
 return <section className="chopperFunctionFlow" aria-label="Chopper routine function flow">
  <header className="chopperFlowHeader"><FileCode2 size={18}/><div><b>Routine function flow</b><small>{data.projectLabel}{data.sourceKind==='comparison'?' · MatchView saved sources':' · Selected project'}</small></div>{opened&&<button className="btn" ref={expandButton} onClick={()=>setExpanded(true)}><Maximize2 size={14}/> Expand flow</button>}</header>
  <details className="chopperRoutinePicker" open={pickerOpen} onToggle={event=>setPickerOpen(event.currentTarget.open)}>
   <summary>{opened?`Choose another routine · ${opened.selectedPath}`:'Choose a PLC routine'}</summary>
   <label className="chopperRoutineSearch"><Search size={15}/><input aria-label="Search PLC routines" placeholder="Search name or path, e.g. ip_add" value={query} onChange={event=>{setQuery(event.target.value);setOffset(0)}}/>{query&&<button aria-label="Clear routine search" onClick={()=>{setQuery('');setOffset(0)}}><X size={14}/></button>}</label>
   <div className="chopperRoutineList" aria-busy={searching}>
    {!catalog.candidates.length&&<p>{catalog.total?'No matching routines. Try another name or clear the search.':'No supported PLC implementation files were found in this project.'}</p>}
    {catalog.candidates.map(routine=><button key={routine.path} disabled={loading||searching} onClick={()=>void openRoutine(routine.path)} aria-label={`Show function flow for ${routine.path}`}><FileCode2 size={15}/><span><b>{routine.name}</b><small>{routine.path}</small></span><em>{routine.language}</em></button>)}
   </div>
   <div className="chopperRoutinePaging"><small>{searching?'Searching routines…':catalog.matched?`${catalog.offset+1}–${Math.min(catalog.offset+catalog.candidates.length,catalog.matched)} of ${catalog.matched} routines`:'0 matching routines'}</small>{(catalog.offset>0||catalog.matched>catalog.limit)&&<><button className="btn" disabled={searching||catalog.offset===0} onClick={()=>setOffset(Math.max(0,catalog.offset-catalog.limit))}>Previous</button><button className="btn" disabled={searching||catalog.offset+catalog.limit>=catalog.matched} onClick={()=>setOffset(catalog.offset+catalog.limit)}>Next</button></>}</div>
  </details>
  {error&&<p className="chopperFlowError" role="alert">{error}</p>}
  {loading&&<p className="chopperFlowLoading" role="status">Reading the complete routine and building its working steps…</p>}
  {opened&&!expanded&&<div className="chopperInlineFlow">{view}</div>}
  <dialog ref={dialog} className="chopperFlowDialog" onClose={()=>{setExpanded(false);expandButton.current?.focus()}}>
   <header><div><b>Routine function flow</b><small>{opened?.selectedPath}</small></div><button className="btn" aria-label="Close expanded function flow" onClick={()=>setExpanded(false)}><X size={18}/> Close</button></header>
   {expanded&&view}
  </dialog>
 </section>;
}
