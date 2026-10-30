import {useMemo,useState,type DragEvent} from 'react';
import {Activity,CalendarDays,Check,ChevronRight,ClipboardCheck,FileText,FolderOpen,GitBranch,LayoutGrid,List,Plus,Search} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {ProjectGantt} from './ProjectGantt';
import {dayLabel,when,type HubRow} from './projectApi';
import './team-activity.css';

const TOOLS:Record<string,string>={validation:'ByteMap',metadata:'ByteMap metadata',datainspect:'DataInspect',compare:'MatchView',rules:'LogicScan'};
// Task development completion and project release are separate milestones.
const columnOf=(row:HubRow)=>row.stage==='released'||(row.type==='task'&&row.stage==='development_completed')?'done':row.stage==='todo'?'assigned':['quality','release_approval','ready_release'].includes(row.stage)?'review':'progress';
const COLUMNS=[{id:'assigned',label:'Assigned'},{id:'progress',label:'In progress'},{id:'review',label:'Review / Approval'},{id:'done',label:'Completed'}];
const localDate=()=>{const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;};
const dueWithinWeek=(row:HubRow)=>{if(!row.due_date||columnOf(row)==='done')return false;const today=Date.parse(localDate()+'T00:00:00Z'),due=Date.parse(String(row.due_date).slice(0,10)+'T00:00:00Z');return Number.isFinite(due)&&due>=today&&due<=today+7*86400000;};

export function TeamActivityBoard({items,users,actions,onOpen,onEvidence,onAction,onNewTask,onNewProject}:{items:HubRow[];users:HubRow[];actions:Record<string,HubRow[]>;onOpen:(project:string,item?:string)=>void;onEvidence:(project:string,item:string)=>void;onAction:(item:HubRow,action:HubRow)=>void;onNewTask:()=>void;onNewProject:()=>void}){
  const {user}=useAccount();const [query,setQuery]=useState(''),[person,setPerson]=useState(''),[scope,setScope]=useState('all'),[project,setProject]=useState(''),[notice,setNotice]=useState(''),[over,setOver]=useState(''),[view,setView]=useState<'board'|'timeline'|'list'>('board');
  const projects=useMemo(()=>items.filter(row=>row.type==='project'),[items]);
  const name=(id:number)=>users.find(row=>row.id===id)?.username||'Account unavailable';
  const projectName=(row:HubRow)=>row.type==='project'?'Project':projects.find(p=>p.id===row.project_id)?.title||'Project unavailable';
  const visible=items.filter(row=>(!person||[row.owner_id,row.current_user_id,row.latest_iteration?.author_id].includes(Number(person)))&&(scope==='all'||row.type===scope)&&(!project||row.project_id===project||row.id===project)&&(`${row.title} ${projectName(row)} ${name(row.owner_id)}`).toLowerCase().includes(query.toLowerCase())).sort((a,b)=>String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
  const counts=COLUMNS.map(column=>visible.filter(row=>columnOf(row)===column.id).length);
  const drop=(event:DragEvent,column:string)=>{
    event.preventDefault();setOver('');const row=items.find(row=>row.id===event.dataTransfer.getData('text/workhub-item'));
    if(!row||columnOf(row)===column)return;
    if(row.current_user_id!==user.id){setNotice('Open the work item to see its assigned owner or reviewer.');return;}
    if(row.type==='project'&&column==='done'&&row.stage!=='ready_release'){setNotice('Projects enter Completed after quality, release approval and release closure.');return;}
    const id=row.stage==='ready_release'&&column==='done'?'release':row.stage==='todo'&&column==='progress'?'start':row.stage==='development'&&column==='done'?'complete_development':row.stage==='development_completed'&&column==='progress'?'continue_development':row.stage==='released'&&column==='progress'?'reopen':'';
    const action=(actions[row.stage]||[]).find(action=>action.id===id);
    if(action){setNotice('');onAction(row,action);}else setNotice('Open this item to use its assigned quality or release action.');
  };
  return <section className="wh-team-activity" aria-label="Team activity workspace">
    <div className="wh-team-summary" aria-label="Team activity summary">{[
      {label:'Projects',value:visible.filter(row=>row.type==='project').length,Icon:FolderOpen,tone:'blue'},
      {label:'Tasks',value:visible.filter(row=>row.type==='task').length,Icon:ClipboardCheck,tone:'green'},
      {label:'Due in 7 days',value:visible.filter(dueWithinWeek).length,Icon:CalendarDays,tone:'amber'},
      {label:'Review / Approval',value:counts[2],Icon:ClipboardCheck,tone:'purple'},
      {label:'Blocked',value:visible.filter(row=>row.stage==='blocked').length,Icon:Activity,tone:'red'},
      {label:'Completed',value:counts[3],Icon:Check,tone:'green'},
    ].map(({label,value,Icon,tone})=><article className={'wh-team-stat '+tone} key={label}><span><Icon size={21}/></span><div><strong>{value}</strong><small>{label}</small></div></article>)}</div>
    <div className="wh-team-controls"><label className="wh-search"><Search size={16}/><input className="textInput" aria-label="Search team work" placeholder="Search tasks, projects or owner" value={query} onChange={event=>setQuery(event.target.value)}/></label><select className="textInput" aria-label="Filter project" value={project} onChange={event=>setProject(event.target.value)}><option value="">All projects</option>{projects.map(row=><option key={row.id} value={row.id}>{row.title}</option>)}</select><select className="textInput" aria-label="Filter team member" value={person} onChange={event=>setPerson(event.target.value)}><option value="">All users</option>{users.map(row=><option key={row.id} value={row.id}>{row.username}</option>)}</select><select className="textInput" aria-label="Filter work type" value={scope} onChange={event=>setScope(event.target.value)}><option value="all">Projects and tasks</option><option value="project">Projects</option><option value="task">Tasks</option></select></div>
    <div className="wh-team-heading"><div><h2>Team activity</h2><p>Track project progress, engineering tasks and review status.</p></div><div className="wh-team-toolbar"><div className="wh-team-view-switch" role="group" aria-label="Team activity view"><button type="button" className={view==='board'?'active':''} aria-pressed={view==='board'} onClick={()=>setView('board')}><LayoutGrid size={15}/>Projects &amp; Tasks</button><button type="button" className={view==='timeline'?'active':''} aria-pressed={view==='timeline'} onClick={()=>setView('timeline')}><CalendarDays size={15}/>Timeline</button><button type="button" className={view==='list'?'active':''} aria-pressed={view==='list'} onClick={()=>setView('list')}><List size={15}/>List</button></div><button className="btn primary" onClick={onNewTask}><Plus size={15}/>New Task</button><button className="btn" onClick={onNewProject}><FolderOpen size={15}/>New Project</button></div></div>
    <p className="wh-team-note">Projects are completed after release; tasks are completed when development is complete. Filters apply to all views and totals.</p>{notice&&<p role="status" className="wh-warning">{notice}</p>}
    {view==='board'&&<div className="wh-team-board">{COLUMNS.map((column,index)=><section key={column.id} className={'wh-team-column '+column.id+(over===column.id?' drop-target':'')} onDragOver={event=>{if(event.dataTransfer.types.includes('text/workhub-item')){event.preventDefault();setOver(column.id);}}} onDragLeave={()=>setOver('')} onDrop={event=>drop(event,column.id)}>
      <header><h3><i aria-hidden="true"/>{column.label}</h3><span>{counts[index]}</span></header>
      {visible.filter(row=>columnOf(row)===column.id).map(row=>{const latest=row.type==='project'?row.latest_iteration:null;const owner=users.find(person=>person.id===row.current_user_id);const progress=Number(row.progress);return <article key={row.id} className="wh-team-card" draggable={row.current_user_id===user.id} onDragStart={event=>{event.dataTransfer.setData('text/workhub-item',row.id);event.dataTransfer.effectAllowed='move';}}>
        <button className="wh-team-card-title" onClick={()=>onOpen(row.project_id,row.id)}>{row.title}<ChevronRight size={16}/></button><p className="wh-team-project-name">{projectName(row)}</p>
        {row.progress!=null&&Number.isFinite(progress)&&<div className="wh-team-progress" title={row.type==='task'?'Development completion':'Project completion'}><progress aria-label={(row.type==='task'?'Development':'Project')+' completion for '+row.title} max={100} value={Math.max(0,Math.min(100,progress))}/><span>{Math.round(progress)}%</span></div>}
        <div className="wh-team-card-tags"><span className={'wh-stage wh-stage-'+row.stage}>{row.stage_label||row.stage}</span>{(latest?.kind||row.kind)&&<span className="wh-work-type">{latest?(TOOLS[latest.kind]||latest.kind):row.kind}</span>}</div>
        {latest&&<div className="wh-team-iteration" title={'Recorded by '+name(latest.author_id)}><GitBranch size={14}/><b>Iteration {latest.iteration}</b><small>{latest.status}</small></div>}
        <footer><span title={row.current_user_id===row.owner_id?'Development owner':'Current responsibility'}>{owner?.avatarUrl?<img src={owner.avatarUrl} alt=""/>:<i>{name(row.current_user_id).slice(0,2).toUpperCase()}</i>}{name(row.current_user_id)}</span><small><CalendarDays size={13}/>{row.due_date?dayLabel(row.due_date):'No due date'}</small></footer>
        <div className="wh-team-card-actions"><button className="btn" onClick={()=>onEvidence(row.project_id,row.id)}><FileText size={13}/>Open work details</button>{row.current_user_id===user.id&&(actions[row.stage]||[]).slice(0,1).map(action=><button className="btn" key={action.id} onClick={()=>onAction(row,action)}>{action.label}</button>)}</div>
      </article>;})}{!counts[index]&&<p className="wh-muted wh-board-empty">No work here yet.</p>}
    </section>)}</div>}
    {view==='timeline'&&<ProjectGantt title="Team work timeline" description="Recorded dates for the selected projects and tasks." items={visible} users={users} onOpen={row=>onOpen(row.project_id,row.id)}/>}
    {view==='list'&&<div className="card tableWrap wh-team-list"><table className="wh-table"><thead><tr><th>Work</th><th>Project</th><th>Status</th><th>Current responsibility</th><th>Due</th><th>Updated</th></tr></thead><tbody>{visible.map(row=><tr key={row.id}><td><button className="wh-text-link" onClick={()=>onOpen(row.project_id,row.id)}>{row.title}</button></td><td>{projectName(row)}</td><td><span className={'wh-stage wh-stage-'+row.stage}>{row.stage_label||row.stage}</span></td><td>{name(row.current_user_id)}</td><td>{row.due_date?dayLabel(row.due_date):'Not scheduled'}</td><td>{row.updated_at?when(row.updated_at):'—'}</td></tr>)}</tbody></table>{!visible.length&&<p className="wh-empty">No work matches the current filters.</p>}</div>}
  </section>;
}
