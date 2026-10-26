import {useEffect,useState} from 'react';
import {useAccount} from '../account/AuthProvider';

async function api(path:string,method='GET') {
 const response=await fetch(path,{method});const data=await response.json();
 if(!response.ok)throw new Error(data.detail||'History could not be loaded.');return data;
}
const names:Record<string,string>={validation:'ByteMap / packet validation',metadata:'MetaWorks / generated metadata',
 rules:'LogicScan / rule validation',compare:'MatchView / project comparison',datainspect:'DataInspect / PLC data', 'data-model':'DataInspect / data model validation'};
export function RunHistory({active,onOpen,onReuse}:{active:boolean;onOpen:(kind:string,result:any)=>void;onReuse:(project:any,kind:string)=>void}){
 const {user}=useAccount();
 const [runs,setRuns]=useState<any[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(''),[query,setQuery]=useState('');
 const [kind,setKind]=useState('all'),[owner,setOwner]=useState('all'),[status,setStatus]=useState('all');
 const refresh=async()=>{setBusy('refresh');setError('');try{setRuns((await api('/api/history')).runs)}catch(e:any){setError(e.message)}finally{setBusy('')}};
 useEffect(()=>{
  if(!active)return;
  let cancelled=false;
  const reload=async()=>{try{const data=await api('/api/history');if(!cancelled)setRuns(data.runs)}catch(e:any){if(!cancelled)setError(e.message)}};
  void reload();const timer=setInterval(()=>{if(document.visibilityState==='visible')void reload()},15000);
  return()=>{cancelled=true;clearInterval(timer)};
 },[active,user.id]);
 const action=async(row:any,reuse:boolean,runKind=row.kind)=>{
  setBusy(row.id);setError('');try{
   if(reuse)onReuse(await api(`/api/history/${row.id}/reuse`,'POST'),runKind);
   else {const data=await api(`/api/history/${row.id}`);onOpen(data.record.kind,data.result)}
  }catch(e:any){setError(e.message)}finally{setBusy('')}
 };
 const owners=[...new Map(runs.filter(row=>row.user).map(row=>[String(row.user.id),row.user.username] as [string,string])).entries()];
 const visible=runs.filter(row=>(kind==='all'||row.kind===kind)&&(owner==='all'||String(row.user?.id)===owner)
  &&(status==='all'||(row.status||'completed')===status)
  &&`${row.projectName} ${row.testId||''} ${row.machineDepartment||''} ${names[row.kind]} ${row.user?.username||''}`.toLowerCase().includes(query.toLowerCase()));
 return <section className="card inputCard adminHistory"><div className="pageHead"><div><h2>Recent work</h2><p>{user.role==='admin'?"All users' saved":'Your saved'} DataInspect, packet, rule, metadata, data model and comparison results. Each test has a separate ID, owner and timestamp. Results and downloads survive cache clearing.</p></div><button className="btn" disabled={!!busy} onClick={()=>void refresh()}>Refresh history</button></div>
  <div className="actions"><input className="textInput" aria-label="Search test history" placeholder="Search test ID, project or user" value={query} onChange={e=>setQuery(e.target.value)}/>
   <label>Activity <select value={kind} onChange={e=>setKind(e.target.value)}><option value="all">All activities</option>{Object.entries(names).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
   {user.role==='admin'&&<label>User <select value={owner} onChange={e=>setOwner(e.target.value)}><option value="all">All users</option>{owners.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>}
   <label>Status <select value={status} onChange={e=>setStatus(e.target.value)}><option value="all">All</option><option value="running">Running</option><option value="completed">Completed</option><option value="failed">Processing failed</option><option value="interrupted">Interrupted</option></select></label>
  </div>
  {error&&<p role="alert" className="failText">{error}</p>}
  <p>{visible.length} stored tests</p>
  <div className="tableWrap"><table className="table"><thead><tr><th>Test ID</th><th>Project / PLC</th><th>Activity</th><th>Date / time</th><th>User</th><th>Status / findings</th><th>Results / downloads</th></tr></thead><tbody>{visible.map(row=><tr key={row.id}>
   <td className="mono">{row.testId||'ID not recorded in earlier version'}{row.legacy&&<small>Earlier run</small>}</td>
   <td>{row.projectName}<small>{row.machineDepartment||'All'}</small></td><td>{names[row.kind]||row.kind}</td><td>{new Date(row.createdAt).toLocaleString()}</td>
   <td>{row.user?<><b>{row.user.username}</b><small>User ID: {row.user.id}</small></>:'Not recorded in earlier version'}</td>
   <td><b>{row.status||'completed'}</b>{Object.entries(row.summary||{}).filter(([key,value])=>typeof value==='number').map(([key,value])=><div key={key}>{key}: {String(value)}</div>)}{row.error&&<small className="failText">{row.error}</small>}</td>
   <td><div className="actions"><button className="btn" disabled={!!busy||row.status==='running'} onClick={()=>void action(row,false)}>Open result</button><a className="btn" href={`/api/history/${row.id}/json`}>Download JSON</a>
    {(row.artifacts||[]).map((name:string)=><a className="btn" key={name} title={name} href={`/api/history/${row.id}/download/${encodeURIComponent(name)}`}>{name.toLowerCase().endsWith('.xlsx')?'Download Excel':'Download report'}</a>)}</div>
    {row.projectAvailable&&<div className="actions"><button className="btn" disabled={!!busy} onClick={()=>void action(row,true,'validation')}>Reuse in ByteMap</button><button className="btn" disabled={!!busy} onClick={()=>void action(row,true,'metadata')}>Reuse in MetaWorks</button><button className="btn" disabled={!!busy} onClick={()=>void action(row,true,'rules')}>Reuse in LogicScan</button></div>}
   </td>
  </tr>)}</tbody></table></div>{!runs.length&&!busy&&<p>No stored runs yet. New tests are saved automatically.</p>}{busy&&<p role="status">Loading stored result…</p>}
 </section>;
}
