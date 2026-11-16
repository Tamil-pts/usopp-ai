import {createContext,useContext,useEffect,useRef,useState,type FormEvent,type ReactNode} from 'react';
import {Download,X} from 'lucide-react';
import {useAccount} from '../features/account/AuthProvider';
import './report-export.css';

export type ReportCover={projectId?:string;department?:string;base?:string;developed?:string;objectiveScope?:string;reviewedBy?:string;projectName:string;description:string;validatedBy:string;validationDetails:string;approvedBy:string;date:string};
type ExportRequest={title:string;projectName:string;format:'html'|'pdf';onExport:(cover:ReportCover)=>Promise<void>};
const Context=createContext<((request:ExportRequest)=>void)|null>(null);
export function useReportExport(){const request=useContext(Context);if(!request)throw new Error('Report export provider is missing');return request;}
const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};

export async function downloadReport(path:string,filename:string,cover:ReportCover){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cover)});
  if(!response.ok){let detail='';try{const data=await response.json();detail=typeof data.detail==='string'?data.detail:'';}catch{}
    throw new Error(detail||`Report export failed (${response.status}). Check that the updated server is running.`);}
  const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=(response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1]||filename).replace(/[\\/:*?"<>|]/g,'_');document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
}

export function ReportExportProvider({children}:{children:ReactNode}){
  const {user}=useAccount();const [request,setRequest]=useState<ExportRequest|null>(null);
  const [cover,setCover]=useState<ReportCover>({projectName:'',description:'',validatedBy:'',validationDetails:'',approvedBy:'',date:today()});
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const dialog=useRef<HTMLDialogElement>(null);const running=useRef(false);
  useEffect(()=>{if(request&&!dialog.current?.open)dialog.current?.showModal();},[request]);
  const open=(next:ExportRequest)=>{if(running.current)return;setCover({projectName:next.projectName,description:'',validatedBy:user.username,validationDetails:'',approvedBy:'',date:today()});setError('');setRequest(next);};
  const close=()=>{if(running.current)return;dialog.current?.close();setRequest(null);};
  const submit=async(event:FormEvent)=>{event.preventDefault();if(!request||running.current)return;running.current=true;setBusy(true);setError('');
    try{await request.onExport(cover);dialog.current?.close();setRequest(null);}catch(e){setError(e instanceof Error?e.message:'Could not export the report.');}finally{running.current=false;setBusy(false);}};
  const update=(key:keyof ReportCover,value:string)=>setCover(previous=>({...previous,[key]:value}));
  return <Context.Provider value={open}>{children}{request&&<dialog ref={dialog} className="reportExportDialog" onCancel={event=>{event.preventDefault();close();}}>
    <form onSubmit={submit} aria-busy={busy}><header><div><span className="eyebrow">RESULTVIEW EXPORT</span><h2>Report cover details</h2><p>{request.title} · {request.format.toUpperCase()}</p></div><button type="button" className="btn" disabled={busy} onClick={close} aria-label="Close export"><X size={18}/></button></header>
      <div className="reportCoverFields"><label>Project name<input autoFocus required maxLength={200} value={cover.projectName} onChange={e=>update('projectName',e.target.value)} disabled={busy}/></label>
      <label>Description<textarea rows={3} maxLength={2000} value={cover.description} onChange={e=>update('description',e.target.value)} disabled={busy}/></label>
      <div className="reportCoverPair"><label>Validated by<input maxLength={200} value={cover.validatedBy} onChange={e=>update('validatedBy',e.target.value)} disabled={busy}/></label><label>Date<input required type="date" value={cover.date} onChange={e=>update('date',e.target.value)} disabled={busy}/></label></div>
      <label>Validation details<textarea rows={4} maxLength={4000} value={cover.validationDetails} onChange={e=>update('validationDetails',e.target.value)} disabled={busy}/></label>
      <label>Approved by<input maxLength={200} value={cover.approvedBy} onChange={e=>update('approvedBy',e.target.value)} disabled={busy}/><small>Leave blank if the report has not been approved.</small></label></div>
      {error&&<p className="reportExportError" role="alert">{error}</p>}<footer><button type="button" className="btn" disabled={busy} onClick={close}>Cancel</button><button type="submit" className="btn primary" disabled={busy}><Download size={16}/>{busy?'Preparing report…':`Export ${request.format.toUpperCase()}`}</button></footer>
    </form></dialog>}</Context.Provider>;
}
