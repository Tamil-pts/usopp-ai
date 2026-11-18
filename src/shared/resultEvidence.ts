/** Presentation of engine evidence. Never calculate a new PLC validation verdict. */
export type ReviewStatus='fail'|'not_found'|'warn'|'unknown'|'pass'|'skipped';
export function resultStatus(value:unknown):ReviewStatus{
 const s=String(value??'').trim().toUpperCase().replace(/[ _-]+/g,' ');
 if(['FAIL','FAILED','ERROR','MISMATCH','MISMATCHING','NOT MATCHING','NOT MATCHED','MISSING IN PLC'].includes(s))return 'fail';
 if(['NOT FOUND','MISSING'].includes(s))return 'not_found';
 if(['WARNING','WARN','REVIEW','NEEDS REVIEW','PARTIAL'].includes(s))return 'warn';
 if(['PASS','PASSED','MATCH','MATCHED','MATCHING'].includes(s))return 'pass';
 if(['SKIP','SKIPPED','NOT REQUIRED','NOT APPLICABLE','DISABLED'].includes(s))return 'skipped';
 return 'unknown';
}
export function uiStatus(value:unknown):'pass'|'warn'|'fail'|'not_found'{
 const s=resultStatus(value);return s==='unknown'||s==='skipped'?'warn':s;
}
export function fieldStatus(value:unknown,issues:any[]=[]){
 const states=[resultStatus(value),...issues.map(i=>resultStatus(i.severity??i.status))];
 return states.includes('fail')?'fail':states.includes('not_found')?'not_found':states.includes('warn')||states.slice(1).includes('unknown')?'warn':uiStatus(value);
}
export function evidenceText(value:any):string{
 if(value===null||value===undefined||value==='')return 'Not reported';
 if(typeof value==='object')return JSON.stringify(value,null,2);
 return String(value);
}
export function actions(value:any):string[]{
 return (Array.isArray(value)?value:[value]).filter(v=>typeof v==='string'&&v.trim()).map(v=>v.trim());
}
export function packetAction(issue:any):string{
 const supplied=actions(issue.suggestedFix??issue.suggested_fix);
 if(supplied.length)return supplied.join(' ');
 const type=String(issue.validationType??issue.validation_type??'').toLowerCase();
 if(/group.*size|packet.*(?:size|length|overflow|underflow)|payload.*length|group.*length/.test(type))return 'Compare the configured payload length with the bytes written on this reported branch. Keep the five protocol header bytes separate from the payload total.';
 if(/offset|overlap|increment|cursor|gap/.test(type))return 'Compare this branch’s source and destination addresses, field sizes and any cursor increment. Fixed-address writes may not use nw_i. Metadata offsets exclude the five-byte protocol header.';
 if(/alarm|bit pack/.test(type))return 'Check the reported alarm array bounds, packing routine and Group 30 copy source/count. Keep separate alarm buffers and packet branches separate.';
 if(/response/.test(type))return 'Check the send-length assignment and response trigger in this reported data-group branch against the expected response contract. Review close commands separately from data responses.';
 if(/datatype|data type|copy size|memcpy size/.test(type))return 'Verify the declared PLC type, resolved storage size and copied byte count against the reported source. Confirm the intended layout before changing code or metadata.';
 if(/sheet.?2|shown|dropdown|reference/.test(type))return 'Check the exact Group Code, TAG_CODE and machine/HMI scope against the workbook’s Sheet2 PLCVAL/SHOWNVAL references. Use the intended engineering labels; do not invent missing mappings.';
 return 'Review the expected and actual values against the reported source and selected target. If evidence is missing, rerun the check before choosing a correction.';
}
export type ReviewFinding={id:string;status:ReviewStatus;engineStatus:string;title:string;scope:string;file:string;line:number;expected:any;actual:any;recommendations:string[];kind:string};
export function packetFindings(result:any):ReviewFinding[]{
 return (Array.isArray(result?.issues)?result.issues:[]).map((i:any,n:number)=>({
  id:`packet-${n}`,status:resultStatus(i.severity??i.status),engineStatus:String(i.severity??i.status??'Not reported'),
  title:[i.validationType||'Validation finding',i.parameter].filter(Boolean).join(' · '),
  scope:[i.groupCode!=null?`GC ${i.groupCode}`:'',i.condition,i.target||i.hmiTarget].filter(Boolean).join(' · '),
  file:i.sourceFile||'',line:Number.isInteger(Number(i.lineNumber))&&Number(i.lineNumber)>0?Number(i.lineNumber):0,
  expected:i.expected,actual:i.actual,recommendations:[packetAction(i)],kind:i.validationType||'Packet validation',
 }));
}
export function ruleFindings(result:any):ReviewFinding[]{
 return (Array.isArray(result?.results)?result.results:[]).map((i:any,n:number)=>{
  const evidence=[...(Array.isArray(i.structuredRequirements)?i.structuredRequirements:[]),...(Array.isArray(i.evidence)?i.evidence:[])];
  const locations=evidence.filter((e:any)=>e&&typeof e==='object'&&typeof e.file==='string'&&e.file);
  const own=typeof i.sourceFile==='string'&&i.sourceFile?{file:i.sourceFile,line:i.lineNumber}:null;
  // Multiple findings must never be represented by an arbitrarily chosen file/line.
  const location=own||(locations.length===1?locations[0]:null);
  const status=resultStatus(i.status);const supplied=actions(i.recommendations??i.suggestedFix);
  return {id:`rule-${n}`,status,engineStatus:String(i.status??'Not reported'),title:i.name||i.id||'Engineering rule',
   scope:[i.standardId||i.id,i.pipelineStageName,i.pipelineBranch,i.hmiScope?.screenFolder].filter(Boolean).join(' · '),
   file:location?.file||'',line:Number.isInteger(Number(location?.line))&&Number(location?.line)>0?Number(location?.line):0,
   expected:i.expected,actual:i.actual,kind:'Engineering rule',recommendations:supplied.length?supplied:
    status==='pass'?['No correction is reported for this rule. Confirm the checked scope before approval.']:
    status==='skipped'?['This check did not establish a pass. Review the pipeline condition or optional-rule configuration.']:
    status==='not_found'?['Check the configured source path and active target, then rerun this rule. Missing source is not proof that the required behavior is absent.']:
    ['Review the detailed expected/actual evidence and configured alternatives. Confirm whether the requirement or the project source needs correction, then rerun the affected rule.']};
 });
}
export const REVIEW_PRIORITY:Record<ReviewStatus,number>={fail:0,not_found:1,warn:2,unknown:3,pass:4,skipped:5};
export function orderedFindings(rows:ReviewFinding[]){
 return [...rows].sort((a,b)=>REVIEW_PRIORITY[a.status]-REVIEW_PRIORITY[b.status]||a.scope.localeCompare(b.scope,undefined,{numeric:true})||a.file.localeCompare(b.file)||a.line-b.line);
}
