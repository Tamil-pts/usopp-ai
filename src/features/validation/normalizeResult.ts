import type {AnyResult} from '../../shared/types';
import {fieldStatus,resultStatus,uiStatus} from '../../shared/resultEvidence';
export function normalizeResult(r:any){
 const s=r?.summary||{}; const counts={pass:s.passed??r?.passed??0,warn:s.warnings??r?.warnings??0,fail:s.failed??r?.failed??0};
 const issues=Array.isArray(r?.issues)?r.issues:[]; let offsetSequence=0;
 const offsetRows=(r?.groups||[]).flatMap((g:any)=>{
  const variants=Array.isArray(g.packetVariants)?g.packetVariants:[];
  const entries=variants.length>1
   ? variants.flatMap((variant:any)=>(variant.parameters||[]).map((parameter:any)=>({p:parameter,variant})))
   : (g.parameters||[]).map((parameter:any)=>({p:parameter,variant:variants[0]}));
  return entries.map(({p,variant}:any)=>{
   const variantParameter=(variant?.parameters||[]).find((entry:any)=>entry.parameter===p.parameter&&entry.sourceFile===p.sourceFile&&entry.lineNumber===p.lineNumber);
   const localIssues=p.issues||variantParameter?.issues||[];
   const parameterIssues=localIssues.length?localIssues:issues.filter((x:any)=>x.parameter===p.parameter&&String(x.groupCode)===String(p.groupCode??g.groupCode)&&(!x.sourceFile||x.sourceFile===p.sourceFile)&&(!x.lineNumber||Number(x.lineNumber)===Number(p.lineNumber)||Number(x.lineNumber)===Number(p.incrementLineNumber))&&(!x.condition||x.condition===(p.conditionContext||variant?.condition||'')));
   const issue=parameterIssues.find((x:any)=>String(x.severity||'').toUpperCase()==='FAIL')||parameterIssues[0];
   const rawMethod=p.transferMethod||'memcpy';
   const method=rawMethod==='direct-byte'?'Direct byte assignment':(rawMethod==='cursor-gap'||rawMethod==='unwritten-gap')?'Unwritten cursor gap':rawMethod==='conditional'?'Conditional alternatives':'memcpy';
   const condition=p.conditionContext||variant?.condition||'';
   return {
    id:++offsetSequence,tag:p.logicSequence??p.sequence??'',gc:`GC${p.groupCode??g.groupCode}`,parameter:p.parameter||'',description:p.description||'',condition,
    type:p.dataType||'',declaredType:p.declaredDataType||p.dataType||'',declaredSize:p.declaredSize??'',size:p.memcpySize??p.size??'',method,evidence:p.writeEvidence||[],
    payloadOffset:p.tcpOffset??p.offsetBuffer??'',tcpOffset:p.tcpOffset??p.offsetBuffer??'',increment:p.incrementValue??'',actual:p.runningOffset??'',expected:p.expectedOffset??'',after:p.offsetAfterCopy??'',
    src:p.sourceExpression||'',dest:p.destinationExpression||'',status:fieldStatus(p.status,parameterIssues),
    sourceFile:p.sourceFile||'',lineNumber:p.lineNumber??0,issues:parameterIssues,
    code:p.sourceFile?`${p.sourceFile}:${p.lineNumber??''}`:'',root:p.remarks||parameterIssues.map((x:any)=>x.validationType).join('; '),fix:issue?.suggestedFix||''
   };
  });
 });
 const metadataSourceRows=(r?.metadataSourceRows||[]).map((m:any,i:number)=>({
  seq:m.sequence??m.metadataSequence??m.sNo??m.s_no??'',
  screenName:m.screenName??m.screen_name??m['Screen name']??m['SCREEN NAME']??'',
  machineVariants:m.machineVariants??m.machine_variants??m['Machine Variants']??m['MACHINE VARIANTS']??'',
  tagCode:m.tagCode??m.metadataTagCode??m.tag_code??'',
  parameter:m.parameter??m.metadataParameterName??m.metadataParameter??m['Parameters']??m['PARAMETERS']??'',
  groupCode:m.groupCode??m.metadataGroupCode??m['GROUP_CODE']??m['Group Code']??'',
  dataType:m.dataType??m.datatype??m.metadataType??m['Data Type']??'',
  offset:m.offset??m.metadataOffset??m['OFFSET']??m['Offset']??'',
  min:m.min??m.minValue??m.metadataMin??m['MIN']??'',
  max:m.max??m.maxValue??m.metadataMax??m['MAX']??'',
  shown:m.shownValueDifferent??m.metadataShownValueDifferent??m.isShownValueDifferent??m['IS_SHOWN_VALUE_DIFFERENT']??'',
  units:m.units??m.unit??m.metadataUnits??m['UNITS']??'',
  offsetFactor:m.offsetFactor??m.offset_factor??m['OFFSET_FACTOR']??'',
  scaleFactor:m.scaleFactor??m.scale_factor??m['SCALE_FACTOR']??'',
  isVisible:m.isVisible??m.is_visible??m['IS_VISIBLE']??'',
  isWritable:m.isWritable??m.is_writable??m['IS_WRITABLE']??'',
  sheet:m.sheetName??m.metadataSheet??'',
  row:m.rowNumber??m.metadataRow??''
 }));
 const hasValue=(value:any)=>value!==undefined&&value!==null&&value!=='';
 const firstValue=(...values:any[])=>values.find(hasValue)??'';
 const sourceLocationKey=(sheet:any,row:any)=>hasValue(sheet)&&hasValue(row)?`${String(sheet)}::${String(row)}`:'';
 const sourceIdentityKey=(seq:any,group:any)=>hasValue(seq)&&hasValue(group)?`${String(seq)}::${String(group)}`:'';
 const metadataSourceByLocation:Map<string,any>=new Map(metadataSourceRows.map((m:any):[string,any]=>[sourceLocationKey(m.sheet,m.row),m]).filter(([key]:[string,any])=>!!key));
 const metadataSourceByIdentity:Map<string,any>=new Map(metadataSourceRows.map((m:any):[string,any]=>[sourceIdentityKey(m.seq,m.groupCode),m]).filter(([key]:[string,any])=>!!key));
 const metadataSourceBySeq:Map<string,any>=new Map(metadataSourceRows.map((m:any)=>[String(m.seq),m]));
 // Build a safe HMI lookup from the validation result. The previous build
 // referenced hmiLookup without declaring it, which caused a runtime white
 // screen as soon as the validation dashboard was rendered.
 const hmiLookup:Map<string,string[]>=new Map();
 (r?.dropdownValidation?.controls||[]).forEach((c:any)=>{
   const gc2=String(c.groupCode??'');
   const norm2=(v:any)=>String(v||'').toLowerCase().trim().replace(/\s+/g,' ');
   const pairs=(c.hmiPairs||[]).map((p:any)=>`${p[0]} = ${p[1]}`);
   if(c.logicComment) hmiLookup.set(`${gc2}::${norm2(c.logicComment)}`,pairs);
   if(c.tagCode!=null) hmiLookup.set(`${gc2}::tag::${String(c.tagCode)}`,pairs);
 });
 const metadataRowsRaw=(r?.metadataComparison?.results||[]).map((x:any,i:number)=>{
  // The uploaded workbook is the source of truth for the Metadata side.
  // Prefer the raw workbook row by Metadata S No.; only fall back to comparison fields when needed.
  const src=metadataSourceByLocation.get(sourceLocationKey(x.metadataSheet,x.metadataRow))
   ||metadataSourceByIdentity.get(sourceIdentityKey(x.metadataSequence,x.metadataGroupCode??x.groupCode))
   ||metadataSourceBySeq.get(String(x.metadataSequence??''))||{};
  return {
  id:i+1,
  sl:x.recordType==='METADATA_ONLY'?'':x.logicSequence??'',
  metaSeq:firstValue(x.metadataSequence,src.seq),
  metadataScreenName:firstValue(x.metadataScreenName,src.screenName),
  metadataMachineVariants:firstValue(x.metadataMachineVariants,src.machineVariants),
  plcTagCode:x.logicSequence??'',
  metadataTagCode:firstValue(x.metadataTagCode,src.tagCode),
  logic:x.plcTag||'',
  plcTag:x.plcTag||'',
  logicComment:x.logicParameterName||x.parameterName||'',
  gc:String(x.groupCode??''),
  lt:x.plcType||'',
  plcDeclaredType:x.plcDeclaredType||x.plcType||'',
  lo:String(x.plcOffset??''),
  size:x.plcSize??x.memcpySize??'',
  dropdown:!!x.dropdown,
  hmiPairs:(()=>{  const gc2=String(x.groupCode??'');  const norm2=(s:string)=>String(s||'').toLowerCase().trim().replace(/\s+/g,' ');  return hmiLookup.get(`${gc2}::${norm2(x.logicComment||'')}`)     ||(x.plcTagCode?hmiLookup.get(`${gc2}::tag::${x.plcTagCode}`):undefined)    ||[];  })(),
  mappingStatus:String(x.matchMethod||'').toLowerCase().includes('configured mapping')?'configured':(String(x.comparisonStatus||'').toUpperCase()==='MISSING_IN_PLC'?'unmatched_meta':(x.metadataParameterName?'matched':'unmatched')),
  valueSource:x.valueSource||'Logic data',
  inputType:x.inputType||'Used only in logic, not in screen',
  hmiMin:x.hmiMin??'',
  hmiMax:x.hmiMax??'',
  metadataMin:firstValue(x.metadataMin,src.min),
  metadataMax:firstValue(x.metadataMax,src.max),
  metadataShown:firstValue(x.metadataShownValueDifferent,src.shown),
  metadataUnits:firstValue(x.metadataUnits,src.units),
  metadataOffsetFactor:firstValue(x.metadataOffsetFactor,src.offsetFactor),
  metadataScaleFactor:firstValue(x.metadataScaleFactor,src.scaleFactor),
  metadataIsVisible:firstValue(x.metadataIsVisible,src.isVisible),
  metadataIsWritable:firstValue(x.metadataIsWritable,src.isWritable),
  // IMPORTANT: these values are copied from the uploaded workbook source row.
  // Never derive, rename, or replace them from the PLC side.
  meta:firstValue(x.metadataParameterName,src.parameter),
  mg:firstValue(x.metadataGroupCode,src.groupCode),
   mt:firstValue(x.metadataType,src.dataType),
   datatypeCompatibility:x.datatypeCompatibility||'',
  mo:firstValue(x.metadataOffset,src.offset),
  status:(String(x.status||'').toUpperCase()==='PASS'||String(x.status||'').toUpperCase()==='MATCH')?'pass':(String(x.status||'').toUpperCase()==='FAIL'||String(x.status||'').toUpperCase().includes('MISMATCH')||String(x.status||'').toUpperCase().includes('MISSING_IN_PLC'))?'fail':'warn',
  root:x.details||'',
  fix:'',
  logicSourceFile:x.logicSourceFile||'',
  logicLineNumber:x.logicLineNumber??'',
  matchMethod:x.matchMethod||'',
  metadataDescription:x.metadataDescription||'',
  metadataSize:x.metadataSize??'',
  metadataSequence:firstValue(x.metadataSequence,src.seq),
  metadataSheet:firstValue(x.metadataSheet,src.sheet),
  metadataRow:firstValue(x.metadataRow,src.row),
  recordType:x.recordType||'PLC_WITH_METADATA',
  metadataSourceCopied:true
  }
 });
 // Older engine results did not always emit a METADATA_ONLY comparison row.
 // Append any raw workbook row that is still absent so the uploaded workbook
 // side is complete and remains independent from PLC matching suggestions.
 const representedSourceLocations=new Set(metadataRowsRaw.map((row:any)=>sourceLocationKey(row.metadataSheet,row.metadataRow)).filter(Boolean));
 metadataSourceRows.forEach((src:any)=>{
  const location=sourceLocationKey(src.sheet,src.row);
  if(location&&representedSourceLocations.has(location))return;
  metadataRowsRaw.push({
   id:metadataRowsRaw.length+1,sl:'',metaSeq:src.seq,metadataScreenName:src.screenName,
   metadataMachineVariants:src.machineVariants,plcTagCode:'',metadataTagCode:src.tagCode,
   logic:'',plcTag:'',logicComment:'',gc:'',lt:'',lo:'',size:'',dropdown:false,hmiPairs:[],
   mappingStatus:'unmatched_meta',valueSource:'Not available',inputType:'Not available',hmiMin:'',hmiMax:'',
   metadataMin:src.min,metadataMax:src.max,metadataShown:src.shown,metadataUnits:src.units,
   metadataOffsetFactor:src.offsetFactor,metadataScaleFactor:src.scaleFactor,
   metadataIsVisible:src.isVisible,metadataIsWritable:src.isWritable,
   meta:src.parameter,mg:src.groupCode,mt:src.dataType,mo:src.offset,status:'fail',
   root:'Listed in the uploaded metadata workbook but no PLC comparison record was returned.',fix:'',
   logicSourceFile:'',logicLineNumber:'',matchMethod:'Metadata Parameter not found in PLC',
   metadataDescription:'',metadataSize:'',metadataSequence:src.seq,metadataSheet:src.sheet,
   metadataRow:src.row,recordType:'METADATA_ONLY',metadataSourceCopied:true
  });
  if(location)representedSourceLocations.add(location);
 });
 // Keep every source row. Within each Group Code, PLC rows remain in PLC extraction order;
 // metadata-only rows follow in uploaded-workbook order. Never reorder either source to force a match.
 let plcSerial=0;
 const metadataRows=metadataRowsRaw.map((row:any)=>row.recordType==='METADATA_ONLY'?row:{...row,sl:++plcSerial});
 metadataRows.sort((a:any,b:any)=>{
  const ag=(a.gc!==''?Number(a.gc):Number(a.mg??'')); const bg=(b.gc!==''?Number(b.gc):Number(b.mg??''));
  if(ag!==bg)return ag-bg;
  const aMeta=a.recordType==='METADATA_ONLY', bMeta=b.recordType==='METADATA_ONLY';
  if(aMeta!==bMeta)return aMeta?1:-1;
  if(!aMeta && !bMeta)return Number(a.sl||0)-Number(b.sl||0);
  return Number(a.metaSeq||0)-Number(b.metaSeq||0);
 });
 const dropdownRows=(r?.dropdownValidation?.controls||[]).map((x:any,i:number)=>({id:i+1,gc:String(x.groupCode??''),comment:x.logicComment||'',parameter:x.logicComment||'No PLC comment found',tag:String(x.tagCode??x.indexDatapoint??''),metaSeq:x.metadataSequence??'',hmi:(x.hmiPairs||[]).map((p:any)=>`${p[0]} = ${p[1]}`),metaParam:x.metadataParameterName||'',meta:(x.metadataPairs||[]).map((p:any)=>`${p[0]} = ${p[1]}`),status:uiStatus(x.status),reason:x.reason||'',root:'',fix:'',matchMethod:x.metadataMatchMethod||'',source:x.logicSourceFile||'',line:x.logicLineNumber??''}));
 const groupSummary=(r?.groups||[]).map((g:any)=>{
  const ps=g.parameters||[];
  const states=ps.map((p:any)=>resultStatus(p.status));
  const pass=states.filter((state:string)=>state==='pass').length;
  const fail=states.filter((state:string)=>state==='fail').length;
  const warn=states.filter((state:string)=>!['pass','fail'].includes(state)).length;
  const groupIssues=issues.filter((issue:any)=>String(issue.groupCode)===String(g.groupCode));
  const explicit=g.overallStatus??g.packetCalResult;
  const status=fieldStatus(explicit,[...groupIssues,...ps.map((p:any)=>({status:p.status})),
   ...(!explicit&&(!ps.length||warn)?[{status:'WARNING'}]:[])]);
  return {gc:String(g.groupCode??''),description:g.description||g.name||'',total:ps.length,pass,warn,fail,status,
   configuredMsb:g.configuredMsb,configuredLsb:g.configuredLsb,configuredBytes:g.configuredBytes,
   calculatedBytes:g.calculatedBytes,calculatedByOffset:g.calculatedByOffset,packetCalResult:g.packetCalResult};
 });
 return {counts,score:s.complianceScore??r?.complianceScore??0,offsetRows,metadataRows,dropdownRows,groupSummary};
}
