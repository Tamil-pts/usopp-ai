import {useRef,useState} from 'react';
import {Paperclip,Upload} from 'lucide-react';
import {HUB,type HubRow as Row} from '../projectApi';
import type {Cursor} from './model';

export function attachmentPath(block:Row|null,cursor:Cursor|null){
 if(!block)return '';
 if(block.type==='native_text'){const binding=block.data.binding;if(binding.startsWith('section:'))return 'section/'+binding.split(':')[1]+'/text';if(['summary','purpose','scope','acceptance_summary','na_reason','meeting_subject','meeting_date','meeting_mode','location','agenda','follow_up'].includes(binding))return binding;}
 if(block.type==='native_table'&&cursor?.cellId){const parts=cursor.cellId.split(':'),field=parts.pop(),key=parts.join(':'),prefix=({requirements:'requirement',cases:'case',changes:'change',sections:'section'} as Row)[block.data.binding];if(prefix&&field!=='id'&&!['requirement_ids','actual_result','result','heading'].includes(field||''))return prefix+'/'+key+'/'+field;}
 return 'element/'+block.id+(cursor&&cursor.blockId===block.id&&cursor.cellId?'/cell/'+cursor.cellId:'');
}
export default function FieldLinks({block,cursor,content,metadata,upload,change}:{block:Row|null;cursor:Cursor|null;content:Row;metadata:Row;upload:(files:File[])=>Promise<Row[]>;change:(fn:(content:Row,layout:Row)=>void,label:string)=>void}){
 const input=useRef<HTMLInputElement>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),path=attachmentPath(block,cursor);
 if(!path)return null;const ids:string[]=content.field_files?.[path]||[];
 const link=(next:string[])=>change(c=>{c.field_files={...c.field_files,[path]:next};c.file_ids=[...new Set([...(c.file_ids||[]),...next])];},'Field attachments updated');
 const add=async(files:File[])=>{setBusy(true);setError('');try{const added=await upload(files);link([...new Set([...ids,...added.map(f=>f.id)])]);}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <details className="ds-field-links"><summary><Paperclip size={13}/>Field attachments{ids.length?' ('+ids.length+')':''}</summary>{metadata.files.filter((f:Row)=>ids.includes(f.id)).map((f:Row)=><div key={f.id}><a href={HUB+'/files/'+f.id+'/download'} target="_blank" rel="noopener">{f.name}</a>{metadata.editable&&<button className="btn" disabled={busy} onClick={()=>link(ids.filter(v=>v!==f.id))}>Remove link</button>}</div>)}{metadata.editable&&<><label>Link an existing file<select aria-label="Attach existing file to selected field" value="" disabled={busy} onChange={e=>{if(e.target.value)link([...new Set([...ids,e.target.value])]);}}><option value="">Choose a project file</option>{metadata.files.filter((f:Row)=>!ids.includes(f.id)).map((f:Row)=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label><button className="btn" disabled={busy} onClick={()=>input.current?.click()}><Upload size={13}/>{busy?'Uploading…':'Upload for selected field'}</button><input ref={input} type="file" multiple hidden onChange={e=>{void add(Array.from(e.target.files||[]));e.currentTarget.value='';}}/></>}{error&&<p role="alert" className="wh-error">{error}</p>}</details>;
}
