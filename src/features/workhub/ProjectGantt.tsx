import {useEffect,useId,useMemo,useRef,useState,type PointerEvent,type KeyboardEvent} from 'react';
import {CalendarDays,Check,Diamond,Pencil,Plus} from 'lucide-react';
import {dayLabel,type HubRow} from './projectApi';
import './gantt.css';

const DAY=86400000,LABEL=290,HEIGHT=72;
const done=(row:HubRow)=>row.type==='project'?row.stage==='released':['development_completed','released'].includes(row.stage);
const percentage=(row:HubRow)=>Math.round(Math.max(0,Math.min(100,Number(row.progress)||0)));
const dateNumber=(value:string|undefined)=>value?Date.parse(value.slice(0,10)+'T00:00:00Z'):NaN;
const todayDate=()=>{const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;};
const labelDate=(value:number)=>new Date(value).toLocaleDateString(undefined,{day:'numeric',month:'short',timeZone:'UTC'});
const iso=(value:number)=>new Date(value).toISOString().slice(0,10);
type Range={start_date:string;due_date:string};
type Drag={row:HubRow;mode:string;x:number;start:number;end:number;next:Range;changed:boolean};

type Props={title?:string;description?:string;items:HubRow[];users:HubRow[];selectedId?:string;
  onOpen:(row:HubRow)=>void;onAdd?:()=>void;onEdit?:(row:HubRow)=>void;canEdit?:(row:HubRow)=>boolean;
  onSchedule?:(row:HubRow,range:Range)=>Promise<void>|void;ordered?:boolean;};

export function ProjectGantt({title='Workflow & timeline',description='Plan this project with your own steps, dates, assignees and dependencies.',items,users,selectedId,onOpen,onAdd,onEdit,canEdit,onSchedule,ordered=false}:Props){
  const [zoom,setZoom]=useState('weeks');
  const drag=useRef<Drag|null>(null),suppressClick=useRef(false);
  const [preview,setPreview]=useState<{id:string;range:Range}|null>(null),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const scroll=useRef<HTMLDivElement>(null),[available,setAvailable]=useState(800);
  const marker=useId().replace(/:/g,'')+'-dependency';
  const rows=useMemo(()=>ordered?items:[...items].sort((a,b)=>a.type==='project'&&b.type!=='project'?-1:b.type==='project'&&a.type!=='project'?1:(dateNumber(a.start_date||a.due_date)||Infinity)-(dateNumber(b.start_date||b.due_date)||Infinity)||String(a.created_at).localeCompare(String(b.created_at))),[items,ordered]);
  useEffect(()=>{const cancel=(event:globalThis.KeyboardEvent)=>{if(event.key==='Escape'){drag.current=null;setPreview(null);}};window.addEventListener('keydown',cancel);return()=>window.removeEventListener('keydown',cancel);},[]);
  useEffect(()=>{const element=scroll.current;if(!element)return;const resize=()=>setAvailable(Math.max(800,element.clientWidth-LABEL));resize();const observer=new ResizeObserver(resize);observer.observe(element);return()=>observer.disconnect();},[rows.length]);
  const today=dateNumber(todayDate());
  const values=rows.flatMap(row=>[row.start_date,row.due_date,row.baseline_due,row.started_at,row.completed_at]).map(dateNumber).filter(Number.isFinite);
  const first=values.length?Math.min(...values):today,last=values.length?Math.max(...values):today+DAY*27;
  const minimum=Math.floor(first/DAY)*DAY-3*DAY,maximum=Math.max(last+4*DAY,minimum+14*DAY),days=(maximum-minimum)/DAY;
  const width=Math.min(32000,Math.max(available,days*({days:34,weeks:13,months:5}[zoom]||13)));
  const x=(value:number)=>(value-minimum)/(maximum-minimum)*width;
  const ticks:number[]=[];const interval=Math.max(1,Math.ceil((zoom==='days'?1:zoom==='weeks'?7:30)*Math.max(1,days/600)));
  for(let value=minimum;value<maximum;value+=interval*DAY)ticks.push(value);
  const months:{start:number;end:number;label:string}[]=[];
  let month=new Date(minimum);month.setUTCDate(1);
  for(let index=0;month.getTime()<maximum&&index<1200;index++){
    const start=month.getTime(),label=month.toLocaleDateString(undefined,{month:'long',year:'numeric',timeZone:'UTC'});
    month=new Date(start);month.setUTCMonth(month.getUTCMonth()+1);
    months.push({start:Math.max(minimum,start),end:Math.min(maximum,month.getTime()),label});
  }
  const position=(row:HubRow)=>{const current=preview&&preview.id===row.id?{...row,...preview.range}:row,start=dateNumber(current.start_date||current.due_date),end=dateNumber(current.due_date||current.start_date);return Number.isFinite(start)?{start:x(start),end:x(Math.max(start,end)+DAY)}:null;};
  const saveRange=async(row:HubRow,range:Range)=>{if(!onSchedule)return;setSaving(true);setError('');try{await onSchedule(row,range);}catch(error){setError((error as Error).message);}finally{setSaving(false);setPreview(null);}};
  const begin=(event:PointerEvent<HTMLElement>,row:HubRow,mode='move')=>{if(!onSchedule||!canEdit?.(row)||saving||!row.start_date||!row.due_date||event.button!==0)return;event.stopPropagation();event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);suppressClick.current=false;drag.current={row,mode,x:event.clientX,start:dateNumber(row.start_date),end:dateNumber(row.due_date),next:{start_date:row.start_date,due_date:row.due_date},changed:false};};
  const move=(event:PointerEvent<HTMLElement>)=>{const current=drag.current;if(!current)return;const delta=Math.round((event.clientX-current.x)/(width/days))*DAY;let start=current.start,end=current.end;if(current.mode==='start')start=Math.min(end,start+delta);else if(current.mode==='end')end=Math.max(start,end+delta);else{start+=delta;end+=delta;}if(start<dateNumber('0001-01-01')||end>dateNumber('9999-12-31'))return;current.next={start_date:iso(start),due_date:iso(end)};current.changed=start!==current.start||end!==current.end;setPreview({id:current.row.id,range:current.next});};
  const finish=(event:PointerEvent<HTMLElement>)=>{const current=drag.current;if(!current)return;drag.current=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);if(current.changed){suppressClick.current=true;void saveRange(current.row,current.next);}else setPreview(null);};
  const cancel=()=>{drag.current=null;setPreview(null);};
  const keyboard=(event:KeyboardEvent<HTMLButtonElement>,row:HubRow)=>{if(!event.altKey||!['ArrowLeft','ArrowRight'].includes(event.key)||!onSchedule||!canEdit?.(row)||saving||!row.start_date||!row.due_date)return;event.preventDefault();const delta=event.key==='ArrowLeft'?-DAY:DAY,start=dateNumber(row.start_date),end=dateNumber(row.due_date);const nextStart=event.shiftKey&&!row.milestone?start:start+delta,nextEnd=row.milestone?nextStart:Math.max(nextStart,end+delta);if(nextStart<dateNumber('0001-01-01')||nextEnd>dateNumber('9999-12-31'))return;const range={start_date:iso(nextStart),due_date:iso(nextEnd)};void saveRange(row,range);};
  const names=(row:HubRow)=>users.find(user=>user.id===row.owner_id)?.username||'Account unavailable';
  return <section className="card wh-gantt" aria-label={title}>
    <header className="wh-section-heading"><div><h2>{title}</h2><p>{description}</p></div><div className="actions"><label>Scale<select aria-label="Timeline scale" value={zoom} onChange={event=>setZoom(event.target.value)}><option value="days">Days</option><option value="weeks">Weeks</option><option value="months">Months</option></select></label>{onAdd&&<button type="button" className="btn primary" onClick={onAdd}><Plus size={15}/>Add workflow step</button>}</div></header>
    <div className="wh-gantt-legend"><span><i className="planned"/>Planned work</span><span><Check size={13}/>Completed work</span><span><Diamond size={13}/>Milestone</span><span><i className="today"/>Today</span><small>{onSchedule?'Drag bars to move dates; drag either end to resize. Alt + arrows moves one day; add Shift to resize.':'Development, quality and release contribute to project completion.'}</small></div>
    {error&&<p role="alert" className="wh-error">{error}</p>}{saving&&<p role="status" className="wh-muted">Saving timeline dates...</p>}
    {!rows.length?<div className="wh-empty"><CalendarDays size={30}/><h3>No work assigned</h3><p>Assigned projects and workflow steps will appear here.</p></div>:<div className="wh-gantt-scroll" ref={scroll} tabIndex={0} aria-label="Scrollable project timeline"><div className="wh-gantt-grid" style={{width:LABEL+width}}>
      <div className="wh-gantt-axis"><div className="wh-gantt-label">Work / Assignee</div><div className="wh-gantt-calendar" style={{width}}>{months.map(month=><span className="wh-gantt-month" key={month.start} style={{left:x(month.start),width:x(month.end)-x(month.start)}}>{month.label}</span>)}{ticks.map(value=><span className="wh-gantt-tick" key={value} style={{left:x(value)}}>{labelDate(value)}</span>)}</div></div>
      <div className="wh-gantt-body">
        <svg className="wh-gantt-connectors" width={width} height={rows.length*HEIGHT} style={{left:LABEL}} aria-hidden="true"><defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z"/></marker></defs>{rows.flatMap((row,index)=>{const target=position(row);if(!target)return [];return (row.dependencies||[]).map((id:string)=>{const previous=rows.findIndex(source=>source.id===id),source=previous>=0?position(rows[previous]):null;if(!source)return null;const end=rows[previous].milestone?source.start:source.end,start=row.milestone?target.start:target.start-3,y1=previous*HEIGHT+HEIGHT/2,y2=index*HEIGHT+HEIGHT/2,turn=Math.max(end+12,start-16);return <path key={id+'-'+row.id} d={`M${end},${y1} H${turn} V${y2} H${start}`} markerEnd={`url(#${marker})`}/>;});})}</svg>
        {today>=minimum&&today<=maximum&&<div className="wh-gantt-today" style={{left:LABEL+x(today),height:rows.length*HEIGHT}} title={'Today: '+dayLabel(todayDate())}/>}
        {rows.map(row=>{const location=position(row),editable=!!onEdit&&!!canEdit?.(row),draggable=!!onSchedule&&!!canEdit?.(row)&&!!row.start_date&&!!row.due_date&&!saving,partial=!row.milestone&&(!row.start_date||!row.due_date),percent=percentage(row),current=preview&&preview.id===row.id?{...row,...preview.range}:row;const caption=`${row.title} / ${percent}% complete / ${names(row)} / ${row.stage_label||row.stage} / Start: ${dayLabel(current.start_date)} / Finish: ${dayLabel(current.due_date)}`;return <div className={'wh-gantt-row'+(row.id===selectedId?' selected':'')+' kind-'+row.type} key={row.id} style={{height:HEIGHT}}>
          <div className="wh-gantt-label"><button type="button" className="wh-gantt-name" onClick={()=>onOpen(row)} title={row.title}><strong>{row.milestone&&<Diamond size={12}/>} {row.title}</strong><small>{names(row)} / {row.stage_label||row.stage}</small></button><span className="wh-gantt-percent" title="Work completed" aria-label={percent+'% complete'}>{percent}%</span>{editable&&<button type="button" className="wh-gantt-edit" aria-label={'Edit workflow plan: '+row.title} onClick={()=>onEdit?.(row)}><Pencil size={14}/></button>}</div>
          <div className="wh-gantt-track" style={{width,backgroundSize:`${width/days*interval}px 100%`}}>
            {location?<button type="button" className={'wh-gantt-bar '+row.stage+' type-'+row.type+(row.phase?' phase-'+row.phase:'')+(row.type==='project'?' project':'')+(row.milestone?' milestone':'')+(done(row)?' done':'')+(draggable?' movable':'')+(preview?.id===row.id?' dragging':'')} style={{left:location.start,width:row.milestone?20:partial?50:Math.max(22,location.end-location.start)}} title={caption} aria-label={caption} onPointerDown={event=>begin(event,row)} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancel} onKeyDown={event=>keyboard(event,row)} onClick={()=>{if(suppressClick.current){suppressClick.current=false;return;}onOpen(row);}}>{row.milestone?<Diamond size={21} fill="currentColor"/>:<><i className="wh-gantt-progress-fill" style={{width:percent+'%'}}/>{draggable&&<span className="wh-gantt-resize start" aria-hidden="true" onPointerDown={event=>begin(event,row,'start')} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancel}/>}<span>{partial?(row.start_date?'Start':'Due'):row.title}</span>{!partial&&<b>{percent}%</b>}{done(row)&&<Check size={14}/>}{draggable&&<span className="wh-gantt-resize end" aria-hidden="true" onPointerDown={event=>begin(event,row,'end')} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancel}/>}</>}</button>:editable?<button type="button" className="wh-gantt-unscheduled" onClick={()=>onEdit?.(row)}>Set dates</button>:<span className="wh-gantt-unscheduled">Unscheduled</span>}
            {row.baseline_due&&Number.isFinite(dateNumber(row.baseline_due))&&<i className="wh-gantt-baseline" style={{left:x(dateNumber(row.baseline_due)+DAY)}} title={'Original due: '+dayLabel(row.baseline_due)}/>}
          </div>
        </div>;})}
      </div>
    </div></div>}
  </section>;
}
