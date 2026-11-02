import {useEffect,useRef,useState} from 'react';
import {Download,Save,X} from 'lucide-react';

export type Cover={fileName:string;reviewVersion:string;reviewDate:string;reviewedBy:string;reviewSignature:string;assignedTo:string;description:string;approvedBy:string;approvalDate:string;approvalDetails:string};
export type ExportFormat='pdf'|'report'|'docx'|'html'|'details';
const fields:[keyof Cover,string,string][]=[['fileName','File name','text'],['reviewVersion','Review version','text'],['reviewDate','Review date','date'],['reviewedBy','Reviewed by','text'],['reviewSignature','Review sign-off','text'],['assignedTo','Assigned to','text'],['description','Description','textarea'],['approvedBy','Approved by','text'],['approvalDate','Approval date','date'],['approvalDetails','Approval details','textarea']];
export function ReviewExportDialog({review,format,onClose,onSaved}:{review:{id:string;cover:Cover;coverVersion:number;access:string};format:ExportFormat|null;onClose:()=>void;onSaved:(value:any)=>void}) {
 const dialog=useRef<HTMLDialogElement>(null),[details,setDetails]=useState<Cover>(review.cover),[version,setVersion]=useState(review.coverVersion),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{if(format){setDetails(review.cover);setVersion(review.coverVersion);setError('');dialog.current?.showModal()}else dialog.current?.close()},[format,review.id]);
 const writable=review.access!=='view';
 const submit=async()=>{
  setBusy(true);setError('');
  try{
   if(writable){const response=await fetch(`/api/e-design/${review.id}/cover`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({version,details})});const next=await response.json();if(!response.ok)throw Error(next.detail||'Could not save the front page.');setVersion(next.coverVersion);onSaved(next);}
   if(format&&format!=='details'){
    const response=await fetch(`/api/e-design/${review.id}/export/${format}?include_cover=true`);if(!response.ok){const data=await response.json();throw Error(data.detail||'Could not export the drawing.')}
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=details.fileName.replace(/\.pdf$/i,'')+'-review.'+(format==='report'?'pdf':format);link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
   }
   onClose();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 };
 return <dialog className="edExportDialog" ref={dialog} onCancel={e=>{e.preventDefault();if(!busy)onClose()}}><form onSubmit={e=>{e.preventDefault();void submit()}}>
  <header><div><small>DRAWING REVIEW / FRONT PAGE</small><h2>{format==='details'?'Front page details':'Review & export'}</h2><p>Review the prefilled details. They are saved with this drawing review.</p></div><button type="button" className="btn" disabled={busy} aria-label="Close export front page" onClick={onClose}><X size={17}/></button></header>
  <div className="edCoverFields">{fields.map(([key,label,type])=><label key={key} className={type==='textarea'?'wide':''}>{label}{type==='textarea'?<textarea aria-label={label} rows={3} maxLength={2000} value={details[key]} readOnly={!writable||busy} onChange={e=>setDetails(v=>({...v,[key]:e.target.value}))}/>:<input aria-label={label} type={type} maxLength={key==='reviewVersion'?40:key==='assignedTo'?500:200} required={key==='fileName'||key==='reviewVersion'} value={details[key]} readOnly={!writable||busy} onChange={e=>setDetails(v=>({...v,[key]:e.target.value}))}/>}</label>)}</div>
  {error&&<p className="edError" role="alert">{error}</p>}<footer><button type="button" className="btn" disabled={busy} onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy}>{format==='details'?<Save size={16}/>:<Download size={16}/>} {busy?'Preparing…':format==='details'?'Save front page':writable?'Save & export':'Export with front page'}</button></footer>
 </form></dialog>;
}
