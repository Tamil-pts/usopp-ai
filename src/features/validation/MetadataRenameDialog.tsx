import {useEffect,useRef,useState} from 'react';

export type MetadataRename={sheet:number;row:number;column:string;oldName:string;newName:string;payload:Record<string,unknown>};
type Mapping={plc_tag:string;plc_parameter:string;machine_department:string;originalName:string;groupCode:string;tagCode:string;sourceFile?:string;lineNumber?:number};
type Preview={mapping:Mapping;revision:string;sourceRevision:string;existingNames:string[];canSave:boolean};

export function MetadataRenameDialog({rename,onClose,onSaved}:{rename:MetadataRename;onClose:()=>void;onSaved:(name:string)=>void}){
  const dialog=useRef<HTMLDialogElement>(null);
  const [preview,setPreview]=useState<Preview>();
  const [name,setName]=useState(rename.newName);
  const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const [reload,setReload]=useState(0);
  useEffect(()=>{const element=dialog.current;element?.showModal();return()=>element?.close()},[]);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setPreview(undefined);
    fetch('/api/metadata/view/parameter-mapping',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rename.payload),signal:controller.signal})
      .then(async response=>{const result=await response.json();if(!response.ok)throw new Error(result.detail||'Cannot load the PLC mapping.');return result})
      .then(result=>{if(!controller.signal.aborted)setPreview(result)})
      .catch(reason=>{if(!controller.signal.aborted)setError(reason.message)})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[rename,reload]);
  const save=async()=>{
    if(!preview?.canSave||saving)return;
    setSaving(true);setError('');
    try{
      const response=await fetch('/api/knowledge/master/metadata-rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...rename.payload,revision:preview.revision,sourceRevision:preview.sourceRevision,metadataParameter:name})});
      const result=await response.json();if(!response.ok)throw new Error(result.detail||'Cannot save the master mapping.');
      onSaved(result.metadataParameter);
    }catch(reason:any){setError(reason.message)}finally{setSaving(false)}
  };
  return <dialog ref={dialog} className="metadataRenameDialog" aria-labelledby="metadata-rename-title" onCancel={event=>{event.preventDefault();if(!saving)onClose()}}>
    <form onSubmit={event=>{event.preventDefault();void save()}}>
      <h2 id="metadata-rename-title">Save this parameter name to master?</h2>
      <p>Reuse the name for this PLC tag and comment in future projects in the same department.</p>
      <p className="metadataRenameChange"><span>{rename.oldName||'(empty name)'}</span><span aria-hidden="true"> → </span><strong>{name}</strong></p>
      {loading&&<p role="status">Finding the PLC tag and comment…</p>}
      {error&&<p className="failText" role="alert">{error}</p>}
      {preview&&<>
        <div className="metadataRenameFields">
          <label>PLC tag<input className="textInput" value={preview.mapping.plc_tag} readOnly/></label>
          <label>PLC comment / parameter<input className="textInput" value={preview.mapping.plc_parameter} readOnly/></label>
          <label>Department<input className="textInput" value={preview.mapping.machine_department} readOnly/></label>
          <label>New metadata parameter name<input className="textInput" value={name} onChange={event=>setName(event.target.value)} maxLength={300} disabled={saving} required/></label>
        </div>
        <p className="muted">Group Code {preview.mapping.groupCode} · TAG_CODE {preview.mapping.tagCode}{preview.mapping.sourceFile?` · ${preview.mapping.sourceFile}${preview.mapping.lineNumber?`:${preview.mapping.lineNumber}`:''}`:''}</p>
        {!!preview.existingNames.length&&<p>Current master name: <b>{preview.existingNames.join(', ')}</b>. Saving replaces that name for this PLC identity and department.</p>}
        {!preview.canSave&&<p>A personal account is required to save shared master mappings.</p>}
      </>}
      <p>Your workbook edit is kept if you cancel. Save a workbook copy separately to keep the edited file.</p>
      <div className="actions">
        <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel — keep workbook edit only</button>
        {error&&<button type="button" className="btn" disabled={loading||saving} onClick={()=>setReload(value=>value+1)}>Reload mapping details</button>}
        <button type="submit" className="btn primary" disabled={loading||saving||!preview?.canSave||!name.trim()}>{saving?'Saving…':'Save mapping to master'}</button>
      </div>
    </form>
  </dialog>;
}
