import {useDatasetBI} from './datasetBI';
import {useEffect,useState} from 'react';
import type {ChatAttachment} from './chatFiles';

export type DatasetTab='dashboard'|'prompts'|'overview'|'outliers'|'comparisons'|'recommendations';
export type ChartType='bar'|'line'|'donut'|'pivot';
export const DATASET_TABS:[DatasetTab,string][]=[['dashboard','Auto dashboard'],['prompts','Dataset Prompts'],['overview','Overview'],['outliers','Outliers & Risk'],['comparisons','Comparisons'],['recommendations','Recommendations']];
export const DATASET_PROMPTS:Record<DatasetTab,string[]>={
 dashboard:['Summarize this worksheet.'],
 prompts:['Summarize this worksheet and list its columns.','Show missing cells and duplicate rows.','Compare the groups using the selected measure.'],
 overview:['Give an overview of this worksheet.','Show the grouped values for the current chart.'],
 outliers:['Find statistical outliers in the selected measure.','Show missing values and spreadsheet errors.'],
 comparisons:['Compare the groups using the selected measure.','Show the largest and smallest group values.'],
 recommendations:['Recommend data-quality checks for this worksheet.','Which source cells should I review first?']
};
export type DatasetProfile={index:number;letter:string;name:string;numeric:number;missing:number;errors:number;distinct:number;sum:number|null;mean:number|null;min:number|null;max:number|null};
export type DatasetResult={source:{file:string;id:string;sheet:string;header_row:number;sha256:string};columns:DatasetProfile[];rows:number;empty_rows:number;blank_cells:number;error_cells:number;duplicates:number;value:number|null;metric:number|null;group:number|null;pivot:number|null;operation:string;order:string;categories:{id:string;label:string;type:string;value:number|null;rows:number;source_rows:number[]}[];group_count:number;outliers:{row:number;cell:string;value:number}[];outlier_count:number;outlier_bounds:{q1:number;q3:number;lower:number;upper:number}|null;pivot_table:{columns:{id:string;label:string}[];rows:{label:string;values:(number|null)[]}[]}|null;issues:{kind:string;column:number;count:number;cells:string[]}[];recommendations:string[];notes:string[];preview:{row:number;cells:string[]}[];preview_total:number};
export type DatasetConfig={id:string;sheet:string;header_row:number;group:number|null;metric:number|null;pivot:number|null;operation:string;order:string};
async function query<T>(url:string,init:RequestInit):Promise<T>{const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...init});const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Could not read this worksheet.');return value;}
export function useDatasetWorkspace(attachments:ChatAttachment[]){
 const files=attachments.filter(item=>item.dataset),fileKeys=files.map(item=>item.dataset!.id).join(',');
 const [config,setConfig]=useState<DatasetConfig>({id:'',sheet:'',header_row:1,group:null,metric:null,pivot:null,operation:'count',order:'source'});
 const [data,setData]=useState<DatasetResult|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [tab,setTab]=useState<DatasetTab>('dashboard'),[chart,setChart]=useState<ChartType>('bar'),[selection,setSelection]=useState<string|null>(null);
 const [selectedRows,setSelectedRows]=useState<{rows:{row:number;cells:string[]}[];total:number}|null>(null),[selectionLoading,setSelectionLoading]=useState(false),[selectionError,setSelectionError]=useState('');
 const source=files.find(item=>item.dataset?.id===config.id)?.dataset;
 const bi=useDatasetBI(config,!!source);
 useEffect(()=>{if(!files.some(item=>item.dataset?.id===config.id)){const first=files[0]?.dataset,sheet=first?.sheets[0]?.name||'';setConfig({id:first?.id||'',sheet,header_row:first?.header_rows?.[sheet]??(first?.sheets[0]?.rows?1:0),group:null,metric:null,pivot:null,operation:'count',order:'source'});}},[fileKeys,config.id]);
 useEffect(()=>{
  setSelection(null);setData(null);setError('');if(!source||!config.sheet){setLoading(false);return;}
  const controller=new AbortController();setLoading(true);
  void query<DatasetResult>('/api/assist/datasets/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config),signal:controller.signal}).then(setData).catch(problem=>{if(problem.name!=='AbortError')setError(problem.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();
 },[JSON.stringify(config),revision,!!source]);
 useEffect(()=>{
  setSelectedRows(null);setSelectionError('');if(!selection){setSelectionLoading(false);return;}
  const controller=new AbortController();setSelectionLoading(true);
  void query<{rows:{row:number;cells:string[]}[];total:number}>('/api/assist/datasets/rows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...config,category_id:selection}),signal:controller.signal}).then(setSelectedRows).catch(problem=>{if(problem.name!=='AbortError')setSelectionError(problem.message);}).finally(()=>{if(!controller.signal.aborted)setSelectionLoading(false);});return()=>controller.abort();
 },[selection,JSON.stringify(config)]);
 function chooseFile(id:string){const next=files.find(item=>item.dataset?.id===id)?.dataset,sheet=next?.sheets[0]?.name||'';if(next)setConfig({id,sheet,header_row:next.header_rows?.[sheet]??(next.sheets[0]?.rows?1:0),group:null,metric:null,pivot:null,operation:'count',order:'source'});}
 function chooseSheet(sheet:string){setConfig(current=>({...current,sheet,header_row:source?.header_rows?.[sheet]??(source?.sheets.find(s=>s.name===sheet)?.rows?1:0),group:null,metric:null,pivot:null,operation:'count'}));}
 async function download(format:'csv'|'xlsx'|'json'){
  const response=await fetch('/api/assist/datasets/export/'+format,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
  if(!response.ok){const value=await response.json();throw Error(value.detail||'Worksheet export failed.');}
  const url=URL.createObjectURL(await response.blob()),anchor=document.createElement('a');anchor.href=url;anchor.download=`${(config.sheet||'Worksheet').replace(/[<>:"/\\|?*]/g,'_')}.${format}`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async function answer(question:string){
  bi.result.current=null;
  if(Object.values(DATASET_PROMPTS).flat().includes(question)&&question!==DATASET_PROMPTS.dashboard[0])return await legacyAnswer(question);
  setTab('dashboard');return await bi.answer(question);
 }
 async function legacyAnswer(question:string){
  const result=await query<DatasetResult>('/api/assist/datasets/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});setData(result);
  const lower=question.toLowerCase(),section:DatasetTab=/outlier|missing|error|risk|duplicate/.test(lower)?'outliers':/recommend|review first|check/.test(lower)?'recommendations':/compare|largest|smallest|group/.test(lower)?'comparisons':'overview';setTab(section);
  const exact=Object.values(DATASET_PROMPTS).flat().includes(question);
  const provenance=`${result.source.file} / ${result.source.sheet} · header row ${result.source.header_row} · SHA256 ${result.source.sha256.slice(0,12)}`;
  if(!exact&&!/\b(overview|summari[sz]e|columns?|missing|duplicate|outlier|compare|groups?|largest|smallest|recommend|data quality)\b/i.test(question))return `I can calculate the selected worksheet's profile, grouped values, IQR outliers and data-quality checks. Choose a Dataset Prompt or adjust the group, measure and aggregation controls.\n\nSource: ${provenance}`;
  const profile=`${result.rows.toLocaleString()} nonempty rows, ${result.columns.length} columns; ${result.blank_cells} missing cells, ${result.error_cells} spreadsheet errors and ${result.duplicates} repeated complete rows.`;
  const measure=result.metric==null?'row count':`${result.operation} of ${result.columns[result.metric].name}`;
  if(section==='outliers')return `**Worksheet checks**\n\n${profile}\n\n${result.outlier_bounds?`${result.outlier_count} IQR candidates in ${result.columns[result.metric!].name}; bounds ${result.outlier_bounds.lower} to ${result.outlier_bounds.upper}. These are statistical review candidates.`:'Select a numeric measure with at least four finite values to calculate IQR outliers.'}\n\n${result.issues.slice(0,6).map(issue=>`- ${result.columns[issue.column].name}: ${issue.count} ${issue.kind} cells; ${issue.cells.join(', ')}.`).join('\n')}\n\nSource: ${provenance}`;
  if(section==='recommendations')return `**Suggested review**\n\n${result.recommendations.map(value=>'- '+value).join('\n')}\n\nSource: ${provenance}`;
  if(section==='comparisons')return `**Group comparison · ${measure}**\n\n${result.categories.slice(0,12).map(category=>`- ${category.label}: ${category.value??'No numeric value'} (${category.rows} rows).`).join('\n')}\n\n${result.group_count>12?`Showing 12 of ${result.group_count} groups. The chart and worksheet download provide more detail.\n\n`:''}Source: ${provenance}`;
  return `**Worksheet overview**\n\n${profile}\n\nSelected calculation: ${measure} = ${result.value??'No numeric value'}.\n\nColumns: ${result.columns.map(column=>`${column.letter}: ${column.name}`).join('; ')}.\n\nSource: ${provenance}`;
 }
 const currentData=data&&data.source.id===config.id&&data.source.sheet===config.sheet&&data.source.header_row===config.header_row&&data.metric===config.metric&&data.group===config.group&&data.pivot===config.pivot&&data.operation===config.operation&&data.order===config.order?data:null;
 return {bi,files,source,config,setConfig,chooseFile,chooseSheet,data:currentData,loading,error,tab,setTab,chart,setChart,selection,setSelection,selectedRows,selectionLoading,selectionError,download,answer,refresh:()=>setRevision(value=>value+1)};
}
export type DatasetManager=ReturnType<typeof useDatasetWorkspace>;
