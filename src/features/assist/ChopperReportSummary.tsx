import {BarChart3,Download,FileSpreadsheet} from 'lucide-react';
import type {PerformanceDashboard,ReportQueryPlan} from './reportDashboard';

export type ReportAnalysis={
 summary?:string;dashboard?:PerformanceDashboard;
 fields?:string[];groupBy?:string;plan?:ReportQueryPlan;
 cards?:{label:string;value:string;unit:string;detail:string}[];
 sources?:{file:string;reportId?:string;sheet:string;headerRow:number;metric:string;column:string;columns?:string[];rows:number[];records:number;summaryRowsExcluded:number;complete:boolean}[];
 scope?:{from?:string;to?:string;shift?:string;machines?:string[]};kind?:string|null;kinds?:string[];complete?:boolean;focusMachine?:string|null;
};

export function ChopperReportSummary({data,compact=false}:{data:ReportAnalysis;compact?:boolean}){
 if(compact)return <div className="chopperReportCompact"><BarChart3 size={13}/>{data.complete===false?'Partial report coverage':'Calculated from your reports'}</div>;
 return <section className="chopperReportAnalysis" aria-label="Calculated report results">
  <header><BarChart3 size={16}/><strong>Report analysis</strong><span>{data.complete===false?'Partial workbook coverage':'Calculated from uploaded records'}</span></header>
  {!!data.cards?.length&&<div className="chopperReportCards">{data.cards.map((card,index)=><div className="chopperReportCard" key={index}>
   <span>{card.label}</span><strong>{card.value} <small>{card.unit}</small></strong><small>{card.detail}</small>
  </div>)}</div>}
  {!!data.sources?.length&&<details className="chopperReportSources"><summary><FileSpreadsheet size={14}/>Worksheet evidence · {data.sources.length} source table(s)</summary>
   {data.sources.map((source,index)=><div key={index}>
    <strong>{source.file} → {source.sheet}</strong>
    <p>Header row {source.headerRow} · {source.records.toLocaleString()} selected detail records · {source.summaryRowsExcluded} summary rows excluded.</p>
    <p>{source.metric}: {source.rows.flatMap(row=>(source.columns||[source.column]).map(column=>`${column}${row}`)).join(', ')}</p>
    {source.reportId&&<a className="btn" href={`/api/assist/report/${encodeURIComponent(source.reportId)}/source`} download><Download size={13}/>Original workbook</a>}
   </div>)}
  </details>}
 </section>;
}
