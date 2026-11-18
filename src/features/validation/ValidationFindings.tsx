import {Bot} from 'lucide-react';
import {Badge} from '../../shared/ui';
import {packetAction,uiStatus,evidenceText} from '../../shared/resultEvidence';

const display=evidenceText;

export function packetRecommendation(issue:any):string {
 return `${packetAction(issue)} After review or correction, rerun the affected ByteMap checks on the same target and packet branch. A recommendation does not change the validation result.`;
}

export function ChopperRecommendation({text}:{text:string}){
 return <aside className="chopperRecommendation"><div className="chopperRecommendationHeading"><Bot size={22}/><strong>Recommended next action</strong></div><p>{text}</p></aside>;
}

export function ValidationFindings({issues=[],fallback,sourceFile,lineNumber,onSource}:{issues?:any[];fallback?:string;sourceFile?:string;lineNumber?:number;onSource?:(file:string,line:number)=>void}){
 const findings=issues.length?issues:[{validationType:fallback||'Validation needs review',sourceFile,lineNumber}];
 return <div className="validationFindings">{findings.map((issue,index)=>{
  const file=issue.sourceFile||sourceFile;
  const line=Number(issue.lineNumber??(file===sourceFile?lineNumber:0))||0;
  const status=uiStatus(issue.severity??issue.status);
  return <section className={'validationFinding '+status} key={index}>
   <header><Badge status={status}/><strong>{issue.validationType||'Validation finding'}</strong></header>
   {issue.parameter&&<p><b>PLC tag:</b> <code>{issue.parameter}</code></p>}
   {issue.condition&&<p><b>Packet path:</b> {issue.condition}</p>}
   <p><b>Reported location:</b> {file?<code>{file}{line>0?` : line ${line}`:''}</code>:'Source location was not provided in this result.'}</p>
   {file&&line>0&&onSource&&<button className="btn" onClick={()=>onSource(file,line)}>Open source at line {line}</button>}
   {(issue.expected!=null||issue.actual!=null)&&<dl className="findingComparison"><div><dt>Expected</dt><dd>{display(issue.expected)}</dd></div><div><dt>Actual</dt><dd>{display(issue.actual)}</dd></div></dl>}
   {!!issue.sourceContext?.length&&<div className="findingSource" aria-label="Source code around the finding">{issue.sourceContext.map((entry:any)=><div key={entry.lineNumber} className={entry.highlight?'findingSourceHighlight':''}><span>{entry.lineNumber}</span><code>{entry.text}</code></div>)}</div>}
   <ChopperRecommendation text={packetRecommendation(issue)}/>
  </section>;
 })}</div>;
}
