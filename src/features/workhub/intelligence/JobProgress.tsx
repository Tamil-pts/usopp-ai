import {useState} from 'react';
import {LoaderCircle} from 'lucide-react';
import type {HubRow as Row} from '../projectApi';
import './job-progress.css';

export function JobProgress({job,onRetry,onCancel,onOpen}:{job:Row;onRetry:()=>Promise<unknown>;onCancel:()=>Promise<unknown>;onOpen?:()=>void}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const active=['queued','running'].includes(job.status);
 const status=job.display_status||(active?'Processing':job.status==='completed'?'Completed':job.status==='cancelled'?'Cancelled':'Failed');
 const act=async(action:()=>Promise<unknown>)=>{setBusy(true);setError('');try{await action();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <article className="wh-job" aria-label={status+' background job'}>
  <div className="wh-job-body"><div className="wh-job-heading">{active&&<LoaderCircle size={14} className="spin"/>}<strong>{job.stage||status}</strong><span className={'pi-status '+job.status}>{status}</span></div>
   {active&&<><progress value={job.progress||0} max={100} aria-label="Processing progress"/><small>{job.cancel_requested?'Cancellation requested — stopping the worker safely.':job.status==='queued'?'Queued. You can continue working.':String(job.progress||0)+'% · You can continue working.'}</small></>}
   {job.status==='completed'&&<small>Completed{job.duration_ms?' in '+(job.duration_ms/1000).toFixed(1)+' seconds':''}. Generated engineering documents remain subject to review.</small>}
   {job.error&&<p role="status">{job.error}</p>}{!job.can_retry&&job.retry_reason&&['failed','blocked','cancelled'].includes(job.status)&&<small>{job.retry_reason}</small>}
   {job.source_changed&&<small>Source revisions changed. This historical result needs a fresh preparation.</small>}
   {error&&<p role="alert">{error}</p>}
  </div><div className="actions">{job.status==='completed'&&job.result?.download_url&&<a className="btn" href={job.result.download_url}>Download {job.result.filename||'export'}</a>}{onOpen&&<button className="btn" onClick={onOpen}>Open result</button>}{job.can_retry&&<button className="btn" disabled={busy} onClick={()=>void act(onRetry)}>Retry</button>}{job.can_cancel&&<button className="btn" disabled={busy} onClick={()=>void act(onCancel)}>Cancel</button>}</div>
 </article>;
}
