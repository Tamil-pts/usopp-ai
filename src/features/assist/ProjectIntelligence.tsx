import {useCallback,useEffect,useRef,useState} from 'react';
import {Bot,ChevronDown,Database,RefreshCw,Square} from 'lucide-react';
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
 return <details className="projectIntelligence">
  <summary aria-label="Expand or collapse Project Intelligence"><Database size={17}/><b>Project Intelligence</b><span>{state?`${state.projectName} · ${state.ready?'Ready':state.phase} · ${state.indexedFiles||0} indexed${state.running&&state.percentage!=null?` · ${state.percentage}%`:''}`:'Select or attach a project to begin'}{error?' · Needs attention':''}</span><ChevronDown size={16} className="intelligenceChevron"/></summary>
  {error&&<p role="alert">{error}</p>}{state&&<div className="intelligenceBody"><div className="intelligenceStage"><span>{state.stage}</span><span>{state.elapsedSeconds||0}s</span></div><progress max={100} value={state.percentage??undefined}/><small>{state.percentage==null?'Discovering files':`${state.percentage}% indexed`} · {state.running?'Working locally':state.ready?'Ready for questions':'Analysis incomplete'}</small>
  <div className="intelligenceCounts">{[['Total files',state.totalFiles],['Excluded',state.excludedFiles],['Indexed',state.indexedFiles],['Failed',state.failedFilesCount],['Programs',state.programs],['Variables',state.variables],['Functions',state.functions],['Data types',state.dataTypes],['Block instances',state.blockInstances],['Function blocks',state.functionBlocks],['Dependencies',state.dependencies],['Unchanged',state.unchangedFiles],['Updated',state.changedFiles],['Removed',state.removedFiles]].map(([label,value])=><div key={String(label)}><b>{Number(value||0).toLocaleString()}</b><span>{label}</span></div>)}</div>
  <div className="actions"><button className="btn" disabled={state.running} onClick={()=>void refresh()}><RefreshCw size={13}/>Refresh changes</button><button className="btn" disabled={state.running} onClick={()=>void refresh('rebuild')}>Rebuild index</button><button className="btn" disabled={state.running} onClick={()=>void refresh('retry')}>Retry failed files</button><button className="btn" disabled={!state.running} onClick={()=>void cancel()}><Square size={12}/>Cancel indexing</button></div><small>Temp, Binaries, Diagnosis, AS, caches and generated folders are excluded. Knowledge stays on this server when you start a new chat. Refresh after editing project files.</small>
  {!!state.failedFiles?.length&&<details><summary>Failed files ({state.failedFilesCount})</summary>{state.failedFiles.map((file:any)=><p key={file.path}><code>{file.path}</code> · {file.error}</p>)}</details>}</div>}
 </details>;
}
export function ContextUsage({retrieval}:{usage?:any;retrieval?:any}){
 if(!retrieval?.files?.length)return null;
 return <details className="chopperContextUsage"><summary>Source references ({retrieval.files.length})</summary>{retrieval.files.map((file:any,index:number)=><p key={index}><code>[{file.sourceId}] {file.file}:{file.line}-{file.endLine}</code></p>)}</details>;
}
