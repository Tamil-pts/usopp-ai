import {FileCode2} from 'lucide-react';
import {Item,Project,list,sourcePath,memoryValue,valueText} from './model';

/** Show the real declaration identity; labels never create another PLC value. */
export function VariableIdentity({project,variable,openSource,select}: {
  project:Project;variable:Item;openSource:(path:string,line?:number)=>void;select:(row:Item)=>void;
}) {
  const name=String(variable.name||'').toLowerCase();
  const matches=list(project.model?.variables).filter(row=>String(row.name||'').toLowerCase()===name);
  return <section className="variable-identity">
    <h4>Shared PLC memory identity</h4>
    <p className="muted">ST, Ladder, HMI and components share a value when they resolve to this declaration ID. {project.model?.symbolCaseSensitive?'B&R names are case sensitive: different capitalization can identify separate variables.':'This workspace uses case insensitive IEC names.'}</p>
    <code>{variable.id||`${variable.scope}::${variable.name}`}</code>
    {matches.length>1?<><p className="muted">{matches.length} declarations have similar spelling. Check capitalization and scope; a local declaration takes precedence inside its program.</p>{matches.map(row=><div className="identity-row" key={row.id}><button className={row.id===variable.id?'active':''} onClick={()=>select(row)}><strong>{row.name} / {row.scope||'Global'}</strong><span>{row.type} · {valueText(memoryValue(project,row.id))}</span></button>{sourcePath(row)&&<button className="icon-button" title={`Open ${sourcePath(row)}:${row.line||1}`} onClick={()=>openSource(sourcePath(row),row.line)}><FileCode2 size={14}/></button>}</div>)}</>:<p className="muted">No other declaration with this spelling was found in the loaded model.</p>}
    {variable.ambiguous&&<div className="notice warning">This declaration has conflicting source definitions. Review its source before binding a device or running logic.</div>}
  </section>;
}
