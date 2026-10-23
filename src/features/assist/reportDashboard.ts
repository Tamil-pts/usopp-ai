import {useEffect,useRef,useState} from 'react';
import type {ChatAttachment} from './chatFiles';

export type ReportScope={from?:string;to?:string;shift?:string;machines?:string[]};
export type KpiTarget={value:number;operator:'lte'|'gte'};
export type ReportQueryPlan={version:number;question:string;catalog:string;queries:unknown[];unavailable:string[]};
export type ReportControls={scope:ReportScope;comparison:boolean|{from:string;to:string};targets:Record<string,KpiTarget>;question?:string;fields?:string[];groupBy?:string;kinds?:string[];plan?:ReportQueryPlan};
export type QuestionTable={title:string;headers:string[];rows:(string|number)[][];totalRows?:number};
export type DashboardQuery={plan?:ReportQueryPlan;methods?:string[];planner?:string;question:string;title:string;fields:string[];groupBy?:string;section:string;intent:string;tables:QuestionTable[];notes:string[];message:string;machineCount?:number;recordCount?:number};
export type DashboardMetric={key:string;label:string;kind:string;unit:string;value:number|null;previous:number|null;direction:string;available:boolean;status:string;basis:string;records:number;target?:KpiTarget;comparisonNote:string;change?:{absolute:number;percent:number|null;unit:string;favorable:boolean|null}|null;daysPassing?:number|null;daysMeasured?:number;flaggedMachines?:number};
export type DashboardMachine={machine:string;values:Record<string,number|null>;records:Record<string,number>;violations:string[];runtimeSeconds?:number|null;speedRPM?:number|null;leadingReason?:string;lots?:string[]};
export type DashboardSource={kind:string;file:string;sheet:string;reportId?:string;headerRow:number;columns:{key:string;label:string;column:string}[];rows:number[];records:number;days:number;previousRecords:number;previousDays:number;summaryRowsExcluded:number;complete:boolean;digest:string};
export type PerformanceDashboard={schema:number;kinds:string[];query?:DashboardQuery;title:string;scope:ReportScope;period:{from:string|null;to:string|null;days:number};comparison:{from:string;to:string;days:number}|null;targets:Record<string,KpiTarget>;metrics:DashboardMetric[];daily:({date:string}&Record<string,number|string>)[];machines:DashboardMachine[];topMachines:string[];bottomMachines:string[];reasons:{reason:string;events:number;seconds:number|null;minutes:number|null;share:number|null;machines:string[]}[];compliance:DashboardMetric[];findings:{title:string;detail:string;severity:string;metric?:string;machine?:string}[];actions:{priority:string;action:string;evidence:string;owner:string;due:string;status:string;metric:string}[];notes:string[];sources:DashboardSource[];complete:boolean;machineCount:number;recordCount:number;available:{kinds:string[];from:string|null;to:string|null;machines:string[];shifts:string[]}};

const localToday=()=>{const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;};
const savedTargets=(key:string):Record<string,KpiTarget>=>{try{const value=JSON.parse(localStorage.getItem(key)||'{}');if(!value||typeof value!=='object'||Array.isArray(value))return {};return Object.fromEntries(Object.entries(value).filter(([,item])=>!!item&&typeof item==='object'&&Number.isFinite((item as KpiTarget).value)&&(item as KpiTarget).value>=0&&['lte','gte'].includes((item as KpiTarget).operator))) as Record<string,KpiTarget>}catch{return {}}};
export function useReportDashboard(attachments:ChatAttachment[],userKey:string){
 const key=`chopper-kpi-targets:${userKey}`;
 const [controls,setControls]=useState<ReportControls>(()=>({scope:{},comparison:true,targets:savedTargets(key)}));
 const [data,setData]=useState<PerformanceDashboard|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const reportIds=attachments.filter(a=>a.kind==='report'&&a.reportId).map(a=>a.reportId!).join(',');
 const [revision,refresh]=useState(0);const active=useRef(0),receivedControls=useRef<ReportControls|null>(null);
 const payload=()=>({reportIds:reportIds.split(',').filter(Boolean),...controls,today:localToday()});
 useEffect(()=>{try{localStorage.setItem(key,JSON.stringify(controls.targets))}catch{/* Browser storage is optional. */}},[key,controls.targets]);
 useEffect(()=>{
  const turn=++active.current;const abort=new AbortController();
  if(!reportIds){setData(null);setLoading(false);setError('');setControls(current=>Object.keys(current.scope).length?{...current,scope:{}}:current);return;}
  if(receivedControls.current===controls){receivedControls.current=null;setLoading(false);return;}
  setLoading(true);setError('');
  fetch('/api/assist/reports/dashboard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload()),signal:abort.signal}).then(async response=>{const result=await response.json();if(!response.ok)throw new Error(result.detail||'Report analysis is unavailable.');return result}).then(result=>{if(turn===active.current)setData(result)}).catch(reason=>{if(!abort.signal.aborted&&turn===active.current)setError(reason instanceof Error?reason.message:'Report analysis is unavailable.')}).finally(()=>{if(turn===active.current)setLoading(false)});
  return()=>abort.abort();
 },[reportIds,controls,revision]);
 const receive=(result?:PerformanceDashboard)=>{if(!result)return;active.current++;setData(result);setError('');setLoading(false);setControls(current=>{const question=result.query?.question||'',fields=result.query?.fields,groupBy=result.query?.groupBy,kinds=result.kinds,plan=result.query?.plan;if(JSON.stringify(current.scope)===JSON.stringify(result.scope)&&current.question===question&&JSON.stringify(current.fields)===JSON.stringify(fields)&&current.groupBy===groupBy&&JSON.stringify(current.kinds)===JSON.stringify(kinds)&&JSON.stringify(current.plan)===JSON.stringify(plan))return current;const next={...current,scope:result.scope,question,fields,groupBy,kinds,plan};receivedControls.current=next;return next;});};
 const reset=()=>{active.current++;setData(null);setControls(current=>({...current,scope:{},question:'',fields:undefined,groupBy:undefined,kinds:undefined,plan:undefined}));};
 const download=async(format:'pdf'|'csv'|'json')=>{
  const response=await fetch(`/api/assist/reports/export/${format}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});
  if(!response.ok){const result=await response.json().catch(()=>({}));throw new Error(result.detail||'Report export failed.');}
  const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=`Chopper_${controls.question?'Question':'Performance'}_Report.${format}`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 return {data,controls,setControls,loading,error,receive,reset,download,refresh:()=>refresh(value=>value+1)};
}

export const metricNumber=(value:number|null|undefined,digits=2)=>value==null?'—':value.toLocaleString(undefined,{maximumFractionDigits:digits,minimumFractionDigits:digits});
export const hours=(seconds:number|null|undefined)=>seconds==null?'—':`${Math.floor(seconds/3600)}:${String(Math.floor(seconds/60)%60).padStart(2,'0')}:${String(Math.round(seconds)%60).padStart(2,'0')}`;
