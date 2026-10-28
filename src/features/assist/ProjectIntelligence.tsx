import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react';
import {Bot,ChevronDown,Cpu,Database,Link2,RefreshCw,Search,Square} from 'lucide-react';
import './project-intelligence.css';

async function request(path:string,body?:unknown,signal?:AbortSignal){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal,cache:'no-store'});
 const data=await response.json();if(!response.ok)throw new Error(data.detail||'Project Intelligence is unavailable.');return data;
}
export function useProjectIntelligence(path:string){
 const [state,setState]=useState<any>(null),[error,setError]=useState('');const active=useRef(0);
 const refresh=useCallback(async(mode='refresh')=>{
  if(!path)return;const turn=++active.current;setError('');
  try{const data=await request('/api/assist/projects/index',{projectPath:path,mode});if(turn===active.current)setState(data)}catch(reason){if(turn===active.current)setError(reason instanceof Error?reason.message:'Indexing failed.')}
 },[path]);
 useEffect(()=>{setState(null);setError('');if(path)void refresh();return()=>{active.current++}},[path,refresh]);
 useEffect(()=>{if(!state?.projectId||!state?.running)return;let alive=true;const poll=()=>request(`/api/assist/projects/${state.projectId}`).then(value=>{if(alive)setState(value)}).catch(reason=>{if(alive)setError(reason.message)});const timer=setInterval(()=>void poll(),1500);return()=>{alive=false;clearInterval(timer)}},[state?.projectId,state?.running]);
 const cancel=async()=>{try{await request(`/api/assist/projects/${state.projectId}/cancel`,{});setState((current:any)=>({...current,stage:'Finishing current file and cancelling…'}))}catch(reason:any){setError(reason.message)}};
 return {state,error,refresh,cancel};
}
export function ProjectIntelligence({project}:{project:ReturnType<typeof useProjectIntelligence>}){
 const {state,error,refresh,cancel}=project;
 const [symbolQuery,setSymbolQuery]=useState(''),[searchedSymbolQuery,setSearchedSymbolQuery]=useState(''),[symbolResults,setSymbolResults]=useState<any[]>([]),[symbolError,setSymbolError]=useState(''),[symbolBusy,setSymbolBusy]=useState(false);
 const searchSymbols=async(event:FormEvent<HTMLFormElement>)=>{
  event.preventDefault();if(!state?.projectId||!symbolQuery.trim())return;setSymbolBusy(true);setSymbolError('');setSearchedSymbolQuery(symbolQuery.trim());
  try{const result=await request(`/api/assist/projects/${encodeURIComponent(state.projectId)}/symbols?q=${encodeURIComponent(symbolQuery.trim())}&limit=60`);setSymbolResults(result.symbols||[])}
  catch(reason){setSymbolError(reason instanceof Error?reason.message:'Variable search failed.');setSymbolResults([])}
  finally{setSymbolBusy(false)}
 };
 return <details className="projectIntelligence">
  <summary aria-label="Expand or collapse Project Intelligence"><Database size={17}/><b>Project Intelligence</b><span>{state?`${state.projectName} · ${state.ready?'Ready':state.phase} · ${state.indexedFiles||0} indexed${state.running&&state.percentage!=null?` · ${state.percentage}%`:''}`:'Select or attach a project to begin'}{error?' · Needs attention':''}</span><ChevronDown size={16} className="intelligenceChevron"/></summary>
  {error&&<p role="alert">{error}</p>}{state&&<div className="intelligenceBody"><div className="intelligenceStage"><span>{state.stage}</span><span>{state.elapsedSeconds||0}s</span></div><progress max={100} value={state.percentage??undefined}/><small>{state.percentage==null?'Discovering files':`${state.percentage}% indexed`} · {state.running?'Working locally':state.ready?'Ready for questions':'Analysis incomplete'}</small>
  <div className="intelligenceCounts">{[['Total files',state.totalFiles],['Excluded',state.excludedFiles],['Indexed',state.indexedFiles],['Failed',state.failedFilesCount],['Programs',state.programs],['Variables',state.variables],['Functions',state.functions],['Data types',state.dataTypes],['Block instances',state.blockInstances],['Function blocks',state.functionBlocks],['Dependencies',state.dependencies],['Unchanged',state.unchangedFiles],['Updated',state.changedFiles],['Removed',state.removedFiles]].map(([label,value])=><div key={String(label)}><b>{Number(value||0).toLocaleString()}</b><span>{label}</span></div>)}</div>
  <details className="intelligenceDetails"><summary><Cpu size={15}/>Project structure and linked evidence</summary><div className="intelligenceDetailsBody">
   <div className="intelligenceHardwareGrid">
    <div><span>Automation Studio</span><b>{state.projectDetails?.automationStudioVersion||'Not identified'}</b></div>
    <div><span>Active configuration</span><b>{state.projectDetails?.activeConfiguration||'Not identified'}</b></div>
    <div><span>PLC type</span><b>{state.projectDetails?.plcType||'Not identified'}</b></div>
    <div><span>HMI project</span><b>{state.projectDetails?.screenFolder||'Not identified'}</b></div>
    <div><span>HMI panel type</span><b>{state.projectDetails?.screenType||'Not identified'}</b></div>
    <div><span>Configuration status</span><b>{state.projectDetails?.configurationStatus||'Not available'}</b></div>
   </div>
   {state.projectDetails?.configurationMessage&&<p className="intelligenceNotice">{state.projectDetails.configurationMessage}</p>}
   {!!state.projectDetails?.logicScopeMessage&&<p className="intelligenceNotice">{state.projectDetails.logicScopeMessage}</p>}
   <div className="intelligenceInventory"><b>Indexed source inventory</b>{Object.entries(state.fileCategories||{}).map(([category,count])=><span key={category}>{category}: {Number(count).toLocaleString()}</span>)}</div>
   <div className="intelligenceRelations"><b>Source relationships</b>
    <span>Function calls: {Number(state.callResolution?.found||0).toLocaleString()} found; {Number(state.callResolution?.matchedToLocalDeclaration||0).toLocaleString()} matched to local declarations.</span>
    <span>HMI bindings: {Number(state.hmiResolution?.bindings||0).toLocaleString()} found; {Number(state.hmiResolution?.notMatchedToVariableDeclaration||0).toLocaleString()} did not match an indexed variable declaration.</span>
    <span>I/O bindings: {Number(state.relationshipCounts?.['io-binding']||0).toLocaleString()} source mappings indexed.</span>
    <small>Unmatched calls can be library or external functions. Unmatched HMI names need review; they are not automatically treated as PLC faults.</small>
   </div>
   {!!state.taskHierarchy?.length&&<details className="intelligenceTaskDetails"><summary>Task and program hierarchy ({state.taskHierarchy.length})</summary><div className="intelligenceTableWrap"><table><thead><tr><th>Task</th><th>Program source</th><th>Configuration</th><th>Status</th><th>Source reference</th></tr></thead><tbody>{state.taskHierarchy.map((task:any,index:number)=><tr key={`${task.configuration}-${task.name}-${index}`}><td>{task.name||'Unnamed task'}</td><td>{task.source||'Source not declared'}</td><td>{task.configuration||'Not mapped'}</td><td>{task.enabled?'Enabled':'Disabled'}{task.activeConfiguration?' · active configuration':''}</td><td><code>{task.file}:{task.line}</code></td></tr>)}</tbody></table></div></details>}
   <details className="intelligenceMappings"><summary><Link2 size={14}/>Sample HMI and I/O links</summary><div className="intelligenceMappingLists">
    <div><b>HMI datapoints</b>{(state.hmiMappings||[]).map((item:any,index:number)=><p key={`hmi-${index}`}><code>{item.file}:{item.line}</code><span>{item.a} → {item.b}</span><small>{item.detail}</small></p>)}</div>
    <div><b>Physical I/O</b>{(state.ioMappings||[]).map((item:any,index:number)=><p key={`io-${index}`}><code>{item.file}:{item.line}</code><span>{item.a} → {item.detail||item.b}</span></p>)}</div>
   </div></details>
   <form className="intelligenceSymbolSearch" onSubmit={searchSymbols}><label htmlFor="chopper-symbol-search">Search indexed variables and functions</label><div><input id="chopper-symbol-search" value={symbolQuery} onChange={event=>setSymbolQuery(event.target.value)} placeholder="Variable, function or block name"/><button className="btn" type="submit" disabled={symbolBusy||!symbolQuery.trim()}><Search size={14}/>{symbolBusy?'Searching…':'Search index'}</button></div></form>
   {symbolError&&<p role="alert" className="intelligenceNotice">{symbolError}</p>}{symbolResults.length>0&&<div className="intelligenceTableWrap"><table><thead><tr><th>Symbol</th><th>Kind / type</th><th>Scope</th><th>References</th><th>Declaration</th></tr></thead><tbody>{symbolResults.map((symbol:any,index:number)=><tr key={`${symbol.file}-${symbol.line}-${index}`}><td>{symbol.display||symbol.name}</td><td>{symbol.kind}{symbol.datatype?` · ${symbol.datatype}`:''}</td><td>{symbol.scope}</td><td>Read {symbol.reads||0} · Write {symbol.writes||0} · Call {symbol.calls||0}</td><td><code>{symbol.file}:{symbol.line}</code></td></tr>)}</tbody></table></div>}
   {searchedSymbolQuery===symbolQuery.trim()&&searchedSymbolQuery&&!symbolBusy&&!symbolError&&symbolResults.length===0&&<small>No declarations match this search.</small>}
  </div></details>
  <div className="actions"><button className="btn" disabled={state.running} onClick={()=>void refresh()}><RefreshCw size={13}/>Refresh changes</button><button className="btn" disabled={state.running} onClick={()=>void refresh('rebuild')}>Rebuild index</button><button className="btn" disabled={state.running} onClick={()=>void refresh('retry')}>Retry failed files</button><button className="btn" disabled={!state.running} onClick={()=>void cancel()}><Square size={12}/>Cancel indexing</button></div><small>Temp, Binaries, Diagnosis, AS, caches and generated folders are excluded. Knowledge stays on this server when you start a new chat. Refresh after editing project files.</small>
  {!!state.failedFiles?.length&&<details><summary>Failed files ({state.failedFilesCount})</summary>{state.failedFiles.map((file:any)=><p key={file.path}><code>{file.path}</code> · {file.error}</p>)}</details>}</div>}
 </details>;
}
export function ContextUsage({retrieval}:{usage?:any;retrieval?:any}){
 if(!retrieval?.files?.length)return null;
 return <details className="chopperContextUsage"><summary>Source references ({retrieval.files.length})</summary>{retrieval.files.map((file:any,index:number)=><p key={index}><code>[{file.sourceId}] {file.file}:{file.line}-{file.endLine}</code></p>)}</details>;
}
