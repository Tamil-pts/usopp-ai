import {useEffect,useState} from 'react';
import {Database,RefreshCw} from 'lucide-react';
import {apiJson} from '../rules/library';

export function SemanticIndexControl({projectId}:{projectId:string}){
 const [state,setState]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const endpoint='/api/assist/projects/'+encodeURIComponent(projectId);
 useEffect(()=>{let active=true;setState(null);setError('');apiJson(endpoint+'/semantic-status').then(value=>{if(active)setState(value)}).catch(reason=>{if(active)setError(reason.message)});return()=>{active=false}},[endpoint]);
 useEffect(()=>{if(!state?.running)return;let active=true;const timer=setInterval(()=>apiJson(endpoint+'/semantic-status').then(value=>{if(active)setState(value)}).catch(reason=>{if(active)setError(reason.message)}),1500);return()=>{active=false;clearInterval(timer)}},[endpoint,state?.running]);
 async function action(build:boolean){setBusy(true);setError('');try{setState(await apiJson(endpoint+(build?'/semantic-build':'/semantic-status'),build?{}:undefined))}catch(reason:any){setError(reason.message)}finally{setBusy(false)}}
 return <div className="intelligenceSemantic" aria-label="Project semantic retrieval"><div><b><Database size={14}/> Local semantic index</b><small>{state?.running?`Embedding ${state.chunks||0} / ${state.totalChunks||'…'} source chunks`:state?.ready?`${state.chunks} indexed chunks · source-linked`:state?.message||'Build after indexing the source files. Install retrieval models in Settings → AI & Chopper.'}</small></div><div className="actions"><button className="btn" disabled={busy||state?.running} onClick={()=>void action(true)}>{state?.running?'Building…':state?.ready?'Rebuild semantic index':'Build semantic index'}</button><button className="btn" disabled={busy} onClick={()=>void action(false)} aria-label="Refresh semantic index status"><RefreshCw size={14}/></button></div>{(error||state?.error)&&<p role="alert">{error||state.error}</p>}<small>This improves candidate retrieval. Parser gaps and machine-sequence proofs remain explicitly unresolved.</small></div>;
}
