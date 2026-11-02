import {useWorkHubDialog} from './useWorkHubDialog';
import {useState} from 'react';
import {Trash2,X} from 'lucide-react';
import {hub,type HubRow as Row} from './projectApi';
export function DeleteDocumentDialog({document,onClose,onDeleted}:{document:Row;onClose:()=>void;onDeleted:()=>void}){
 const [reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const dialog=useWorkHubDialog(onClose,busy);
 const remove=async()=>{setBusy(true);setError('');try{await hub('/documents/'+document.id+'/delete',{revision_id:document.current_revision,version:document.revision_version,reason});onDeleted();window.dispatchEvent(new Event('workhub-document-deleted'));}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <div className="wh-backdrop"><section ref={dialog} className="wh-dialog wh-delete-document" role="dialog" aria-modal="true" aria-label="Delete document"><header><h2><Trash2 size={21}/>Delete document</h2><button type="button" className="btn" aria-label="Close delete document" disabled={busy} onClick={onClose}><X size={18}/></button></header><p><strong>{document.title}</strong></p><p>This removes the document from active lists. Its revisions, approvals and recorded evidence remain in history.</p><label>Reason for deletion<textarea className="textInput" aria-label="Reason for deletion" rows={3} maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/></label>{error&&<p className="wh-error" role="alert">{error}</p>}<footer><button className="btn" disabled={busy} onClick={onClose}>Cancel</button><button className="btn danger" disabled={busy||!reason.trim()} onClick={()=>void remove()}>{busy?'Deleting…':'Delete document'}</button></footer></section></div>;
}
