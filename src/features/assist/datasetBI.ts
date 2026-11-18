import {useEffect,useRef,useState} from 'react';
export type BISpec={chart:'bar'|'line'|'scatter'|'histogram'|'donut'|'table';x?:number|null;y?:number|null;series?:number|null;aggregate?:string;time_bucket?:string;filters?:{column:number;value:string}[]};
export type BIChart={spec:BISpec;title:string;caption:string;points:{x:string|number;y:number|null;row?:number;rows?:number;series?:string}[];truncated:boolean;correlation:number|null;sql:string;parameters?:string[]};
export type BIColumn={index:number;letter:string;name:string;kind:'number'|'date'|'category';numeric:number;missing:number;errors:number;distinct:number;count:number;sum:number|null;mean:number|null;min:number|null;max:number|null;outliers:number};
export type BIDashboard={source:{id:string;file:string;sheet:string;header_row:number;sha256:string};rows:number;duplicates:number;columns:BIColumn[];charts:BIChart[];insights:{id:string;text:string}[];notes:string[];cached:boolean;seconds:number};
export async function biRequest(path:string,body?:unknown,signal?:AbortSignal){const response=await fetch('/api/assist/datasets/bi'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal});const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Worksheet analysis failed.');return value;}
export function useDatasetBI(config:{id:string;sheet:string;header_row:number},active:boolean){
 const result=useRef<{dashboard:BIDashboard|null;chart:BIChart|null}|null>(null);
 const scope=JSON.stringify([config.id,config.sheet,config.header_row]),latest=useRef(scope);latest.current=scope;
 const [data,setData]=useState<BIDashboard|null>(null),[chart,setChart]=useState<BIChart|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0),[summary,setSummary]=useState<{insights:{id:string;text:string}[];modelUsed:boolean;notice:string}|null>(null);
 useEffect(()=>{setData(null);setChart(null);setSummary(null);setError('');if(!active||!config.id||!config.sheet){setBusy(false);return;}
 const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;setBusy(true);
 const poll=async(id:string)=>{try{const value=await biRequest('/jobs/'+id,undefined,controller.signal);if(controller.signal.aborted)return;if(value.status==='ready'){setData(value.result);setBusy(false);void biRequest('/summary',{id:config.id,sheet:config.sheet,header_row:config.header_row},controller.signal).then(v=>{if(!controller.signal.aborted)setSummary(v)}).catch(()=>{});}else if(value.status==='failed'){setError(value.error);setBusy(false);}else timer=setTimeout(()=>void poll(id),500);}catch(e:any){if(e.name!=='AbortError'){setError(e.message);setBusy(false);}}};
 void biRequest('/start',{id:config.id,sheet:config.sheet,header_row:config.header_row},controller.signal).then(value=>poll(value.jobId)).catch(e=>{if(e.name!=='AbortError'){setError(e.message);setBusy(false);}});
 return()=>{controller.abort();if(timer)clearTimeout(timer)};
 },[config.id,config.sheet,config.header_row,active,revision]);
 async function answer(question:string,spec?:BISpec){const requested=scope;const value=await biRequest('/question',{id:config.id,sheet:config.sheet,header_row:config.header_row,question,...(spec?{spec}:{})});if(latest.current!==requested)throw Error('Worksheet selection changed. Ask again for the current sheet.');result.current={dashboard:value.dashboard||data,chart:value.chart||null};if(value.dashboard)setData(value.dashboard);setChart(value.chart||null);return value.answer as string;}
 return {data,chart,busy,error,summary,result,answer,refresh:()=>setRevision(v=>v+1)};
}
