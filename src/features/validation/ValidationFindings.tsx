import {Bot} from 'lucide-react';
import {Badge} from '../../shared/ui';

const display=(value:any)=>value===undefined||value===null||value===''?'Not available':String(value);

export function packetRecommendation(issue:any):string {
 const type=String(issue.validationType||'').toLowerCase();
 const action=issue.suggestedFix||'Review the expected and actual values at the reported source location.';
 const explanation=type.includes('size')||type.includes('overflow')||type.includes('length')
  ? 'The group length must equal the transmitted payload bytes on this branch. Calculate header MSB * 256 + LSB, sum every field copy, and keep the five protocol header bytes out of the payload total. A short length truncates values; a long length sends unintended bytes.'
  : type.includes('offset')||type.includes('increment')||type.includes('cursor')
  ? 'Start the payload at buffer index 5. Each next field must start after the previous copy; advance nw_i by the copied byte count. Metadata offsets start at 0, so subtract 5 from buffer positions. An incorrect increment shifts every later field.'
  : type.includes('alarm')
  ? 'FOR endpoints are inclusive: count = upper - lower + 1 for step 1, and packed bytes = ceil(count / 8). Match the alarm array bounds, BIT_SET destination, first packed byte and Group 30 memcpy source/count for each alarm buffer separately.'
  : type.includes('response')
  ? 'Every data group branch must set the send length to payload bytes + 5 and enable nw_snd_response. GC 11 is the close command and does not require a data response.'
  : 'Check the declared variable datatype, copied byte count, packet path and metadata mapping together. Follow the reported branch independently of other IF/ELSIF alternatives.';
 return `${action} ${explanation} After changing the PLC source, rerun ByteMap and Group Code checks and review all later fields in the same path. Update metadata only when it reflects the intended PLC layout.`;
}

export function ChopperRecommendation({text}:{text:string}){
 return <aside className="chopperRecommendation"><div className="chopperRecommendationHeading"><Bot size={22}/><strong>Chopper recommends</strong></div><p>{text}</p></aside>;
}

export function ValidationFindings({issues=[],fallback,sourceFile,lineNumber,onSource}:{issues?:any[];fallback?:string;sourceFile?:string;lineNumber?:number;onSource?:(file:string,line:number)=>void}){
 const findings=issues.length?issues:[{validationType:fallback||'Validation needs review',sourceFile,lineNumber}];
 return <div className="validationFindings">{findings.map((issue,index)=>{
  const file=issue.sourceFile||sourceFile;
  const line=Number(issue.lineNumber||lineNumber)||0;
  const status=String(issue.severity||'').toLowerCase()==='fail'?'fail':'warn';
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
