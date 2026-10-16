import {useEffect,useState} from 'react';
import {ArrowDown,ArrowUp,Plus,RefreshCw,Save,Trash2} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';

type Rule={id:string;keyword:string;unit:string;match:'word'|'contains'|'exact';machine_department:string;enabled:boolean};
export function UnitRules({departments=['All'],machineDepartment='All',active=true}:{departments?:string[];machineDepartment?:string;active?:boolean}){
 const {user}=useAccount();const admin=user.role==='admin';
 const [rows,setRows]=useState<Rule[]>([]),[enabled,setEnabled]=useState(true),[revision,setRevision]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [parameter,setParameter]=useState('Doff time minutes'),[department,setDepartment]=useState(machineDepartment),[preview,setPreview]=useState<{unit:string;source:string}|null>(null);
 const accept=(data:any)=>{setRows(data.mappings);setEnabled(data.enabled);setRevision(data.revision);setPreview(null)};
 const api=async(init?:RequestInit,path='/api/knowledge/units')=>{const response=await fetch(path,init);const data=await response.json();if(!response.ok)throw new Error(data.detail||'Unit rules could not be loaded.');return data};
 const reload=async()=>{setBusy(true);setError('');try{accept(await api())}catch(reason:any){setError(reason.message)}finally{setBusy(false)}};
 useEffect(()=>{if(active&&!revision)void reload()},[active]);
 const change=(index:number,patch:Partial<Rule>)=>{setRows(previous=>previous.map((row,i)=>i===index?{...row,...patch}:row));setPreview(null);setMessage('')};
 const move=(index:number,direction:number)=>{setRows(previous=>{const next=[...previous];[next[index],next[index+direction]]=[next[index+direction],next[index]];return next});setPreview(null)};
 const body=()=>({enabled,mappings:rows,revision});
 const save=async()=>{setBusy(true);setError('');setMessage('');try{accept(await api({method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body())}));setMessage('Unit rules saved. Generate a new metadata workbook to apply them.')}catch(reason:any){setError(reason.message)}finally{setBusy(false)}};
 const check=async()=>{setBusy(true);setError('');setPreview(null);try{setPreview(await api({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body(),parameter,department})},'/api/knowledge/units/preview'))}catch(reason:any){setError(reason.message)}finally{setBusy(false)}};
 const machines=[...new Set(['All',...departments,department,...rows.map(row=>row.machine_department)])];
 return <section className="card knowledgeTableCard unitRules">
  <div className="pageHead"><div><h3>Automatic metadata units</h3><p>Fill empty UNITS from configurable parameter-name rules. Explicit units in Parameter mappings take priority. Unit labels do not convert PLC values.</p></div><button className="btn" disabled={busy} onClick={()=>void reload()}><RefreshCw size={14}/>Reload</button></div>
  <p className="muted">Department-specific rules run first, then All. Within each scope, the first matching enabled row wins. Matching ignores capitalization and separates words in PLC names. Rules apply when generating new metadata and are included in Admin knowledge export/import.</p>
  {!admin&&<p>Admin manages these shared rules.</p>}
  <div className="actions"><label><input type="checkbox" checked={enabled} disabled={!admin||busy} onChange={event=>{setEnabled(event.target.checked);setPreview(null)}}/> Enable automatic unit labels</label>
   {admin&&<><button className="btn" disabled={busy||!revision||rows.length>=200} onClick={()=>{setRows(previous=>[...previous,{id:crypto.randomUUID(),keyword:'',unit:'',match:'word',machine_department:machineDepartment,enabled:true}]);setPreview(null)}}><Plus size={14}/>Add unit rule</button><button className="btn primary" disabled={busy||!revision} onClick={()=>void save()}><Save size={14}/>Save unit rules</button></>}
  </div>
  {error&&<p role="alert" className="failText">{error}</p>}{message&&<p role="status">{message}</p>}
  <div className="knowledgeTableScroll"><table className="table"><thead><tr><th>Order</th><th>Enabled</th><th>Parameter keyword</th><th>Match</th><th>Unit label</th><th>Machine / department</th>{admin&&<th>Actions</th>}</tr></thead><tbody>{rows.map((row,index)=><tr key={row.id}>
   <td>{index+1}</td><td><input type="checkbox" aria-label={`Enable unit rule ${index+1}`} checked={row.enabled} disabled={!admin||busy} onChange={event=>change(index,{enabled:event.target.checked})}/></td>
   <td><input aria-label={`Unit keyword ${index+1}`} value={row.keyword} maxLength={100} disabled={!admin||busy} onChange={event=>change(index,{keyword:event.target.value})}/></td>
   <td><select aria-label={`Unit match ${index+1}`} value={row.match} disabled={!admin||busy} onChange={event=>change(index,{match:event.target.value as Rule['match']})}><option value="word">Whole word / phrase</option><option value="contains">Contains text</option><option value="exact">Entire parameter name</option></select></td>
   <td><input aria-label={`Unit label ${index+1}`} value={row.unit} maxLength={32} disabled={!admin||busy} onChange={event=>change(index,{unit:event.target.value})}/></td>
   <td><select aria-label={`Unit department ${index+1}`} value={row.machine_department} disabled={!admin||busy} onChange={event=>change(index,{machine_department:event.target.value})}>{machines.map(name=><option key={name}>{name}</option>)}</select></td>
   {admin&&<td><div className="actions"><button className="btn" aria-label={`Move unit rule ${index+1} up`} disabled={busy||index===0} onClick={()=>move(index,-1)}><ArrowUp size={13}/></button><button className="btn" aria-label={`Move unit rule ${index+1} down`} disabled={busy||index===rows.length-1} onClick={()=>move(index,1)}><ArrowDown size={13}/></button><button className="btn danger" aria-label={`Delete unit rule ${index+1}`} disabled={busy} onClick={()=>{setRows(previous=>previous.filter(item=>item.id!==row.id));setPreview(null)}}><Trash2 size={13}/></button></div></td>}
  </tr>)}</tbody></table></div>
  {!rows.length&&<p>{busy?'Loading unit rules...':'No unit rules configured.'}</p>}
  <div className="unitRulePreview"><h4>Preview a parameter name</h4><div className="actions"><input className="textInput" aria-label="Unit preview parameter" value={parameter} onChange={event=>{setParameter(event.target.value);setPreview(null)}} maxLength={300}/><select aria-label="Unit preview department" value={department} onChange={event=>{setDepartment(event.target.value);setPreview(null)}}>{machines.map(name=><option key={name}>{name}</option>)}</select><button className="btn" disabled={busy||!parameter.trim()||!revision||user.isDemo} onClick={()=>void check()}>Preview unit</button></div>{preview&&<p role="status">Unit: <b>{preview.unit==='\u003cnull\u003e'?'Not configured':preview.unit}</b> · {preview.source}</p>}</div>
 </section>;
}
