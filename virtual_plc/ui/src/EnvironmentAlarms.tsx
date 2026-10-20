import React, {useEffect, useState} from 'react';
import {Item, Project, list, request, valueText} from './model';

export function EnvironmentAlarms({project,signal,openSource,view='alarms'}:{project:Project;view?:'alarms'|'timers';signal:(id:string,value:number)=>void;openSource?:(path:string,line?:number)=>void}) {
  const [query,setQuery]=useState(''),[page,setPage]=useState(0),[data,setData]=useState<Item>({}),[error,setError]=useState('');
  useEffect(()=>setPage(0),[view]);
  useEffect(()=>{
    const controller=new AbortController();let busy=false;setData({});
    const load=async()=>{if(busy||document.hidden)return;busy=true;try{
      const result=await request(`/projects/${project.id}/environment?view=${view}&query=${encodeURIComponent(query)}&offset=${page*25}`,{signal:controller.signal});
      if(!controller.signal.aborted){setData(result);setError('');}
    }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}finally{busy=false;}};
    void load();const timer=setInterval(()=>void load(),2500);return()=>{clearInterval(timer);controller.abort();};
  },[project.id,query,page,view]);
  return <div className="environment-alarms"><header><h3>{view==='timers'?'PLC timers - live values':'Alarm conditions and field feedback'}</h3><label className="search"><input placeholder={view==='timers'?'Find a timer':'Find an alarm or PLC tag'} value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}}/></label><span>{Number(data.total)||0} {view==='timers'?'timers':'alarm definitions'}</span></header>
    {view==='alarms'&&<p>The simulation jig supplies configured field states and automatic feedback. Original PLC logic evaluates each alarm and interlock; use Change contact for a manual sensor override.</p>}
    {error&&<div className="notice error">{error}</div>}
    {view==='timers'&&<div className="environment-timer-grid">{list(data.timers).map(timer=><article className="environment-timer" key={timer.variable}><header><b>{timer.type}</b><span className="spacer"/><span className={`timer-done ${timer.value.Q?'on':''}`}>{timer.value.Q?'DONE / Q = 1':'Q = 0'}</span></header><code>{timer.variable}</code><div className="timer-values"><span>PRESET (PT)<b>{valueText(timer.value.PT)} ms</b></span><span>ELAPSED (ET)<b>{valueText(timer.value.ET)} ms</b></span></div><progress aria-label={`${timer.name} elapsed time`} max={Math.max(1,Number(timer.value.PT)||0)} value={Math.min(Number(timer.value.ET)||0,Math.max(1,Number(timer.value.PT)||0))}/><footer><span>IN: {valueText(timer.value.IN)}</span><button onClick={()=>openSource?.(timer.source,timer.line)}>{timer.source}:{timer.line}</button></footer></article>)}</div>}
    {list(data.alarms).map(row=><article key={row.id} className="environment-alarm"><header><b className={row.value?'failText':''}>{row.value===null?'Unresolved':row.value?'ACTIVE':'Inactive'}</b><strong>{row.text||row.id}</strong><small>{row.group}</small></header><code>{row.variable||row.binding||'Missing alarm binding'}</code>
      <div className="environment-inputs">{list(row.inputs).map(input=><div key={input.variable}><code>{input.variable}</code><b>{valueText(input.value)}</b>{input.component&&typeof input.value==='boolean'&&<button onClick={()=>signal(input.component,input.value?0:1)}>Change contact</button>}</div>)}</div>
      {!list(row.inputs).length&&<small>No scalar field input was resolved through this alarm's compiled writers. Inspect its source or configure the associated device.</small>}
      <footer>{list(row.logicSources).map((source,index)=><button key={index} onClick={()=>openSource?.(source.source,source.line)}>{source.source}:{source.line}</button>)}{row.dependencyLimitReached&&<span>Dependency preview is bounded.</span>}</footer>
    </article>)}
    <footer><button disabled={!page} onClick={()=>setPage(v=>v-1)}>Previous</button><span>{page+1} / {Math.max(1,Math.ceil(Number(data.total||0)/25))}</span><button disabled={(page+1)*25>=Number(data.total||0)} onClick={()=>setPage(v=>v+1)}>Next</button></footer>
    {list(data.unresolved).length>0&&<details><summary>{list(data.unresolved).length} unresolved hardware mappings</summary>{list(data.unresolved).map((row,index)=><p key={index}><code>{row.variable}</code> — {row.reason} <button onClick={()=>openSource?.(row.source,row.line)}>Mapping source</button></p>)}</details>}
  </div>;
}
