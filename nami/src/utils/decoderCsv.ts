import type {GroupResponseData,ParsedParamValue} from '../types';

export const DECODER_CSV_HEADERS=['Tag','Parameter','Offset','Type','Raw decimal bytes','Decoded value','Finding'] as const;
export type DecoderCsvRow={tag:unknown;parameter:string;offset:string;type:string;rawDecimal:string;decoded:string;finding:string};

export function decimalBytesFromHex(hex:string):string {
 const parts=hex.trim().split(/\s+/).filter(Boolean);
 return parts.length&&parts.every(part=>/^[0-9a-f]{2}$/i.test(part))?parts.map(part=>parseInt(part,16)).join(' '):'';
}

export function decoderValueRow(value:ParsedParamValue,rawDecimal=decimalBytesFromHex(value.rawHex||''),decoded=value.formattedValue):DecoderCsvRow {
 return {tag:value.tagCode,parameter:value.parameter,offset:`+${value.offset} B`,type:value.dataType,
  rawDecimal:rawDecimal||'Unavailable',decoded,finding:value.qualityIssue||(value.isInRange?'Decoded':'Data issue')};
}

export function decoderFrameRow(group:number,bytes:number[]|undefined,findings:string[]):DecoderCsvRow {
 return {tag:'',parameter:`GC ${group} frame`,offset:'',type:'',rawDecimal:bytes?.join(' ')||'Unavailable',decoded:'',
  finding:findings.filter(Boolean).join('; ')||'No parameter values decoded. Attach the matching metadata to map the frame.'};
}

export function responseDecoderRows(response:GroupResponseData):DecoderCsvRow[] {
 const findings=[response.error||'',...(!response.lengthMatch?[`Payload length ${response.dataLength}; metadata expects ${response.expectedLength??'unavailable'}.`]:[])].filter(Boolean);
 const rows=response.parsedValues.map(value=>decoderValueRow(value));
 return rows.length?rows.map(row=>({...row,finding:[row.finding,...findings].join('; ')})):[decoderFrameRow(response.groupCode,response.rawBytes,findings)];
}

export function decoderCsv(rows:DecoderCsvRow[]):string {
 const cell=(input:unknown)=>{
  let text=String(input??'');
  // Workbook labels are untrusted text. Preserve signed numbers while preventing formulas.
  if(/^\s*[=+@-]/.test(text)&&!/^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?\s*$/i.test(text))text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
 };
 return '\ufeff'+[DECODER_CSV_HEADERS,...rows.map(row=>[row.tag,row.parameter,row.offset,row.type,row.rawDecimal,row.decoded,row.finding])]
  .map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n';
}

export function downloadDecoderCsv(rows:DecoderCsvRow[],filename:string){
 const url=URL.createObjectURL(new Blob([decoderCsv(rows)],{type:'text/csv;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download=filename.replace(/[^a-z0-9._-]+/gi,'_');
 document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
