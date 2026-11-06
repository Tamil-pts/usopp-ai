import {useEffect,useState} from 'react';
import {Database,Download,RefreshCw} from 'lucide-react';
import {apiJson} from '../rules/library';

export function SemanticRetrievalSettings(){
 const [state,setState]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;const poll=()=>apiJson('/api/assist/model/retrieval').then(value=>{if(active)setState(value)}).catch(reason=>{if(active)setError(reason.message)});void poll();const timer=setInterval(()=>void poll(),5000);return()=>{active=false;clearInterval(timer)};},[]);
 async function action(path:string,body:any){const previous=state;setBusy(true);setError('');if(path==='/api/assist/model/retrieval')setState((current:any)=>({...current,...body}));try{setState(await apiJson(path,body))}catch(reason:any){setState(previous);setError(reason.message)}finally{setBusy(false)}}
 const installing=state?.installation?.phase==='downloading';
 return <section className="assistSemanticSettings" aria-label="Local semantic retrieval settings"><h3><Database size={20}/> Local semantic retrieval</h3>
  <p>Find engineering evidence by meaning as well as exact PLC tags. Existing BM25 and graph tracing stay active. Source checks decide what can be published.</p>
  {state&&<><label className="modelStartup"><input type="checkbox" checked={state.enabled} disabled={busy} onChange={event=>void action('/api/assist/model/retrieval',{enabled:event.target.checked})}/><span><b>Enable local hybrid retrieval</b><small>Build each project's semantic index in Chat → Project Intelligence after indexing its files.</small></span></label>
   <label className="modelStartup"><input type="checkbox" checked={state.rerank} disabled={busy} onChange={event=>void action('/api/assist/model/retrieval',{rerank:event.target.checked})}/><span><b>Rerank retrieved candidates locally</b><small>Exact PLC tags and explicit source-file matches remain first. Similarity scores do not establish PLC behaviour.</small></span></label>
   <div className="modelCpuChoices">{state.models.map((model:any)=><div key={model.kind}><b>{model.kind==='embedding'?'BGE-small embeddings':'Jina tiny reranker'}</b><small>{model.installed?'Installed':'Not installed'} · {(model.size/1e6).toFixed(1)} MB · {model.license}{model.running?' · Running locally':''}</small><small>{model.repository}</small></div>)}</div>
   <div className="actions"><button className="btn" disabled={busy||installing} onClick={()=>void action('/api/assist/model/retrieval/install',{})}><Download size={15}/>{installing?'Installing retrieval models…':state.models.every((model:any)=>model.installed)?'Verify installed retrieval models':'Install retrieval models (73.4 MB)'}</button><button className="btn" disabled={busy} onClick={()=>void apiJson('/api/assist/model/retrieval').then(setState).catch(reason=>setError(reason.message))}><RefreshCw size={15}/>Refresh</button></div>
   {installing&&<p role="status">Downloading verified model files: {(state.installation.downloaded/1e6).toFixed(1)} / 73.4 MB. Project files are not part of this download.</p>}
   <p><small>Queries use loopback CPU services and never download models. Missing, stale or busy retrieval models produce an explicit notice and retain lexical/graph search.</small></p>
   {state.installation.error&&<p role="alert" className="failText">{state.installation.error}</p>}</>}
  {error&&<p role="alert" className="failText">{error}</p>}
 </section>;
}
