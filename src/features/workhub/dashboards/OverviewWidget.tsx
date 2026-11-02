import {Activity,ArrowRight,CalendarDays,ClipboardCheck,FolderOpen,Users} from 'lucide-react';
import {dayLabel,when,type HubRow as Row} from '../projectApi';
import type {Widget} from './model';
import './overview-widgets.css';

export type OverviewContext={items:Row[];userId:number;pending:number|null;editing:boolean;onView:(view:string)=>void;onOpen:(row:Row)=>void};
const done=(r:Row)=>r.stage==='released'||r.type==='task'&&r.stage==='development_completed';
const SHORTCUTS={
 work:{view:'mine',caption:'Your current responsibilities',Icon:ClipboardCheck},
 projects:{view:'projects',caption:'Open the project portfolio',Icon:FolderOpen},
 approvals:{view:'approvals',caption:'Documents, workflow and time',Icon:ClipboardCheck},
 team:{view:'workload',caption:'Plan resources and availability',Icon:Users}
};

export function OverviewWidget({widget:w,context:c}:{widget:Widget;context:OverviewContext}){
 const key=w.overview?.content||'work',limit=w.overview?.limit||4;
 const projects=c.items.filter(r=>r.type==='project'),mine=c.items.filter(r=>r.current_user_id===c.userId&&!done(r));
 const view=(target:string)=>{if(!c.editing)c.onView(target);},open=(row:Row)=>{if(!c.editing)c.onOpen(row);};
 const inactive={'aria-disabled':c.editing,tabIndex:c.editing?-1:0};
 if(w.type==='workhub_shortcut'){
  const shortcut=SHORTCUTS[key as keyof typeof SHORTCUTS]||SHORTCUTS.work,{Icon}=shortcut;
  const value=key==='work'?mine.length:key==='projects'?projects.filter(r=>!done(r)).length:key==='approvals'?c.pending??'—':null;
  return <button className="db-overview-shortcut" {...inactive} onClick={()=>view(shortcut.view)}><span className="db-overview-icon"><Icon size={23}/></span><div>{value!==null&&<b>{value}</b>}<strong>{w.title}</strong><small>{w.overview?.caption||shortcut.caption}</small></div><ArrowRight size={18}/></button>;
 }
 const spec=key==='actions'?{Icon:ClipboardCheck,link:'All my work',view:'mine',empty:'No work is currently assigned to you.'}:key==='milestones'?{Icon:CalendarDays,link:'Projects',view:'projects',empty:'No upcoming milestones are scheduled.'}:key==='recent'?{Icon:FolderOpen,link:'View all',view:'projects',empty:'Create a project to start planning and sharing work.'}:{Icon:Activity,link:'',view:'',empty:''};
 const {Icon}=spec;
 const dated=(a:Row,b:Row)=>String(a.due_date||'9999').localeCompare(String(b.due_date||'9999'));
 const rows=(key==='actions'?[...mine].sort(dated):key==='milestones'?c.items.filter(r=>r.milestone&&r.due_date&&!done(r)).sort(dated):key==='recent'?[...projects].sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at))):[]).slice(0,limit);
 return <section className="db-overview-list"><header><h3><Icon size={18}/>{w.title}</h3>{spec.link&&<button {...inactive} onClick={()=>view(spec.view)}>{spec.link}<ArrowRight size={14}/></button>}</header>{w.overview?.caption&&<p className="db-overview-caption">{w.overview.caption}</p>}
 <div className="db-overview-rows">{key==='links'?[
  {title:'Team Activity',caption:'Assigned, in progress and completed work',view:'activity'},
  {title:'Team Management',caption:'Resources, capacity and responsibilities',view:'workload'},
  {title:'Document Management',caption:'MOM, FRD, reports, FAT and closure',view:'documents'}
 ].map(row=><button className="db-overview-row" {...inactive} key={row.view} onClick={()=>view(row.view)}><span><strong>{row.title}</strong><small>{row.caption}</small></span><ArrowRight size={16}/></button>):rows.map(row=><button className="db-overview-row" {...inactive} key={row.id} onClick={()=>open(row)}><span><strong>{row.title}</strong><small>{key==='recent'?`${row.project_number||'Number not recorded'} · ${when(row.updated_at)}`:key==='milestones'?projects.find(p=>p.id===row.project_id)?.title||'Project milestone':(row.type!=='project'?(projects.find(p=>p.id===row.project_id)?.title||'Project')+' / ':'')+(row.stage_label||row.stage.replaceAll('_',' '))}</small></span><span>{key==='recent'?row.health||row.stage_label:row.due_date?dayLabel(row.due_date):'No due date'}<ArrowRight size={14}/></span></button>)}{key!=='links'&&!rows.length&&<p className="db-overview-empty">{spec.empty}</p>}</div></section>;
}
