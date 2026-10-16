import {useState,type ReactNode} from 'react';

/** Definitions are loaded only when inspected, keeping large rule packs compact. */
export function RuleReference({check,renderDefinition,onMakeEditable}:{check:any;renderDefinition?:(definition:any)=>ReactNode;onMakeEditable?:(definition:any)=>void}){
 const [definition,setDefinition]=useState<any>(null),[open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const inspect=async()=>{if(open){setOpen(false);return}setOpen(true);if(definition)return;setBusy(true);setError('');try{
  const url=`/api/rules/references/${encodeURIComponent(check.referenceFile)}/${encodeURIComponent(check.checkId)}?reference_hash=${encodeURIComponent(check.referenceHash||'')}`;
  const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Reference could not be loaded.');setDefinition(data.definition);
 }catch(reason){setError(reason instanceof Error?reason.message:'Reference could not be loaded.')}finally{setBusy(false)}};
 return <section className="ruleSavedReference"><b>{check.name||'Saved cross reference'}</b><p>{check.file}{check.line?` · Reference line ${check.line}`:''}</p><button type="button" className="btn" aria-expanded={open} disabled={busy} onClick={()=>void inspect()}>{busy?'Loading reference...':open?'Hide requirement':'Inspect referenced logic'}</button>
  {open&&<>{error&&<p role="alert" className="failText">{error}</p>}{definition&&<>{renderDefinition?renderDefinition(definition):<pre>{JSON.stringify(definition,null,2)}</pre>}{onMakeEditable&&<button type="button" className="btn" onClick={()=>onMakeEditable(structuredClone(definition))}>Create editable copy in this rule</button>}</>}</>}
 </section>;
}
