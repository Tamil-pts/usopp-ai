import {useEffect,useState} from 'react';
import {metricNumber,type QuestionTable} from './reportDashboard';

function numeric(value:string|number){
 if(typeof value==='number')return Number.isFinite(value)?value:null;
 const text=value.trim();
 if(/^[+-]?[\d,]+(?:\.\d+)?$/.test(text))return Number(text.replaceAll(',',''));
 const time=text.match(/^(\d+):(\d{2}):(\d{2})$/);
 return time?Number(time[1])*60+Number(time[2])+Number(time[3])/60:null;
}
export function QuestionResultChart({table}:{table:QuestionTable}){
 const available=table.headers.map((label,index)=>({label,index})).filter(column=>column.index>0&&!/^(?:records|first recorded date|last recorded date)$/i.test(column.label)&&table.rows.some(row=>numeric(row[column.index])!=null));
 const [chosen,setChosen]=useState('all');
 useEffect(()=>setChosen('all'),[table]);
 const metric=available.find(column=>column.label===chosen)||available[0];
 if(!metric||table.rows.length<2)return null;
 const displayed=chosen==='all'?available.slice(0,4):[metric];
 return <div className="questionResultChart"><header><span>Requested measures · separate scales and source units</span><label>Measure<select aria-label="Question chart measure" value={chosen} onChange={event=>setChosen(event.target.value)}><option value="all">All requested measures</option>{available.map(column=><option key={column.index}>{column.label}</option>)}</select></label></header>
  <div className="questionMeasures">{displayed.map(measure=>{
   const rows=table.rows.filter(row=>numeric(row[measure.index])!=null).slice(0,20);
   const maximum=Math.max(1,...rows.map(row=>Math.abs(numeric(row[measure.index])||0)));
   const isTime=rows.some(row=>typeof row[measure.index]==='string'&&String(row[measure.index]).includes(':'));
   return <section key={measure.index}><h4>{measure.label}{isTime?' · minutes':''}</h4><div className="questionChartBars">{rows.map((row,index)=>{const value=numeric(row[measure.index])||0;const label=table.headers.map((header,i)=>({header,value:row[i],index:i})).filter(item=>item.index===0||item.index!==measure.index&&/lot|yarn count|tpi/i.test(item.header)).map(item=>String(item.value)).join(' · ');return <div key={index} title={`${label}: ${row[measure.index]}`}><span>{label}</span><div><i style={{width:`${Math.max(0,Math.abs(value)/maximum*100)}%`}}/></div><b>{metricNumber(value)}{isTime?' min':''}</b></div>})}</div></section>;
  })}</div>{table.rows.length>20&&<small>Each chart shows the first 20 displayed rows. The table contains the remaining results.</small>}{chosen==='all'&&available.length>4&&<small>The first four measures are charted. Select another measure above to view it.</small>}</div>;
}
