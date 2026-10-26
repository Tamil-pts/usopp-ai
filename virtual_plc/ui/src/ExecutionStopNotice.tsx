import {FileCode2, ShieldAlert} from 'lucide-react';
import {Item, Project, list} from './model';

export function ExecutionStopNotice({project,openSource,openTrace}: {
  project:Project;openSource:(path:string,line?:number)=>void;openTrace:()=>void;
}) {
  const runtime=project.runtime||{};
  if(runtime.status==='running')return null;
  const fault=list(runtime.diagnostics).filter(row=>row.code==='RUNTIME_FAULT').at(-1);
  const saved:Item|undefined=project.lastExecutionStop;
  const current=runtime.status==='faulted'&&fault?{...saved,...fault,kind:'runtime-fault',timeMs:runtime.timeMs}:undefined;
  const workerError=project.progress?.runtimeError;
  const previous=saved&&['runtime-fault','worker-error','source-stop','breakpoint'].includes(saved.kind)?saved:undefined;
  if(!current&&!workerError&&!previous)return null;
  const reason:Item=current||previous||{message:workerError};
  const failed=!!current||!!workerError||['runtime-fault','worker-error'].includes(reason.kind);
  const title=current?'PLC faulted':workerError?'PLC scan paused after an error':previous?.kind==='breakpoint'?'PLC paused at a breakpoint':previous?.kind==='source-stop'?'PLC stopped by source logic':'Last saved PLC failure';
  return <section className={`notice execution-stop-notice ${failed?'error':'warning'}`} role="alert" aria-label="PLC stop reason">
    <ShieldAlert size={18}/><div><strong>{title}</strong><p>{reason.message}</p>
      {reason.timeMs!=null&&<small>Virtual time: {reason.timeMs} ms{reason.task?' / '+reason.task:''}</small>}
      {reason.source&&<button className="link" onClick={()=>openSource(reason.source,reason.line)}><FileCode2 size={14}/>{reason.source}:{reason.line||1}</button>}
      <button onClick={openTrace}>Open execution trace</button>
      {failed&&<small>Review the error and its source inputs before resetting. Reset preserves retained settings.</small>}
    </div>
  </section>;
}
