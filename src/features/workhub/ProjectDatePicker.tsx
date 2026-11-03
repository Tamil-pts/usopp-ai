import {useEffect,useLayoutEffect,useRef,useState,type KeyboardEvent} from 'react';
import {createPortal} from 'react-dom';
import {CalendarDays,ChevronLeft,ChevronRight,ChevronsLeft,ChevronsRight} from 'lucide-react';
import {useWorkHubDialog} from './useWorkHubDialog';
import './project-date-picker.css';

type Range={from_date:string;to_date:string};
type Mode='day'|'week'|'month'|'range';
type Props={value:Range;onChange:(value:Range)=>void;label?:string};
const MODES:Mode[]=['day','week','month','range'];
const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
const WEEKDAYS=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const DAY=86400000;
const parse=(value:string)=>new Date(value+'T00:00:00Z');
const iso=(value:Date)=>value.toISOString().slice(0,10);
const shift=(value:Date,n:number)=>new Date(value.getTime()+n*DAY);
const monthStart=(value:Date)=>new Date(Date.UTC(value.getUTCFullYear(),value.getUTCMonth(),1));
const addMonths=(value:Date,n:number)=>new Date(Date.UTC(value.getUTCFullYear(),value.getUTCMonth()+n,1));
const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const caption=(value:string)=>parse(value).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const dayName=(value:string)=>parse(value).toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
function selectedPeriod(value:string,mode:Mode):Range{
 const d=parse(value);
 if(mode==='week'){const first=shift(d,-d.getUTCDay());return {from_date:iso(first),to_date:iso(shift(first,6))};}
 if(mode==='month')return {from_date:iso(monthStart(d)),to_date:iso(shift(addMonths(d,1),-1))};
 return {from_date:value,to_date:value};
}
function weekNumber(first:Date){
 const thursday=shift(first,4),yearStart=new Date(Date.UTC(thursday.getUTCFullYear(),0,1));
 return Math.ceil(((thursday.getTime()-yearStart.getTime())/DAY+1)/7);
}
function rangeLabel(value:Range){
 if(!value.from_date&&!value.to_date)return 'All dates';
 if(!value.to_date)return 'From '+caption(value.from_date);
 if(!value.from_date)return 'Until '+caption(value.to_date);
 return value.from_date===value.to_date?caption(value.from_date):caption(value.from_date)+' – '+caption(value.to_date);
}

function CalendarDialog({value,initialMode,anchor,close,apply}:{value:Range;initialMode:Mode;anchor:HTMLButtonElement|null;close:()=>void;apply:(range:Range,mode:Mode)=>void}){
 const [mode,setMode]=useState<Mode>(initialMode),[draft,setDraft]=useState<Range>({...value}),[month,setMonth]=useState(()=>monthStart(parse(value.from_date||value.to_date||today()))),[pickingEnd,setPickingEnd]=useState(false);
 const root=useWorkHubDialog(close),[position,setPosition]=useState({left:12,top:12,width:360,maxHeight:500});
 useEffect(()=>{root.current?.querySelector<HTMLButtonElement>('[role=tab][aria-selected=true]')?.focus();},[root]);
 useLayoutEffect(()=>{
  const place=()=>{const v=window.visualViewport,x=v?.offsetLeft||0,y=v?.offsetTop||0,w=v?.width||innerWidth,h=v?.height||innerHeight,r=anchor?.getBoundingClientRect(),width=Math.min(mode==='range'?700:370,w-24),height=Math.min(root.current?.scrollHeight||500,h-24);setPosition({left:Math.max(x+12,Math.min(r?.left||x+12,x+w-width-12)),top:Math.max(y+12,Math.min((r?.bottom||y)+8,y+h-height-12)),width,maxHeight:h-24});};
  place();const observer=new ResizeObserver(place);if(root.current)observer.observe(root.current);window.addEventListener('resize',place);window.visualViewport?.addEventListener('resize',place);
  return()=>{observer.disconnect();window.removeEventListener('resize',place);window.visualViewport?.removeEventListener('resize',place);};
 },[anchor,mode,root]);
 const invalid=!!(draft.from_date&&draft.to_date&&draft.from_date>draft.to_date);
 const select=(day:string)=>{
  if(mode!=='range'){setDraft(selectedPeriod(day,mode));return;}
  if(!pickingEnd){setDraft({from_date:day,to_date:''});setPickingEnd(true);}
  else{setDraft({from_date:day<draft.from_date?day:draft.from_date,to_date:day<draft.from_date?draft.from_date:day});setPickingEnd(false);}
 };
 const chooseMode=(next:Mode)=>{setMode(next);setPickingEnd(false);if(next!=='range')setDraft(selectedPeriod(draft.from_date||draft.to_date||today(),next));};
 const moveMonth=(n:number)=>setMonth(current=>{const next=addMonths(current,n);return next.getUTCFullYear()>=100&&next.getUTCFullYear()<=9998?next:current;});
 const focusDay=(event:KeyboardEvent<HTMLButtonElement>,day:string)=>{
  const offset:Record<string,number>={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};let target:Date;
  if(event.key in offset)target=shift(parse(day),offset[event.key]);
  else if(event.key==='Home')target=shift(parse(day),-parse(day).getUTCDay());
  else if(event.key==='End')target=shift(parse(day),6-parse(day).getUTCDay());
  else return;
  event.preventDefault();if(target<month||target>=addMonths(month,mode==='range'?2:1))setMonth(monthStart(target));
  requestAnimationFrame(()=>{const key=iso(target);(root.current?.querySelector<HTMLButtonElement>(`td:not(.outside) button[data-date="${key}"]`)||root.current?.querySelector<HTMLButtonElement>(`button[data-date="${key}"]`))?.focus();});
 };
 const calendar=(visibleMonth:Date,index:number)=>{
  const start=monthStart(visibleMonth),first=shift(start,-start.getUTCDay()),last=shift(addMonths(start,1),-1),weeks=Math.ceil((start.getUTCDay()+last.getUTCDate())/7),thisMonth=visibleMonth.getUTCMonth();
  return <section className="pp-calendar-month" key={iso(visibleMonth)} aria-label={MONTHS[thisMonth]+' '+visibleMonth.getUTCFullYear()}>
   <header>{index===0&&<div className="pp-calendar-nav"><button type="button" aria-label="Previous year" onClick={()=>moveMonth(-12)}><ChevronsLeft size={16}/></button><button type="button" aria-label="Previous month" onClick={()=>moveMonth(-1)}><ChevronLeft size={16}/></button></div>}
    <div className="pp-calendar-heading"><select aria-label={'Calendar month '+(index+1)} value={thisMonth} onChange={e=>setMonth(new Date(Date.UTC(visibleMonth.getUTCFullYear(),Number(e.target.value)-index,1)))}>{MONTHS.map((m,i)=><option key={m} value={i}>{m}</option>)}</select><input aria-label={'Calendar year '+(index+1)} type="number" min={100} max={9998} key={visibleMonth.getUTCFullYear()} defaultValue={visibleMonth.getUTCFullYear()} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();}} onBlur={e=>{const year=Number(e.target.value);if(year>=100&&year<=9998)setMonth(new Date(Date.UTC(year,thisMonth-index,1)));else e.currentTarget.value=String(visibleMonth.getUTCFullYear());}}/></div>
    {index===(mode==='range'?1:0)&&<div className="pp-calendar-nav"><button type="button" aria-label="Next month" onClick={()=>moveMonth(1)}><ChevronRight size={16}/></button><button type="button" aria-label="Next year" onClick={()=>moveMonth(12)}><ChevronsRight size={16}/></button></div>}
   </header>
   <table className="pp-calendar-grid"><thead><tr><th scope="col"><span className="pp-date-sr">Week</span></th>{WEEKDAYS.map(day=><th scope="col" key={day}>{day}</th>)}</tr></thead><tbody>{Array.from({length:weeks},(_,week)=>{const firstDay=shift(first,week*7);return <tr key={week}><th scope="row"><button type="button" aria-label={'Select week starting '+dayName(iso(firstDay))} onClick={()=>{setMode('week');setDraft(selectedPeriod(iso(firstDay),'week'));setPickingEnd(false);}}>{weekNumber(firstDay)}</button></th>{WEEKDAYS.map((_,i)=>{const d=shift(firstDay,i),key=iso(d),selected=!!draft.from_date&&key>=draft.from_date&&key<=(draft.to_date||draft.from_date),edge=key===draft.from_date||key===draft.to_date;return <td key={key} className={(selected?'selected ':'')+(edge?'edge ':'')+(d.getUTCMonth()!==thisMonth?'outside ':'')+(i===0||i===6?'weekend':'')}><button type="button" data-date={key} aria-label={dayName(key)} aria-pressed={selected} aria-current={key===today()?'date':undefined} onClick={()=>select(key)} onKeyDown={e=>focusDay(e,key)}>{d.getUTCDate()}</button></td>;})}</tr>;})}</tbody></table>
  </section>;
 };
 return createPortal(<div className="pp-date-overlay" onPointerDown={e=>{if(e.target===e.currentTarget)close();}}><section className={'pp-date-popover mode-'+mode} style={position} ref={root} role="dialog" aria-modal="true" aria-label="Choose dates">
  <div className="pp-date-tabs" role="tablist" aria-label="Date selection mode">{MODES.map((tab,i)=><button type="button" role="tab" id={'pp-date-tab-'+tab} aria-controls="pp-date-selection-panel" aria-selected={mode===tab} tabIndex={mode===tab?0:-1} key={tab} onClick={()=>chooseMode(tab)} onKeyDown={e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?3:(i+(e.key==='ArrowRight'?1:3))%4;chooseMode(MODES[next]);root.current?.querySelector<HTMLButtonElement>('#pp-date-tab-'+MODES[next])?.focus();}}>{tab[0].toUpperCase()+tab.slice(1)}</button>)}</div>
  <div id="pp-date-selection-panel" role="tabpanel" aria-labelledby={'pp-date-tab-'+mode}>
   {mode==='month'?<><div className="pp-month-year"><button type="button" aria-label="Previous year" onClick={()=>moveMonth(-12)}><ChevronsLeft size={16}/></button><input type="number" aria-label="Calendar year" min={100} max={9998} key={month.getUTCFullYear()} defaultValue={month.getUTCFullYear()} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();}} onBlur={e=>{const y=Number(e.target.value);if(y>=100&&y<=9998)setMonth(new Date(Date.UTC(y,month.getUTCMonth(),1)));else e.currentTarget.value=String(month.getUTCFullYear());}}/><button type="button" aria-label="Next year" onClick={()=>moveMonth(12)}><ChevronsRight size={16}/></button></div><div className="pp-month-options">{MONTHS.map((name,i)=>{const day=iso(new Date(Date.UTC(month.getUTCFullYear(),i,1)));return <button type="button" key={name} aria-label={name+' '+month.getUTCFullYear()} aria-pressed={draft.from_date===day} onClick={()=>setDraft(selectedPeriod(day,'month'))}>{name.slice(0,3)}</button>;})}</div></>:<div className="pp-calendars">{calendar(month,0)}{mode==='range'&&calendar(addMonths(month,1),1)}</div>}
   <p className="pp-date-selection" role="status">{rangeLabel(draft)}{mode==='week'&&<small>Sunday – Saturday</small>}{mode==='range'&&pickingEnd&&<small>Choose an end date.</small>}</p>
   {mode==='range'&&<div className="pp-date-inputs"><label>From date<input type="date" aria-label="From date" value={draft.from_date} onChange={e=>setDraft({...draft,from_date:e.target.value})}/></label><label>To date<input type="date" aria-label="To date" value={draft.to_date} onChange={e=>setDraft({...draft,to_date:e.target.value})}/></label></div>}
   {invalid&&<p className="wh-error" role="alert">The From date must be on or before the To date.</p>}
  </div>
  <footer><button type="button" className="pp-calendar-current" onClick={()=>{const now=today();setMonth(monthStart(parse(now)));setDraft(selectedPeriod(now,mode==='range'?'month':mode));setPickingEnd(false);}}>Current {mode==='range'?'month':mode}</button><button type="button" className="pp-calendar-current" onClick={()=>apply({from_date:'',to_date:''},mode)}>All dates</button><div><button type="button" className="btn primary" disabled={invalid||(!draft.from_date&&!draft.to_date)} onClick={()=>apply(draft,mode)}>OK</button><button type="button" className="btn" onClick={close}>Cancel</button></div></footer>
 </section></div>,document.body);
}

export function ProjectDatePicker({value,onChange,label='Choose project dates'}:Props){
 const trigger=useRef<HTMLButtonElement>(null),[open,setOpen]=useState(false),[mode,setMode]=useState<Mode>('range');
 return <><button type="button" className="btn pp-date-trigger" ref={trigger} aria-label={label} aria-haspopup="dialog" aria-expanded={open} onClick={()=>setOpen(true)}><CalendarDays size={16}/><span>{rangeLabel(value)}</span></button>{open&&<CalendarDialog value={value} initialMode={mode} anchor={trigger.current} close={()=>setOpen(false)} apply={(range,selection)=>{onChange(range);setMode(selection);setOpen(false);}}/>}</>;
}
