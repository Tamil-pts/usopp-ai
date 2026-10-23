import {useEffect,useId,useState} from 'react';
import {metricNumber,type PerformanceDashboard} from './reportDashboard';

const PALETTE=['#1677cf','#12a98a','#f5aa34','#8864dc','#ed6875','#8b9eb4'];
export function ReportTrend({data,metric='production',label='Production',unit='kg',line='utilization',onDate}:{data:PerformanceDashboard;metric?:string;label?:string;unit?:string;line?:string|null;onDate?:(day:string)=>void}){
 const id=useId().replace(/:/g,'');const [hover,setHover]=useState<number|null>(null);
 const rows=data.daily.filter(row=>typeof row[metric]==='number').slice(-60);
 if(!rows.length)return <div className="reportEmpty">No recorded {label.toLowerCase()} values in this period.</div>;
 const width=700,height=238,left=62,right=line?50:18,top=20,bottom=42;
 const plotWidth=width-left-right,plotHeight=height-top-bottom;
 const maximum=Math.max(...rows.map(row=>Number(row[metric])),1)*1.12,step=plotWidth/rows.length;
 const points=rows.map((row,index)=>typeof row[line||'']==='number'?`${left+step*(index+.5)},${top+plotHeight*(1-Math.min(100,Math.max(0,Number(row[line||''])))/100)}`:null);
 const hovered=hover==null?null:rows[hover];
 return <div className="reportTrend">
  <div className="reportChartLegend"><span><i style={{background:'#12a98a'}}/>{label} ({unit})</span>{line&&<span><i style={{background:'#ed9e35'}}/>Mean utilization (%)</span>}<small>Click a date to filter</small></div>
  <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label} by date${line?', with mean utilization on the right axis':''}`} onMouseLeave={()=>setHover(null)}>
   <defs><linearGradient id={`report-bars-${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#13b99a"/><stop offset="100%" stopColor="#087d78"/></linearGradient></defs>
   {[0,.25,.5,.75,1].map(fraction=><g key={fraction}><line x1={left} x2={width-right} y1={top+plotHeight*fraction} y2={top+plotHeight*fraction} className="reportGridLine"/><text x={left-10} y={top+plotHeight*fraction+4} textAnchor="end">{metricNumber(maximum*(1-fraction),0)}</text>{line&&<text x={width-right+10} y={top+plotHeight*fraction+4}>{Math.round(100*(1-fraction))}</text>}</g>)}
   {rows.map((row,index)=>{const value=Number(row[metric]),x=left+index*step+step*.15,y=top+plotHeight*(1-value/maximum);return <g key={row.date} tabIndex={0} role="button" aria-label={`${row.date}: ${metricNumber(value)} ${unit}. Filter this date.`} onMouseEnter={()=>setHover(index)} onFocus={()=>setHover(index)} onBlur={()=>setHover(null)} onClick={()=>onDate?.(row.date)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onDate?.(row.date)}}}>
    <rect x={x} y={y} width={Math.max(2,step*.7)} height={Math.max(0,top+plotHeight-y)} rx={Math.min(4,step*.12)} fill={hover===index?'#1677cf':`url(#report-bars-${id})`}/><rect x={left+index*step} y={top} width={step} height={plotHeight} fill="transparent"/>
    {(rows.length<15||index%Math.ceil(rows.length/10)===0)&&<text x={left+step*(index+.5)} y={height-17} textAnchor="middle">{row.date.slice(5)}</text>}
   </g>})}
   {line&&points.map((point,index)=>point&&points[index-1]?<line key={`segment-${index}`} x1={points[index-1]!.split(',')[0]} y1={points[index-1]!.split(',')[1]} x2={point.split(',')[0]} y2={point.split(',')[1]} stroke="#ed9e35" strokeWidth={3} pointerEvents="none"/>:null)}
   {line&&points.map((point,index)=>point?<circle key={index} cx={point.split(',')[0]} cy={point.split(',')[1]} r={3.5} fill="#fff" stroke="#ed9e35" strokeWidth={2} pointerEvents="none"/>:null)}
  </svg>
  <div className="reportChartReadout" role="status">{hovered?<><strong>{hovered.date}</strong><span>{metricNumber(Number(hovered[metric]))} {unit}</span>{line&&typeof hovered[line]==='number'&&<span>Utilization {metricNumber(Number(hovered[line]))}%</span>}</>:<span>Hover or focus a bar for the recorded values.</span>}{data.daily.length>60&&<small>Latest 60 dates shown.</small>}</div>
 </div>;
}

export function StoppageDonut({data}:{data:PerformanceDashboard}){
 const [selected,setSelected]=useState<number|null>(null);
 useEffect(()=>setSelected(null),[data]);
 const reasons=data.reasons.filter(r=>(r.minutes||0)>0),total=reasons.reduce((sum,r)=>sum+(r.minutes||0),0);
 if(!total)return <div className="reportEmpty">No positive-duration stoppages recorded for this selection.</div>;
 const top=reasons.slice(0,5).map(r=>({label:r.reason,value:r.minutes!,events:r.events,machines:r.machines}));
 if(reasons.length>5)top.push({label:`Other recorded reasons (${reasons.length-5})`,value:reasons.slice(5).reduce((sum,r)=>sum+r.minutes!,0),events:reasons.slice(5).reduce((sum,r)=>sum+r.events,0),machines:[]});
 let cursor=0;const stops=top.map((item,index)=>{const start=cursor;cursor+=item.value/total*100;return `${PALETTE[index]} ${start}% ${cursor}%`}).join(',');
 return <div className="reportDonutLayout"><div className="reportDonut" style={{background:`conic-gradient(${stops})`}} role="img" aria-label={`${metricNumber(total)} minutes recorded stoppage`}><div><strong>{metricNumber(total,1)}</strong><span>minutes</span><small>{data.reasons.reduce((sum,r)=>sum+r.events,0).toLocaleString()} events</small></div></div>
  <div className="reportDonutLegend">{top.map((item,index)=><button key={item.label} className={selected===index?'selected':''} onClick={()=>setSelected(selected===index?null:index)} aria-pressed={selected===index}><i style={{background:PALETTE[index]}}/><span title={item.label}>{item.label}<small>{item.events.toLocaleString()} events</small></span><strong>{metricNumber(item.value/total*100,1)}%<small>{metricNumber(item.value,1)} min</small></strong></button>)}
  {selected!=null&&top[selected]&&<p role="status">{top[selected].machines.length?`Recorded on ${top[selected].machines.join(', ')}.`:'Expand the reason table below for all recorded reasons.'}</p>}</div>
 </div>;
}
