import {Component,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import * as echarts from 'echarts/core';
import {BarChart,LineChart,PieChart,ScatterChart,GaugeChart,HeatmapChart,TreemapChart,FunnelChart,RadarChart} from 'echarts/charts';
import {GridComponent,LegendComponent,TooltipComponent,VisualMapComponent,RadarComponent,AriaComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
import {AlertCircle,ExternalLink,FileText,LoaderCircle,RefreshCw} from 'lucide-react';
import {hub} from '../projectApi';
import {formatValue,queryFor,type Widget,type GlobalFilters,type Row} from './model';

const numeric=(v:any):v is number=>typeof v==='number'&&Number.isFinite(v);
const CHART_TYPES=new Set(['bar','stacked_bar','line','area','pie','donut','scatter','combo','heatmap','histogram','treemap','funnel','radar','gauge']);
type WidgetProps={widget:Widget;filters:GlobalFilters;registry:Row;dark:boolean;refresh:number;scope?:{project_ids:string[]}};
class WidgetBoundary extends Component<{children:ReactNode;resetKey:string},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 componentDidUpdate(previous:{resetKey:string}){if(this.state.failed&&previous.resetKey!==this.props.resetKey)this.setState({failed:false});}
 render(){return this.state.failed?<div className="db-state db-error" role="alert"><AlertCircle size={20}/><span>This widget could not be displayed. Your dashboard and project records are saved.</span><button className="btn" onClick={()=>this.setState({failed:false})}><RefreshCw size={14}/>Reload widget</button></div>:this.props.children;}
}
export function WidgetView(props:WidgetProps){return <WidgetBoundary resetKey={JSON.stringify([props.widget,props.filters,props.refresh,props.scope])}><WidgetContent {...props}/></WidgetBoundary>;}
echarts.use([BarChart,LineChart,PieChart,ScatterChart,GaugeChart,HeatmapChart,TreemapChart,FunnelChart,RadarChart,GridComponent,LegendComponent,TooltipComponent,VisualMapComponent,RadarComponent,AriaComponent,CanvasRenderer]);
function Chart({option}:{option:Row}){
 const ref=useRef<HTMLDivElement>(null),[error,setError]=useState('');
 useEffect(()=>{if(!ref.current)return;setError('');const chart=echarts.init(ref.current,undefined,{renderer:'canvas'});try{chart.setOption(option,true);}catch{setError('This chart cannot display the selected settings. Review its fields, dimensions and numeric ranges.');}const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);return()=>{observer.disconnect();chart.dispose();};},[option]);
 return <>{error&&<p className="db-state db-error" role="alert">{error}</p>}<div ref={ref} className="db-chart" role="img" style={error?{display:'none'}:undefined} aria-label="Chart of the selected WorkHub records"/></>;
}
function chartOption(w:Widget,data:Row,dark:boolean):Row{
 const a={...w.appearance,horizontal:w.appearance.horizontal&&w.type!=='combo'},rows:Row[]=(Array.isArray(data.rows)?data.rows:[]).map((r:Row)=>({...r,dimensions:Array.isArray(r.dimensions)?r.dimensions:[],values:Array.isArray(r.values)?r.values:[]})),labels=rows.map(r=>r.dimensions.join(' / ')||'All records'),seriesNames=w.query.metrics.map(m=>m.aggregation+' '+m.field.replaceAll('_',' '));
 const ink=dark?'#dce8ef':'#294251',muted=dark?'#38515f':'#e1e9ed',dim0=Array.from(new Set(rows.map(r=>r.dimensions?.[0]||'All records'))),dim1=Array.from(new Set(rows.map(r=>r.dimensions?.[1]||'All records')));
 const option:Row={color:a.colors,backgroundColor:'transparent',textStyle:{color:ink,fontFamily:'inherit'},animationDuration:250,
  tooltip:{trigger:'item',renderMode:'richText',confine:true},legend:{show:a.legend,textStyle:{color:ink},type:'scroll',bottom:0},
  grid:{top:28,right:24,bottom:a.legend?65:35,left:52,containLabel:true},aria:{enabled:true}};
 const axis=(type:string,name:string)=>({type,name,nameLocation:'middle',nameGap:28,show:a.axes,axisLabel:{color:ink,hideOverlap:true,...(type==='value'?{formatter:(v:number)=>formatValue(v,w)}:{})},axisLine:{lineStyle:{color:muted}},splitLine:{lineStyle:{color:muted}}});
 if(w.type==='gauge')return {...option,series:[{type:'gauge',min:a.min,max:Math.max(a.min+1,a.max),progress:{show:true},axisLine:{lineStyle:{width:12}},axisLabel:{color:ink},detail:{color:ink,formatter:(v:number)=>formatValue(v,w),fontSize:25},title:{color:ink},data:[{value:data.totals[0],name:seriesNames[0]}]}]};
 if(['pie','donut','funnel','treemap'].includes(w.type)){
  const values=rows.filter(r=>numeric(r.values[0])).map(r=>({name:r.dimensions?.join(' / ')||'All records',value:r.values[0]}));
  if(w.type==='treemap'&&w.query.dimensions.length===2){const children=dim0.map(name=>({name,children:rows.filter(r=>r.dimensions[0]===name&&numeric(r.values[0])).map(r=>({name:r.dimensions[1],value:r.values[0]}))}));return {...option,series:[{type:'treemap',data:children,roam:false,leafDepth:2,breadcrumb:{show:true}}]};}
  return {...option,series:[{type:w.type==='donut'?'pie':w.type,stillShowZeroSum:false,radius:w.type==='donut'?['45%','70%']:'65%',center:['50%','45%'],data:values,label:{color:ink},...(w.type==='funnel'?{sort:'none',left:'12%',width:'76%',top:10,bottom:50}:{})}]};
 }
 if(w.type==='radar'){
  const max=Math.max(1,...rows.flatMap(r=>r.values.filter(numeric)));return {...option,radar:{indicator:labels.map(name=>({name,max})),axisName:{color:ink},radius:'60%'},series:[{type:'radar',data:seriesNames.map((name,i)=>({name,value:rows.map(r=>r.values[i])}))}]};
 }
 if(w.type==='heatmap')return {...option,xAxis:{...axis('category',a.x_label),data:dim0},yAxis:{...axis('category',a.y_label),data:dim1},visualMap:{min:Math.min(0,...rows.map(r=>r.values[0]).filter(numeric)),max:Math.max(1,...rows.map(r=>r.values[0]).filter(numeric)),calculable:true,orient:'horizontal',left:'center',bottom:0,textStyle:{color:ink},inRange:{color:[dark?'#163945':'#e0f2ef',a.colors[0]]}},legend:{show:false},series:[{type:'heatmap',data:rows.filter(r=>numeric(r.values[0])).map(r=>[dim0.indexOf(r.dimensions[0]||'All records'),dim1.indexOf(r.dimensions[1]||'All records'),r.values[0]])}]};
 if(w.type==='scatter')return {...option,xAxis:axis('value',a.x_label||w.query.metrics[0]?.field),yAxis:axis('value',a.y_label||w.query.metrics[1]?.field),series:[{type:'scatter',symbolSize:10,data:rows.filter(r=>numeric(r[w.query.metrics[0]?.field])&&numeric(r[w.query.metrics[1]?.field])).map(r=>[r[w.query.metrics[0].field],r[w.query.metrics[1].field]])}]};
 if(w.type==='histogram'){
  const bins:Row[]=data.histogram||[];
  return {...option,legend:{show:false},xAxis:{...axis('category',a.x_label||w.query.metrics[0]?.field),data:bins.map(b=>b.from.toFixed(Math.min(4,Math.max(1,a.decimals)))+'–'+b.to.toFixed(Math.min(4,Math.max(1,a.decimals))))},yAxis:axis('value',a.y_label||'Records'),series:[{type:'bar',barGap:0,data:bins.map(b=>b.count)}]};
 }
 const grouped=w.query.dimensions.length>1;
 const series=grouped?dim1.flatMap(group=>seriesNames.map((name,i)=>({name:group+' / '+name,data:dim0.map(d=>rows.find(r=>r.dimensions[0]===d&&r.dimensions[1]===group)?.values[i]??null)}))):seriesNames.map((name,i)=>({name,data:rows.map(r=>r.values[i])}));
 const categories=grouped?dim0:labels;
 option.xAxis={...axis(a.horizontal?'value':'category',a.x_label),...(a.horizontal?{}:{data:categories})};option.yAxis={...axis(a.horizontal?'category':'value',a.y_label),...(a.horizontal?{data:categories}:{})};
 if(w.type==='combo'&&a.secondary_axis)option.yAxis=[option.yAxis,{...axis('value',seriesNames[1]||''),position:'right'}];
 option.tooltip.trigger='axis';option.series=series.map((s,i)=>({...s,type:w.type==='combo'?(a.series_types?.[i%seriesNames.length]||(i%seriesNames.length>0?'line':'bar')):['line','area'].includes(w.type)?'line':'bar',...(w.type==='combo'&&a.secondary_axis?{yAxisIndex:i%seriesNames.length>0?1:0}:{}),tooltip:{valueFormatter:(v:any)=>v==null?'Not recorded':formatValue(v,w)},smooth:a.smooth,connectNulls:false,...(w.type==='area'?{areaStyle:{opacity:.2}}:{}),...(w.type==='stacked_bar'?{stack:'total'}:{})}));
 return option;
}
function Timeline({rows,w}:{rows:Row[];w:Widget}){
 const dated=rows.filter(r=>r.start&&r.end&&Date.parse(r.start)<=Date.parse(r.end));
 if(!dated.length)return <p className="db-state">No saved start and due dates. Choose Projects, Tasks or Milestones with scheduled dates.</p>;
 const start=Math.min(...dated.map(r=>Date.parse(r.start))),end=Math.max(...dated.map(r=>Date.parse(r.end)))+86400000,span=end-start;
 return <div className={'db-timeline '+(w.type==='roadmap'?'roadmap':'')}><div className="db-timeline-range"><span>{new Date(start).toLocaleDateString()}</span><span>{new Date(end-86400000).toLocaleDateString()}</span></div>{dated.map(r=><div key={r.id} className="db-timeline-row"><a href={r._url||undefined} title={r.title}>{r.title}</a><div><span title={`${r.title}: ${r.start} — ${r.end}`} style={{left:100*(Date.parse(r.start)-start)/span+'%',width:Math.max(1,100*(Date.parse(r.end)+86400000-Date.parse(r.start))/span)+'%',background:w.appearance.colors[0]}}>{r.progress!=null?r.progress+'%':''}</span></div></div>)}</div>;
}
function Calendar({rows}:{rows:Row[]}){
 const [month,setMonth]=useState(new Date().toISOString().slice(0,7));const [year,m]=month.split('-').map(Number),start=new Date(year,m-1,1),days=new Date(year,m,0).getDate(),offset=(start.getDay()+6)%7;
 return <div className="db-calendar"><label>Month <input type="month" value={month} onChange={e=>e.target.value&&setMonth(e.target.value)}/></label><div className="db-calendar-grid">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=><b key={d}>{d}</b>)}{Array.from({length:offset},(_,i)=><div key={'gap'+i}/>)}{Array.from({length:days},(_,i)=>{const day=month+'-'+String(i+1).padStart(2,'0');return <div key={day}><small>{i+1}</small>{rows.filter(r=>String(r.end||r.date||'').slice(0,10)===day).map(r=><a key={r.id} href={r._url||undefined} title={r.title}>{r.title}</a>)}</div>;})}</div></div>;
}
function Pivot({data,w}:{data:Row;w:Widget}){
 if(w.query.dimensions.length<2)return <p className="db-state">Select a row dimension and a column dimension in widget settings.</p>;
 const rows:Row[]=data.rows,cols=[...new Set(rows.map(r=>r.dimensions[1]))],groups=[...new Set(rows.map(r=>r.dimensions[0]))],max=Math.max(1,...rows.map(r=>r.values[0]).filter(numeric));
 return <div className="db-table-wrap"><table><thead><tr><th>{w.query.dimensions[0].field}</th>{cols.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{groups.map(g=><tr key={g}><th>{g}</th>{cols.map(c=>{const v=rows.find(r=>r.dimensions[0]===g&&r.dimensions[1]===c)?.values[0];return <td key={c} style={w.type==='matrix'&&numeric(v)?{background:w.appearance.colors[0]+Math.max(0,Math.min(255,Math.round(30+100*v/max))).toString(16).padStart(2,'0')}:undefined}>{v==null?'—':formatValue(v,w)}</td>;})}</tr>)}</tbody></table></div>;
}
function WidgetContent({widget:w,filters,registry,dark,refresh,scope}:WidgetProps){
 const [data,setData]=useState<Row|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0);
 const request=queryFor(w,filters);
 const q=JSON.stringify(scope?{...request,global:{...request.global,project_ids:scope.project_ids}}:request);
 useEffect(()=>{if(w.type==='text')return;const abort=new AbortController();setLoading(true);setError('');setData(null);void hub('/dashboards/query',JSON.parse(q),'POST',abort.signal).then(result=>{if(!abort.signal.aborted)setData(result);}).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});return()=>abort.abort();},[q,w.type,refresh,retry]);
 // Tables, calendars, KPIs and timelines return raw records, not chart series.
 // Computing an aggregate chart option for those rows crashed saved dashboards.
 const option=useMemo(()=>data&&CHART_TYPES.has(w.type)?chartOption(w,data,dark):{},[w,data,dark]);
 if(w.type==='text')return <div className="db-text">{w.text||<span className="db-muted">Add text in widget settings.</span>}</div>;
 if(loading)return <div className="db-state" role="status"><LoaderCircle size={20} className="spin"/>Loading {registry.sources[w.query.source].title.toLowerCase()}…</div>;
 if(error)return <div className="db-state db-error" role="alert"><AlertCircle size={20}/><span>{error}</span><button className="btn" onClick={()=>setRetry(v=>v+1)}><RefreshCw size={14}/>Retry</button></div>;
 if(!data)return null;
 if(!data.total_records&&!['kpi','scorecard','progress'].includes(w.type))return <div className="db-state">No authorized records match these filters. Choose another source or adjust the filters.</div>;
 let content;
 if(['kpi','scorecard','progress'].includes(w.type))content=<div className={'db-values '+(w.type==='scorecard'?'multiple':'')}>{data.metrics.map((m:Row,i:number)=><div key={i}><strong style={{color:w.appearance.colors[i%w.appearance.colors.length]}}>{formatValue(data.totals[i],w)}</strong><small>{m.aggregation} · {registry.sources[w.query.source].fields[m.field]?.label}</small>{w.type==='progress'&&numeric(data.totals[i])&&<progress max={Math.max(1,w.appearance.max-w.appearance.min)} value={Math.max(0,data.totals[i]-w.appearance.min)}/>}</div>)}</div>;
 else if(w.type==='table'){const fields=registry.sources[w.query.source].fields,cols=w.columns.length?w.columns:['title','project','engineer','date'].filter(k=>fields[k]);content=<div className="db-table-wrap"><table><thead><tr>{cols.map(k=><th key={k}>{fields[k].label}</th>)}</tr></thead><tbody>{data.rows.map((r:Row)=><tr key={r.id}>{cols.map(k=><td key={k}>{k==='title'&&r._url?<a href={r._url}>{r[k]}<ExternalLink size={11}/></a>:r[k]==null?'—':fields[k].type==='number'?formatValue(r[k],w):String(r[k])}</td>)}</tr>)}</tbody></table></div>;}
 else if(['pivot','matrix'].includes(w.type))content=<Pivot data={data} w={w}/>;
 else if(['gantt','roadmap'].includes(w.type))content=<Timeline rows={data.rows} w={w}/>;
 else if(w.type==='calendar')content=<Calendar rows={data.rows}/>;
 else if(w.type==='documents')content=<ul className="db-documents">{data.rows.map((r:Row)=><li key={r.id}><FileText size={18}/><div><a href={r._url||undefined}>{r.title}</a><small>{r.project} · {r.kind||r.category||''}</small></div></li>)}</ul>;
 else if((w.type==='scatter'&&!data.rows.some((r:Row)=>numeric(r[w.query.metrics[0]?.field])&&numeric(r[w.query.metrics[1]?.field])))||(w.type==='histogram'&&!data.histogram?.length))content=<div className="db-state">Select {w.type==='scatter'?'two numeric metrics':'a numeric metric'} with recorded values for this visualization.</div>;
 else if(data.totals.every((v:any)=>v==null))content=<div className="db-state">Not enough information for the selected metrics.</div>;
 else if(w.type==='radar'&&data.rows.some((r:Row)=>r.values.some((v:any)=>!numeric(v))))content=<div className="db-state">A radar chart needs recorded values for every selected category. Use a table or bar chart to show categories with missing information.</div>;
 else if(['pie','donut','funnel','treemap'].includes(w.type)&&(!data.rows.some((r:Row)=>numeric(r.values[0])&&r.values[0]>0)||data.rows.some((r:Row)=>numeric(r.values[0])&&r.values[0]<0)))content=<div className="db-state">This visualization needs nonnegative values with a positive total. Choose another metric or a bar chart.</div>;
 else content=<Chart option={option}/>;
 return <>{content}<footer className="db-widget-foot"><span>{data.mode==='records'&&data.truncated?`${data.rows.length} displayed / `:''}{data.total_records.toLocaleString()} source records</span>{data.notes.length>0&&<details><summary>{data.truncated?'Partial display':'About this data'}</summary>{data.notes.map((n:string,i:number)=><p key={i}>{n}</p>)}</details>}</footer></>;
}
