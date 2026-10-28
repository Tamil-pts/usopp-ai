import {useState,type DragEvent} from 'react';
import {Check,ChevronRight,FileText,GitBranch,Search} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {dayLabel,when,type HubRow} from './projectApi';

const TOOLS:Record<string,string>={validation:'ByteMap',metadata:'ByteMap metadata',datainspect:'DataInspect',compare:'MatchView',rules:'LogicScan'};
const columnOf=(row:HubRow)=>row.stage==='todo'?(row.type==='project'&&row.assignment_state==='assigned'?'assigned':'todo'):row.stage==='released'||(row.type==='task'&&row.stage==='development_completed')?'done':'progress';
const COLUMNS=[{id:'assigned',label:'Assigned'},{id:'todo',label:'To do'},{id:'progress',label:'In progress'},{id:'done',label:'Completed'}];

export function TeamActivityBoard({items,users,actions,onOpen,onEvidence,onAction}:{items:HubRow[];users:HubRow[];actions:Record<string,HubRow[]>;onOpen:(project:string,item?:string)=>void;onEvidence:(project:string,item:string)=>void;onAction:(item:HubRow,action:HubRow)=>void}){
  const {user}=useAccount();const [query,setQuery]=useState(''),[person,setPerson]=useState(''),[scope,setScope]=useState('all'),[notice,setNotice]=useState(''),[over,setOver]=useState('');
  const name=(id:number)=>users.find(row=>row.id===id)?.username||'Account unavailable';
  const visible=items.filter(row=>(!person||[row.owner_id,row.current_user_id,row.latest_iteration?.author_id].includes(Number(person)))&&(scope==='all'||row.type===scope)&&(row.title+' '+name(row.owner_id)).toLowerCase().includes(query.toLowerCase())).sort((a,b)=>b.updated_at.localeCompare(a.updated_at));
  const drop=(event:DragEvent,column:string)=>{
    event.preventDefault();setOver('');const row=items.find(row=>row.id===event.dataTransfer.getData('text/workhub-item'));
    if(!row||columnOf(row)===column)return;
    if(row.current_user_id!==user.id){setNotice('Open the work item to see its assigned owner or reviewer.');return;}
    if(row.type==='project'&&column==='done'&&row.stage!=='ready_release'){setNotice('Projects enter Done after quality, release approval and release closure. Open the project to continue its current phase.');return;}
    const id=row.stage==='ready_release'&&column==='done'?'release':row.stage==='todo'&&column==='progress'?'start':row.stage==='development'&&column==='done'?'complete_development':row.stage==='development_completed'&&column==='progress'?'continue_development':row.stage==='released'&&column==='progress'?'reopen':'';
    const action=(actions[row.stage]||[]).find(action=>action.id===id);
    if(action){setNotice('');onAction(row,action);}else setNotice('Open this item to use its assigned quality or release action.');
  };
  return <section className="wh-team-activity"><div className="wh-section-heading"><div><h2>Team activity</h2><p>Projects and tasks, with engineering results recorded as numbered iterations.</p></div><div className="actions"><label className="wh-search"><Search size={16}/><input className="textInput" aria-label="Search team work" placeholder="Find project, task or owner" value={query} onChange={event=>setQuery(event.target.value)}/></label><select className="textInput" aria-label="Filter team member" value={person} onChange={event=>setPerson(event.target.value)}><option value="">All users</option>{users.map(row=><option key={row.id} value={row.id}>{row.username}</option>)}</select><select className="textInput" aria-label="Filter work type" value={scope} onChange={event=>setScope(event.target.value)}><option value="all">Projects and tasks</option><option value="project">Projects</option><option value="task">Tasks</option></select></div></div>
    <p className="wh-muted">Projects enter Done after release closes. Completed development tasks can enter Done while their project continues through quality and release.</p>{notice&&<p role="status" className="wh-warning">{notice}</p>}
    <div className="wh-team-board">{COLUMNS.map(column=><section key={column.id} className={'wh-team-column '+column.id+(over===column.id?' drop-target':'')} onDragOver={event=>{if(event.dataTransfer.types.includes('text/workhub-item')){event.preventDefault();setOver(column.id);}}} onDragLeave={()=>setOver('')} onDrop={event=>drop(event,column.id)}>
      <header><h3>{column.label}{column.id==='done'&&<Check size={18}/>}</h3><span>{visible.filter(row=>columnOf(row)===column.id).length}</span></header>
      {visible.filter(row=>columnOf(row)===column.id).map(row=>{const latest=row.type==='project'?row.latest_iteration:null;const owner=users.find(person=>person.id===row.current_user_id);return <article key={row.id} className="wh-team-card" draggable={row.current_user_id===user.id} onDragStart={event=>{event.dataTransfer.setData('text/workhub-item',row.id);event.dataTransfer.effectAllowed='move';}}>
        <button className="wh-team-card-title" onClick={()=>onOpen(row.project_id,row.id)}>{row.title}<ChevronRight size={16}/></button>
        <div className="wh-team-card-tags"><span className={'wh-stage wh-stage-'+row.stage}>{row.stage_label}</span><span className="wh-work-type">{latest?TOOLS[latest.kind]:row.kind}</span></div>
        {latest&&<div className="wh-team-iteration" title={"Recorded by "+name(latest.author_id)}><GitBranch size={14}/><b>Iteration {latest.iteration}</b><small>{latest.status}</small></div>}
        <footer><span title={row.current_user_id===row.owner_id?'Development owner':'Current responsibility'}>{owner?.avatarUrl?<img src={owner.avatarUrl} alt=""/>:<i>{name(row.current_user_id).slice(0,2).toUpperCase()}</i>}{name(row.current_user_id)}</span><small>{row.due_date?dayLabel(row.due_date):when(row.updated_at)}</small></footer>
        <div className="wh-team-card-actions"><button className="btn" onClick={()=>onEvidence(row.project_id,row.id)}><FileText size={13}/>Open work details</button>{row.current_user_id===user.id&&(actions[row.stage]||[]).slice(0,1).map(action=><button className="btn" key={action.id} onClick={()=>onAction(row,action)}>{action.label}</button>)}</div>
      </article>;})}
      {!visible.some(row=>columnOf(row)===column.id)&&<p className="wh-muted wh-board-empty">No work here yet.</p>}
    </section>)}</div>
  </section>;
}
