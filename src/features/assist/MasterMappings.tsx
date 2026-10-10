import {MappingConversation} from './MappingConversation';
import {useEffect,useState} from 'react';
import {Download,Plus,Save,Upload,PenLine,RefreshCw} from 'lucide-react';
import {LocalFileTree} from '../../shared/LocalFileBrowser';
import {DEPARTMENTS} from '../rules/library';

const columns=[['plc_parameter','PLC Parameter'],['plc_tag','PLC Tag'],['metadata_parameter','Metadata Parameter'],['machine_department','Machine / department'],['units','Units'],['MIN','Minimum'],['MAX','Maximum'],['offset_factor','Offset factor'],['scale_factor','Scale factor'],['is_visible','Visible'],['is_writable','Writable'],['status','Status']];
type Mapping=Record<string,any>;
export function MasterMappings({machineDepartment='All',departments=DEPARTMENTS}:{machineDepartment?:string;departments?:string[]}){
 const [conversation,setConversation]=useState<number|'new'|null>(null);
 const [browserOpen,setBrowserOpen]=useState(false);
 const [rows,setRows]=useState<Mapping[]>([]),[saved,setSaved]=useState<Mapping[]>([]);
 const [revision,setRevision]=useState(''),[editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(0);
 const accept=(data:any)=>{const mappings=(data.mappings||[]).map((row:Mapping)=>({...row,machine_department:row.machine_department||'All'}));setRows(mappings);setSaved(mappings);setRevision(data.revision||'');setEditing(false);setPage(0)};
 const request=async(init?:RequestInit)=>{const r=await fetch('/api/knowledge/master',init);const data=await r.json();if(!r.ok)throw new Error(data.detail||'Mapping request failed.');return data};
 const reload=async()=>{setBusy(true);setError('');try{accept(await request())}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 useEffect(()=>{void reload()},[]);
 const save=async()=>{setBusy(true);setError('');setMessage('');try{accept(await request({method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,mappings:rows})}));setMessage('Mappings saved. Run metadata validation again to use the updated knowledge.')}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 const upload=async(file?:File)=>{if(!file)return;setBusy(true);setError('');setMessage('');try{const body=new FormData();body.append('file',file);const r=await fetch('/api/knowledge/master/csv',{method:'POST',body});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Import failed.');accept(data);setMessage(`Imported and saved ${data.imported} mappings.`)}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 const exportCsv=(template:boolean)=>{const quote=(v:any)=>'"'+String(v??'').replaceAll('"','""')+'"';const header=columns.map(([key])=>quote(key.toUpperCase())).join(',');const dataRows=template?[]:rows.map(row=>columns.map(([key])=>quote(row[key]??(key==='machine_department'?'All':''))).join(','));const content=[header,...dataRows].join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+content+'\r\n'],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=template?'uSOPp_parameter_mapping_template.csv':'uSOPp_parameter_mappings.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 const visible=rows.map((row,index)=>({row,index})).filter(({row})=>columns.some(([key])=>String(row[key]??'').toLowerCase().includes(query.toLowerCase())));
 const pages=Math.max(1,Math.ceil(visible.length/40));const current=Math.min(page,pages-1);
 const update=(index:number,key:string,value:string)=>setRows(previous=>previous.map((row,i)=>i===index?{...row,[key]:value===''?null:value}:row));
 return <><section className="card knowledgeTableCard">
  <h3>Master parameter mappings</h3><p>Approved PLC Parameter, PLC Tag and metadata mappings used by metadata validation. Existing rows without a machine are treated as All.</p><p className="muted"><code>knowledge/master/parameter_mappings.json</code> · Project department: <b>{machineDepartment}</b></p>
  <div className="actions"><button className="btn primary" disabled={busy||editing} onClick={()=>setConversation('new')}>Configure with Chopper</button>
   <button className="btn" disabled={busy||!revision||editing} onClick={()=>{setEditing(true);setMessage('')}}><PenLine size={14}/>Edit table</button>
<button className="btn" disabled={busy||!revision} onClick={()=>{setRows([...rows,{plc_parameter:'',plc_tag:'',metadata_parameter:'',machine_department:'All',units:null,MIN:null,MAX:null,offset_factor:1,scale_factor:1,is_visible:'YES',is_writable:'NO',status:'configured'}]);setEditing(true);setQuery('');setPage(Math.floor(rows.length/40))}}><Plus size={14}/>Add mapping</button>
   {editing&&<><button className="btn primary" disabled={busy} onClick={()=>void save()}><Save size={14}/>{busy?'Saving...':'Save changes'}</button><button className="btn" disabled={busy} onClick={()=>{setRows(saved);setEditing(false);setError('')}}>Cancel edits</button></>}
   <button className="btn" disabled={busy||editing} onClick={()=>void reload()}><RefreshCw size={14}/>Reload</button>
   <button className="btn" onClick={()=>exportCsv(true)}><Download size={14}/>Export empty template</button>
   <button className="btn" disabled={busy||!revision} onClick={()=>exportCsv(false)}><Download size={14}/>Export {editing?'current table':'data'} (CSV)</button>
   <label className="btn"><Upload size={14}/>Import CSV<input type="file" accept=".csv" disabled={busy||editing} onChange={e=>{void upload(e.target.files?.[0]);e.target.value=''}} hidden/></label>
   <button className="btn" disabled={busy||editing} onClick={()=>setBrowserOpen(true)}>Browse This PC (CSV)</button>
  </div>
  <LocalFileTree open={browserOpen} onClose={()=>setBrowserOpen(false)} allowedExts={['.csv']} onSelect={async(path)=>{setBusy(true);setError('');setMessage('');try{const r=await fetch('/api/local/knowledge/master/csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Import failed.');accept(data);setMessage(`Imported and saved ${data.imported} mappings.`)}catch(e:any){setError(e.message)}finally{setBusy(false)}}}/>
  {editing&&<p role="status">Editing table. Save changes to update the master file. Export includes current edits.</p>}
  {message&&<p role="status">{message}</p>}{error&&<p className="failText" role="alert">{error}</p>}
  <label className="knowledgeSearch">Search mappings<input className="textInput" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}} placeholder="PLC tag, parameter or metadata name"/></label>
  <div className="knowledgeTableScroll" tabIndex={0} aria-label="Master mappings table"><table className="table"><thead><tr><th>Configure</th><th>#</th>{columns.map(([key,label])=><th key={key}>{label}</th>)}</tr></thead><tbody>{visible.slice(current*40,current*40+40).map(({row,index})=><tr key={index}><td><button className="btn" disabled={editing||busy} onClick={()=>setConversation(index)}>Chopper</button></td><td>{index+1}</td>{columns.map(([key,label])=><td key={key}>{editing?(key==='machine_department'?<select aria-label={`${label} row ${index+1}`} value={row[key]||'All'} disabled={busy} onChange={e=>update(index,key,e.target.value)}>{[...new Set([...departments,row[key]||'All'])].map(d=><option key={d}>{d}</option>)}</select>:key==='is_visible'||key==='is_writable'?<select aria-label={`${label} row ${index+1}`} value={row[key]??''} disabled={busy} onChange={e=>update(index,key,e.target.value)}><option value="">Not set</option>{[...new Set(['YES','NO',...(row[key]?[String(row[key])]:[])])].map(value=><option key={value}>{value}</option>)}</select>:<input aria-label={`${label} row ${index+1}`} disabled={busy} value={row[key]??''} onChange={e=>update(index,key,e.target.value)}/>):String(row[key]??'—')}</td>)}</tr>)}</tbody></table></div>
  {!visible.length&&<p>{busy?'Loading mappings...':'No mappings match this search.'}</p>}
  <div className="actions"><button className="btn" disabled={current===0} onClick={()=>setPage(current-1)}>Previous</button><span>Page {current+1} / {pages} · {visible.length} of {rows.length} mappings</span><button className="btn" disabled={current+1>=pages} onClick={()=>setPage(current+1)}>Next</button></div>
 </section>{conversation!==null&&<MappingConversation key={conversation} kind="parameter" index={conversation==='new'?undefined:conversation} machineDepartment={machineDepartment} departments={departments} onClose={()=>setConversation(null)} onSaved={()=>{setConversation(null);void reload();setMessage('Parameter mapping saved.')}}/>}</>;
}
