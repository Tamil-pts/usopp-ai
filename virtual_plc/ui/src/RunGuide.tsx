import {useEffect, useState} from 'react';
import {BookOpen, ChevronLeft, ChevronRight, FileCode2, Play, RefreshCw, Search, ShieldAlert} from 'lucide-react';
import {Item, Project, list, request} from './model';

const reasons:Record<string,{title:string;next:string}> = {
  UNSUPPORTED_CALL: {title:'Library or function implementation missing', next:'Supply the matching source/library implementation, or use Automation Studio simulation for vendor behavior.'},
  LADDER_UNSUPPORTED_NETWORK: {title:'Ladder network not executable yet', next:'Function blocks and analog networks need interpreter support before this project can run.'},
  LADDER_ELEMENT_TYPE: {title:'Ladder element not supported', next:'The viewer can display this element; its execution semantics still need implementation.'},
  UNSUPPORTED_SYNTAX: {title:'Source construct not supported', next:'Review the original source line. The virtual compiler cannot execute this construct yet.'},
  UNRESOLVED_SYMBOL: {title:'Variable or symbol unresolved', next:'Check the variable scope, declarations, selected configuration and required libraries.'},
  MEMORY_UNRESOLVED_TYPE: {title:'Data type unresolved', next:'Include its type definition and required library. Unknown types cannot become working PLC memory.'},
  LADDER_SYMBOL: {title:'Ladder signal reference unresolved', next:'Review the declared scope and selected array/member type. Contacts and coils require a BOOL value.'},
  BLOCK_INTERFACE: {title:'Function-block interface differs', next:'Review the declared inputs and outputs against the supported block implementation.'},
  'variable-conflict': {title:'Duplicate exact declarations', next:'Review both source locations and their scope. B&R names with different capitalization are separate variables.'},
};

export function RunGuide({project,busy,recheck,example,programTest,openSource,tasks,close}: {
  project:Project|null;busy:boolean;recheck:()=>Promise<void>;example:()=>Promise<void>;programTest:(id:string)=>Promise<void>;
  openSource:(path:string,line?:number)=>void;tasks:()=>void;close:()=>void;
}) {
  const [report,setReport]=useState<Item|null>(null),[error,setError]=useState('');
  const [code,setCode]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(0);
  const [testProgram,setTestProgram]=useState('');
  useEffect(()=>{setTestProgram(list(project?.model?.programs).find(p=>/loginout.*cyclic/i.test(p.id))?.id||'');},[project?.id]);
  const [loading,setLoading]=useState(false);
  const ready=project?.status==='ready',allowed=project?.runtime?.compatibility?.runAllowed===true;
  useEffect(()=>setPage(0),[code,query,project?.id]);
  useEffect(()=>{
    setReport(null);
    if(!project||!ready)return;
    const controller=new AbortController();setLoading(true);
    const timer=setTimeout(()=>{void request(`/projects/${project.id}/compatibility?code=${encodeURIComponent(code)}&query=${encodeURIComponent(query)}&offset=${page*75}&limit=75`,{signal:controller.signal})
      .then(result=>{setReport(result);setError('');})
      .catch(e=>{if(e.name!=='AbortError')setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});},150);
    return()=>{clearTimeout(timer);controller.abort();};
  },[project?.id,project?.modelRevision,ready,code,query,page]);
  const groups=Object.entries(report?.byCode||{}).sort((a,b)=>Number(b[1])-Number(a[1]));
  return <div className="run-guide">
    <div className="dialog-eyebrow"><BookOpen size={17}/> RUN YOUR VIRTUAL PLC</div>
    <h2>{allowed?'Ready for a virtual scan':project?'Why is Run disabled?':'Start your first simulation'}</h2>
    <p>{allowed?'The active dependencies are supported. Set virtual input values, execute one scan and inspect the results before continuous running.':project&&!ready?'Wait for project analysis to finish before checking execution readiness.':project?'Your project has been loaded for inspection. The current interpreter cannot execute all of its active dependencies, so Run and Single scan stay disabled.':'Import a PLC project or open the separate training example below.'}</p>
    {ready&&!allowed&&<div className="notice warning"><ShieldAlert size={18}/><div><strong>This machine project cannot run completely in this interpreter yet.</strong><p>These are conversion-support findings, not proof that the real PLC program is faulty. A complete project run currently needs the remaining library/Ladder implementations, or B&amp;R Automation Studio simulation.</p></div></div>}
    {ready&&<section className="notice"><strong>Test one source program in a separate workspace</strong><p>Other machine tasks will be excluded and listed. The selected program and its called dependencies must still be supported.</p><select aria-label="Program to test" value={testProgram} onChange={e=>setTestProgram(e.target.value)}><option value="">Choose a cyclic program</option>{list(project?.model?.programs).filter(p=>p.kind==='program'&&p.entry==='cyclic').map(p=><option key={p.id} value={p.id}>{p.source} ({p.compatibility?.status||'review required'})</option>)}</select><button disabled={busy||!testProgram} onClick={()=>void programTest(testProgram)}>Create program test</button></section>}
    <div className="run-guide-actions"><button className="primary" disabled={busy} onClick={()=>void example()}><Play size={15}/> Open runnable example</button>{ready&&<><button disabled={busy||project?.runtime?.status==='running'} onClick={()=>void recheck()}><RefreshCw size={15}/> Recheck project</button><button onClick={()=>{tasks();close();}}>Task configuration</button></>}</div>
    <small className="muted">The example creates a separate training workspace. Recheck applies current runtime support to the saved model and resets its virtual values and scan history; it does not change PLC source.</small>
    <ol className="guide-steps run-steps">
      <li><strong>Open the starter example, or import your project.</strong> Wait until analysis finishes.</li>
      <li><strong>Check execution readiness.</strong> Run becomes available only when all active dependencies are supported.</li>
      <li><strong>Set inputs in Variable monitor.</strong> In the example set <code>StartCommand</code> to <code>TRUE</code>; leave <code>StopCommand</code> FALSE and <code>DoorClosed</code> TRUE.</li>
      <li><strong>Click Single scan.</strong> In the example <code>MotorRunning</code> becomes TRUE and <code>ScanCounter</code> increases.</li>
      <li><strong>Connect virtual devices if needed.</strong> Open Components, add a device, bind each signal to an exact PLC declaration, then save and enable it. Device feedback advances only with supported scans.</li>
      <li><strong>Click Run, then Pause.</strong> Observe virtual time, task executions and output values. Set <code>StopCommand</code> TRUE to stop the example motor command.</li>
    </ol>
    {ready&&!allowed&&<section className="run-findings" aria-label="Execution blockers">
      <h3>Review execution blockers</h3>
      <p className="muted">{report?.blockers??'…'} retained active findings. Open a source reference to inspect the original line.</p>
      {report?.diagnosticsTruncated&&<div className="notice warning">Showing retained findings only. The analysis produced {report.diagnosticCount} total findings, including warnings; {report.retainedFindings} were retained.</div>}
      <div className="run-finding-filters"><select aria-label="Blocker category" value={code} onChange={e=>setCode(e.target.value)}><option value="">All categories</option>{groups.map(([name,count])=><option key={name} value={name}>{reasons[name]?.title||name} ({String(count)})</option>)}</select><label className="search"><Search size={14}/><input placeholder="Find source or message" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
      {error&&<div className="notice error">{error}</div>}
      {loading?<p className="inline-empty">Loading findings…</p>:list(report?.findings).map((row,i)=><article className="run-finding" key={`${row.code}:${row.source}:${row.line}:${i}`}><strong>{reasons[row.code]?.title||row.code}</strong><p>{row.message}</p><small>{reasons[row.code]?.next||'Review the original source and required runtime support.'}</small>{row.source&&<button className="link" onClick={()=>{openSource(row.source,row.line);close();}}><FileCode2 size={14}/>{row.source}:{row.line||1}</button>}</article>)}
      {report&&<div className="source-footer"><span>{report.total} findings in this filter</span><span className="spacer"/><button disabled={!page} onClick={()=>setPage(v=>v-1)}><ChevronLeft size={14}/></button><span>{page+1} / {Math.max(1,Math.ceil(report.total/75))}</span><button disabled={(page+1)*75>=report.total} onClick={()=>setPage(v=>v+1)}><ChevronRight size={14}/></button></div>}
    </section>}
  </div>;
}
