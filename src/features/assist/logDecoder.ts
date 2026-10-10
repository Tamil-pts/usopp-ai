import type {MetadataItem, ParsedParamValue} from '../../../nami/src/types';
import {parsePLCResponse, parseGroupValues, calculateXorChecksum} from '../../../nami/src/utils/packetParser';
import {getExpectedGroupPayloadLength} from '../../../nami/src/utils/metadataParser';

export type LogStatus = 'received'|'failed'|'mismatch'|'unconfirmed'|'close_requested';
export interface LogCapture {
  id:number; groupCode:number; asset:string; timestamp:string; requestTimestamp?:string;
  requestLine?:number; responseLine?:number; requestBytes?:number[]; responseBytes?:number[];
  machineId?:number; resultCode?:number; payloadLength?:number; expectedLength?:number;
  status:LogStatus; issues:string[]; logErrors:string[]; values:ParsedParamValue[];
}
export interface LogAnalysis {captures:LogCapture[]; warnings:string[]; metadataOnlyGroups:number[]; lineCount:number}

// Responses contain no GC. Use the logged GC and asset, never payload guesses.
export function decodeCollectedLog(text:string, metadata:MetadataItem[], littleEndian=true):LogAnalysis {
  const captures:LogCapture[]=[], warnings:string[]=[];
  const pending=new Map<string,LogCapture[]>(), recent=new Map<string,LogCapture>();
  const groups=new Map<number,MetadataItem[]>();
  for(const item of metadata)groups.set(item.groupCode,[...(groups.get(item.groupCode)||[]),item]);
  const lines=text.split(/\r?\n/);
  for(let index=0;index<lines.length;index++) {
    const line=lines[index], lineNo=index+1;
    const match=line.match(/\b(writeBuffer|buffer):\s*\[([^\]]*)\]\s*for groupCode\s+(\d+)/i);
    const asset=line.match(/(?:for asset|deviceName)\s+([^\s",]+)/i)?.[1]||line.match(/(?:data|device)\s+(AST[A-Za-z0-9]+)/i)?.[1]||'';
    const timestamp=line.match(/\bts=([^\s]+)/)?.[1]||`Line ${lineNo}`;
    if(!match) {
      if(/level=ERROR|\btimeout\b|\btimed out\b/i.test(line)) {
        const error=line.match(/\bmsg="(.*)"\s*$/)?.[1]||line.trim();
        const gc=line.match(/\bgroupCode\s*[=:]?\s*(\d+)/i)?.[1]||line.match(/float64=(\d+)/)?.[1]||line.match(/_([0-9]+)\s*[:-]/)?.[1];
        const target=gc?recent.get(`${asset}:${gc}`):recent.get(asset);
        if(target)target.logErrors.push(`Line ${lineNo}: ${error}`);else warnings.push(`Line ${lineNo}: ${error}`);
      }else if(/\b(?:writeBuffer|buffer):/i.test(line))warnings.push(`Line ${lineNo}: buffer format not recognized; expected decimal bytes and groupCode.`);
      continue;
    }
    const groupCode=Number(match[3]), key=`${asset}:${groupCode}`;
    const tokens=match[2].trim().split(/[\s,]+/).filter(Boolean);
    if(!tokens.length||tokens.some(t=>!/^\d+$/.test(t)||Number(t)>255)) {
      warnings.push(`Line ${lineNo}: GC ${groupCode} has invalid decimal bytes (must be 0–255).`);continue;
    }
    const bytes=tokens.map(Number), isRequest=match[1].toLowerCase()==='writebuffer';
    let capture:LogCapture;
    if(isRequest) {
      capture={id:captures.length,groupCode,asset,timestamp,requestTimestamp:timestamp,requestLine:lineNo,requestBytes:bytes,
        machineId:bytes[1],status:groupCode===11?'close_requested':'unconfirmed',issues:[],logErrors:[],values:[]};
      captures.push(capture);
      const declared=bytes.length>=5?bytes[3]*256+bytes[4]:-1;
      if(bytes.length<9||bytes[0]!==3||bytes[2]!==1||declared+7!==bytes.length||bytes.at(-1)!==2||calculateXorChecksum(bytes,0,bytes.length-2)!==bytes.at(-2)) {
        capture.issues.push('Request header, function, length, checksum or ETX is invalid.');capture.status='failed';
      }
      if(bytes.length>=7&&bytes[5]*256+bytes[6]!==groupCode) {
        capture.issues.push(`Logged GC ${groupCode} differs from request GC ${bytes[5]*256+bytes[6]}.`);capture.status='failed';
      }
      if(groupCode!==11)pending.set(key,[...(pending.get(key)||[]),capture]);
    }else {
      const queue=pending.get(key)||[], matching=queue.filter(c=>c.machineId===bytes[1]);
      capture=matching.length===1?matching[0]:{id:captures.length,groupCode,asset,timestamp,machineId:bytes[1],status:'received',issues:[],logErrors:[],values:[]};
      if(matching.length===1)pending.set(key,queue.filter(c=>c!==capture));else {
        captures.push(capture);warnings.push(`Line ${lineNo}: GC ${groupCode} response has ${matching.length?'ambiguous requests':'no matching request in this excerpt'}; mapped using its logged GC.`);
        if(queue.length&&matching.length===0)capture.issues.push(`Response Machine ID ${bytes[1]} does not match pending request IDs ${[...new Set(queue.map(c=>c.machineId))].join(', ')}.`);
      }
      capture.responseLine=lineNo;capture.timestamp=timestamp;capture.responseBytes=bytes;
      const parsed=parsePLCResponse(bytes,capture.machineId);
      capture.resultCode=parsed.resultCode;capture.payloadLength=parsed.dataLength;
      capture.status=capture.issues.length?'failed':parsed.success?'received':'failed';
      if(!parsed.success)capture.issues.push(parsed.error||`PLC error ${parsed.resultCode}.`);
      if(bytes.length!==parsed.dataLength+7){capture.issues.push(`Frame has ${bytes.length} bytes; header requires ${parsed.dataLength+7}.`);capture.status='failed'}
      const loggedLength=line.match(/\blength\s+(\d+)/i)?.[1];
      if(loggedLength&&Number(loggedLength)!==bytes.length){capture.issues.push(`Logged length ${loggedLength} differs from ${bytes.length} captured bytes.`);capture.status='failed'}
      const items=groups.get(groupCode)||[];
      if(!items.length){capture.issues.push('No matching metadata group; values cannot be mapped.');if(metadata.length&&capture.status==='received')capture.status='mismatch'}
      else {
        capture.expectedLength=getExpectedGroupPayloadLength(items);
        if(parsed.success&&capture.expectedLength!==parsed.dataLength) {
          if(capture.status!=='failed')capture.status='mismatch';
          capture.issues.push(`Metadata requires ${capture.expectedLength} payload bytes; PLC sent ${parsed.dataLength}. Check the workbook version and GC mapping.`);
        }
        if(parsed.success&&capture.status!=='failed') {
          capture.values=parseGroupValues(parsed.dataBytes,items,littleEndian).map((v,i)=> {
            const required=getExpectedGroupPayloadLength([items[i]]);
            return required>parsed.dataLength?{...v,rawValue:null,formattedValue:'Incomplete field',isInRange:false,qualityIssue:`Field ends at byte ${required}; payload has ${parsed.dataLength} bytes.`}:v;
          });
          if(capture.values.some(v=>!v.isInRange)&&capture.status==='received')capture.status='mismatch';
        }
      }
    }
    recent.set(key,capture);recent.set(asset,capture);
  }
  for(const c of captures) {
    if(c.status==='unconfirmed')c.issues.push('No reply recorded in this excerpt. Logging may have stopped before the response; a timeout is not proven.');
    if(c.status==='close_requested')c.issues.push('GC 11 close command sent. No reply frame is expected; socket closure is not proven by this line.');
    if(c.logErrors.length&&c.status==='received')c.status='mismatch';
    const normalize=(name:string)=>name.toLowerCase().replace(/[^a-z0-9]/g,'');
    c.values=c.values.map(v=>{
      const diagnostic=c.logErrors.find(error=>{
        const resource=error.match(/resource\s+(.+?):/i)?.[1]||error.match(/starting byte\s+\d+\s*-\s*(.+?)\s*-\s*%/)?.[1];
        return resource&&normalize(resource.replace(new RegExp(`_${c.groupCode}$`),''))===normalize(v.parameter);
      });
      if(diagnostic)return {...v,isInRange:false,qualityIssue:diagnostic};
      if(typeof v.rawValue==='string'&&/[\u0000-\u001f\u007f\ufffd]/.test(v.rawValue))return {...v,isInRange:false,qualityIssue:'String contains control or undecodable characters. Check the STRING offset and workbook version.'};
      return v;
    });
    if(c.values.some(v=>!v.isInRange)&&c.status==='received')c.status='mismatch';
  }
  for(const c of captures.filter(c=>c.groupCode===10&&c.responseBytes)) {
    const version=c.values.find(v=>/program.*version/i.test(v.parameter));
    const item=groups.get(10)?.find(m=>m.tagCode===version?.tagCode);
    if(typeof version?.rawValue==='number'&&item) {
      const from=Number(item.fromVersion),to=Number(item.toVersion);
      if(Number.isFinite(from)&&Number.isFinite(to)&&(version.rawValue<from||version.rawValue>to))
        warnings.push(`GC 10 at ${c.timestamp}: PLC program version ${version.formattedValue} is outside this metadata row's FROM_VERSION ${item.fromVersion} / TO_VERSION ${item.toVersion}. Confirm the correct workbook before relying on mapped values.`);
    }
  }
  return {captures,warnings,lineCount:lines.length,metadataOnlyGroups:[...groups.keys()].filter(gc=>!captures.some(c=>c.groupCode===gc)).sort((a,b)=>a-b)};
}
