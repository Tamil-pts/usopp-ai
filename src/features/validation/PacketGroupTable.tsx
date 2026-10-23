import {Fragment,useState} from 'react';
import {Badge} from '../../shared/ui';
import {ValidationFindings} from './ValidationFindings';

export function PacketGroupTable({groups,issues,onOffsets,onSource}:{groups:any[];issues:any[];onOffsets:(code:string)=>void;onSource:(file:string,line:number)=>void}){
 const [open,setOpen]=useState<string|null>(null);
 return <section className="card inputCard"><h2>Group code packet validation</h2><div className="tableWrap"><table className="table"><thead><tr><th>Group code</th><th>Array 3</th><th>Array 4</th><th>Configured bytes</th><th>Calculated bytes</th><th>Result</th><th>Details</th></tr></thead><tbody>{groups.map((group:any)=>{
  const variants=group.packetVariants||[];
  const code=String(group.groupCode);
  const field=group.parameters?.find((p:any)=>p.sourceFile)||variants.flatMap((v:any)=>v.parameters||[]).find((p:any)=>p.sourceFile);
  const file=field?.sourceFile||issues.find((i:any)=>String(i.groupCode)===code)?.sourceFile;
  const status=String(group.packetCalResult||group.overallStatus||'').toLowerCase();
  const value=(key:string,fallback:any)=>variants.length>1?[...new Set(variants.map((variant:any)=>variant[key]??'Not available'))].join(' / '):(fallback??'Not available');
  const paths=variants.length?variants:[{id:'group',status:group.overallStatus||status,condition:'Group summary',configuredBytes:group.configuredBytes,calculatedByOffset:group.calculatedByOffset??group.calculatedBytes,packetCalResult:group.packetCalResult,issues:issues.filter(issue=>String(issue.groupCode)===code)}];
  return <Fragment key={code}><tr><td>GC{code}</td><td>{value('configuredMsb',group.configuredMsb)}</td><td>{value('configuredLsb',group.configuredLsb)}</td><td>{value('configuredBytes',group.configuredBytes)}</td><td>{value('calculatedByOffset',group.calculatedByOffset??group.calculatedBytes)}</td><td><Badge status={status.startsWith('pass')?'pass':status.startsWith('fail')?'fail':'warn'}/><div>{group.packetCalResult}</div></td><td><div className="actions"><button className="btn" onClick={()=>onOffsets(code)}>View offsets</button>{file&&<button className="btn" onClick={()=>onSource(file,field?.lineNumber||1)}>View source</button>}<button className="btn" aria-expanded={open===code} onClick={()=>setOpen(open===code?null:code)}>{open===code?'Hide':'View'} findings / {paths.length} packet path(s)</button></div></td></tr>
   {open===code&&<tr><td colSpan={7}><div className="packetPathFindings">{paths.map((variant:any)=>{
    const state=String(variant.status||'').toLowerCase();
    return <section className={'packetVariant '+state} key={variant.id}><header><Badge status={state==='pass'?'pass':state==='fail'?'fail':'warn'}/><b>{variant.condition||'Unconditional'}</b></header><p>Configured: {variant.configuredBytes??'Not available'} bytes | Cursor: {variant.addressingMode==='fixed'?'Not used (fixed buffer offset)':variant.cursorBytes??'Not available'} | Written: {variant.writtenBytes??'Not available'} | Calculated: {variant.calculatedByOffset??'Not available'}</p><p>{variant.packetCalResult}</p>{state!=='pass'&&<ValidationFindings issues={variant.issues||[]} fallback={variant.packetCalResult} onSource={onSource}/>}</section>;
   })}</div></td></tr>}
  </Fragment>;
 })}</tbody></table></div></section>;
}
