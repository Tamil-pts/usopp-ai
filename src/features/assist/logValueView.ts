import type {MetadataItem,ParsedParamValue} from '../../../nami/src/types';
import {getExpectedGroupPayloadLength} from '../../../nami/src/utils/metadataParser';
import type {LogCapture} from './logDecoder';

export interface LogValueRow {value:ParsedParamValue;rawDecimal:string;decoded:string}

export function logValueRows(capture:LogCapture,metadata:MetadataItem[],fullPrecision=false):LogValueRow[] {
 const payload=(capture.responseBytes||[]).slice(5,5+(capture.payloadLength||0));
 return capture.values.map(value=>{
  const item=metadata.find(m=>m.groupCode===capture.groupCode&&m.tagCode===value.tagCode&&m.offset===value.offset);
  const width=item?getExpectedGroupPayloadLength([item])-item.offset:0;
  const rawDecimal=width>0?payload.slice(value.offset,value.offset+width).join(' '):'';
  let decoded=value.formattedValue;
  if(fullPrecision&&/^(L?REAL)(?:\[\d+\])?$/.test(value.dataType)) {
   if(typeof value.rawValue==='number')decoded=String(value.rawValue);
   else if(Array.isArray(value.rawValue))decoded=`[${value.rawValue.map(v=>v==null?'Incomplete field':String(v)).join(', ')}]`;
   if(value.rawValue!=null&&value.dropdownText)decoded+=` (${value.dropdownText})`;
  }
  return {value,rawDecimal,decoded};
 });
}

export function logValuesText(capture:LogCapture,rows:LogValueRow[]):string {
 const cell=(text:unknown)=>String(text??'').replace(/\r?\n/g,' ').replace(/\|/g,'\\|');
 const heading=`GC ${capture.groupCode} | ${capture.timestamp} | ${capture.asset||'Asset not recorded'}`;
 const table=['| Parameter | Offset | Type | Raw Data (decimal) | Decoded Value |',
  '| --- | --- | --- | --- | --- |',
  ...rows.map(({value,rawDecimal,decoded})=>`| ${cell(value.parameter)} | ${value.offset} | ${cell(value.dataType)} | ${rawDecimal||'Unavailable'} | ${cell(decoded)} |`)];
 const issues=rows.filter(r=>r.value.qualityIssue).map(r=>`${r.value.parameter}: ${r.value.qualityIssue}`);
 return [heading,'Offsets start at byte 0 of the payload (after the five-byte response header).','',...table,
  ...(issues.length?['','Data issues:',...issues]:[])].join('\n');
}
