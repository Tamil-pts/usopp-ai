import {createContext,useContext,useRef,useState,type ReactNode} from 'react';
import {Paperclip,Upload} from 'lucide-react';
import {HUB,uploadFiles,type HubRow as Row} from '../projectApi';
type Value={project:string;body:Row;files:Row[];readOnly:boolean;busy:boolean;change:(v:Row)=>void;uploaded:(file:Row)=>void;uploading:(busy:boolean)=>void;trackUpload:(task:Promise<void>)=>void};
const Context=createContext<Value|null>(null);

export function normalizeFieldLinks(body:Row):Row{
 const next:Row={...body,sections:(body.sections||[]).map((s:Row,i:number)=>({...s,id:s.id||'SECTION-'+String(i+1).padStart(3,'0')}))};
 const allowed=new Set(['summary','purpose','scope','acceptance_summary','na_reason']);
 for(const [prefix,key,fields] of [['requirement','requirements',['title','description','trigger','expected_behavior','subsystem','acceptance_criteria']],['case','cases',['objective','procedure','expected_result','acceptance_criteria','actual','observations']],['change','changes',['summary','existing_behavior','expected_behavior','plc_references','impact','before_evidence','after_evidence','verification']],['section','sections',['text']]] as [string,string,string[]][]){for(const r of next[key]||[])for(const f of fields)allowed.add(prefix+'/'+r.id+'/'+f);}
 for(const b of body.studio?.blocks||[]){const base='element/'+b.id;allowed.add(base);for(const cell of b.data.cells||[])allowed.add(base+'/cell/'+cell.id);if(b.type==='native_table')for(const row of body[b.data.binding]||[])if(row&&typeof row==='object')for(const field of Object.keys(row))allowed.add(base+'/cell/'+row.id+':'+field);}
 next.field_files=Object.fromEntries(Object.entries(body.field_files||{}).filter(([path,ids])=>allowed.has(path)&&Array.isArray(ids)&&ids.length));
 next.file_ids=[...new Set([...(body.file_ids||[]),...Object.values(next.field_files).flat()])];
 next.cases=(next.cases||[]).map((c:Row)=>{const result={...c};delete result.field_files;const files=Object.fromEntries(['objective','procedure','expected_result','acceptance_criteria'].flatMap(f=>next.field_files['case/'+c.id+'/'+f]?[[f,next.field_files['case/'+c.id+'/'+f]]]:[]));if(Object.keys(files).length)result.field_files=files;return result;});
 return next;
}
export function FieldAttachmentProvider({children,...value}:Value&{children:ReactNode}){return <Context.Provider value={value}>{children}</Context.Provider>;}
export function FieldAttachments({field,label}:{field:string;label:string}){
 const ctx=useContext(Context),[busy,setBusy]=useState(false),[error,setError]=useState(''),[progress,setProgress]=useState('');const input=useRef<HTMLInputElement>(null),abort=useRef<AbortController|null>(null);
 const latest=useRef(ctx);latest.current=ctx;
 if(!ctx)return null;
 const ids:string[]=ctx.body.field_files?.[field]||[],selected=ctx.files.filter(f=>ids.includes(f.id));
 const change=(values:string[])=>{const value=latest.current!;value.change(normalizeFieldLinks({...value.body,field_files:{...value.body.field_files,[field]:values},file_ids:[...new Set([...(value.body.file_ids||[]),...values])]}));};
 const upload=async(files:File[])=>{if(!files.length)return;setBusy(true);ctx.uploading(true);setError('');abort.current=new AbortController();const added:Row[]=[];try{await uploadFiles(ctx.project,files,v=>setProgress(v.phase+': '+v.name),file=>{added.push(file);ctx.uploaded(file);},abort.current.signal);change([...new Set([...(latest.current?.body.field_files?.[field]||[]),...added.map(f=>f.id)])]);}catch(e){if(added.length)change([...new Set([...(latest.current?.body.field_files?.[field]||[]),...added.map(f=>f.id)])]);setError((e as Error).message);}finally{setBusy(false);latest.current?.uploading(false);setProgress('');}};
 return <details className="qc-field-files"><summary><Paperclip size={12}/>{ids.length?'Attachments ('+ids.length+')':'Attach files'}<span className="sr-only"> for {label}</span></summary>{selected.map(f=><div key={f.id}><a href={HUB+'/files/'+f.id+'/download'} target="_blank" rel="noopener">{f.name}</a>{!ctx.readOnly&&<button type="button" className="btn" disabled={busy||ctx.busy} aria-label={'Remove '+f.name+' from '+label} onClick={()=>change(ids.filter(id=>id!==f.id))}>Remove link</button>}</div>)}{!ctx.readOnly&&<><button type="button" className="btn" disabled={busy||ctx.busy} onClick={()=>input.current?.click()}><Upload size={12}/>Upload for {label}</button><input ref={input} aria-label={'Upload files for '+label} type="file" multiple hidden onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';ctx.trackUpload(upload(files));}}/><details><summary>Use an existing project file</summary>{ctx.files.map(f=><div key={f.id}><input type="checkbox" aria-label={'Attach '+f.name+' to '+label} checked={ids.includes(f.id)} disabled={busy||ctx.busy} onChange={e=>change(e.target.checked?[...ids,f.id]:ids.filter(id=>id!==f.id))}/><span>{f.name}</span></div>)}</details></>}{progress&&<p role="status">{progress}</p>}{error&&<p className="wh-error" role="alert">{error}</p>}</details>;
}
