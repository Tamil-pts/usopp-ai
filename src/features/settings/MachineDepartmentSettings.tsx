import {useEffect,useState} from 'react';
import {Plus,Save,Trash2} from 'lucide-react';
import type {MachinePrefix} from '../validation/projectDetails';

export function MachineDepartmentSettings({departments,prefixes,onSave}:{departments:string[];prefixes:MachinePrefix[];onSave:(value:{departments:string[];prefixes:MachinePrefix[]})=>Promise<void>}){
 const [names,setNames]=useState(departments),[rows,setRows]=useState(prefixes),[newName,setNewName]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 useEffect(()=>{setNames(departments);setRows(prefixes)},[departments,prefixes]);
 const update=(index:number,key:'prefix'|'department',value:string)=>setRows(current=>current.map((row,i)=>i===index?{...row,[key]:value}:row));
 const save=async()=>{setBusy(true);setError('');setMessage('');try{await onSave({departments:names,prefixes:rows});setMessage('Shared machine / department settings saved.')}catch(e:any){setError(e.message||'Save failed.')}finally{setBusy(false)}};
 return <section className="card setting wide"><div className="widgetHead"><h3>Machine / department</h3><button className="btn primary" disabled={busy} onClick={()=>void save()}><Save size={13}/>Save shared settings</button></div>
  <p>Project selection identifies a machine from the prefix of its .apj filename. Add future departments and map each project prefix here. These settings are shared by all users.</p>
  <div className="actions">{names.filter(name=>name!=='All').map(name=><span className="chip active" key={name}>{name}</span>)}</div>
  <div className="actions"><input className="textInput" aria-label="New machine or department" placeholder="Add machine / department" value={newName} disabled={busy} onChange={event=>setNewName(event.target.value)}/><button className="btn" disabled={busy||!newName.trim()||names.some(name=>name.toLowerCase()===newName.trim().toLowerCase())} onClick={()=>{setNames(current=>[...current,newName.trim()]);setNewName('')}}><Plus size={13}/>Add department</button></div>
  <div className="tableWrap"><table><thead><tr><th>.apj prefix</th><th>Machine / department</th><th/></tr></thead><tbody>{rows.map((row,index)=><tr key={`${row.prefix}:${index}`}><td><input className="textInput" aria-label={`Prefix ${index+1}`} maxLength={16} value={row.prefix} disabled={busy} onChange={event=>update(index,'prefix',event.target.value.toUpperCase())}/></td><td><select className="textInput" aria-label={`Department for prefix ${index+1}`} value={row.department} disabled={busy} onChange={event=>update(index,'department',event.target.value)}>{names.filter(name=>name!=='All').map(name=><option key={name}>{name}</option>)}</select></td><td><button className="btn" aria-label={`Remove prefix ${row.prefix}`} title={`Remove prefix ${row.prefix}`} disabled={busy} onClick={()=>setRows(current=>current.filter((_,i)=>i!==index))}><Trash2 size={13}/>Remove</button></td></tr>)}</tbody></table></div>
  <button className="btn" disabled={busy||names.length<2} onClick={()=>setRows(current=>[...current,{prefix:'',department:names.find(name=>name!=='All')||''}])}><Plus size={13}/>Add .apj prefix</button>
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}
