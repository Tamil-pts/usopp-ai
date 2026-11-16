import type {DecoderCsvRow} from '../../../nami/src/utils/decoderCsv';

export const RS485_FIELDS:Array<[string,number,number]> = [
 ['Start',0,1],['Node ID',1,1],['Group code',2,1],['Packet length',3,2],
 ['Shift Number',5,1],['Shift date',6,1],['Shift month',7,1],['Shift year',8,2],
 ['Shift hour',10,1],['Shift minute',11,1],['Run_Time_Hour',12,1],['Run_Time_Minute',13,1],
 ['Idle time hour',14,1],['Idle time minute',15,1],['Powerfail_Time_Hour',16,1],['Powerfail_Time_Minute',17,1],
 ['RF Idle time hour',18,1],['RF Idle time minute',19,1],['Total No of Spindles attended',20,2],
 ['Piecing attended spindles',22,2],['Attempt Success spindles',24,2],['Rogue Count',26,2],['Efficiency',28,2],
 ['Roving not Present',30,2],['Lapping Present',32,2],['Top Arm open',34,2],['Yarn Not Connected',36,2],
 ['Bunch Break',38,2],['Total Piecing time',40,2],['Total Cycle time',42,2],['Machine Mode',44,1],
 ['Machine status',45,1],['Reserved data 1',46,1],['Reserved data 2',47,1],['Reserved data 3',48,1],
 ['Reserved data 4',49,1],['Reserved data 5',50,2],['Reserved data 6',52,2],['CRC',54,1],['End byte',55,1],
];
export type Rs485Capture={bytes:number[];rows:DecoderCsvRow[];issues:string[];offset:number};
export function decodeRs485(text:string,format:'hex'|'decimal',littleEndian:boolean):{captures:Rs485Capture[];notices:string[]} {
 if(text.length>1_000_000)throw new Error('Capture exceeds the 1 MB text limit. Paste a smaller excerpt.');
 const bytes:number[]=[];let skippedTx=0,directionState='RX';
 for(const [index,original] of text.split(/\r?\n/).entries()) {
  let line=original.trim();if(!line)continue;
  const direction=line.match(/\b(RX|TX)\b\s*\]?\s*[:>\-]?\s*/i);
  if(direction){directionState=direction[1].toUpperCase();line=line.slice(direction.index!+direction[0].length);}
  if(directionState==='TX'){skippedTx++;continue;}
  line=line.replace(/[,;\t]/g,' ').trim();if(!line)continue;
  let tokens=line.split(/\s+/);
  if(format==='hex'&&tokens.length===1&&/^(?:[0-9a-f]{2})+$/i.test(line))tokens=line.match(/../g)!;
  for(const token of tokens){
   if(!(format==='hex'?/^(?:0x)?[0-9a-f]{2}$/i:/^\d{1,3}$/).test(token))throw new Error(`Line ${index+1}: invalid ${format} byte "${token}". Paste byte data or Docklight RX/TX lines.`);
   const value=parseInt(token,format==='hex'?16:10);if(value>255)throw new Error(`Line ${index+1}: byte ${token} is outside 0–255.`);bytes.push(value);
  }
 }
 const captures:Rs485Capture[]=[];const notices:string[]=[];let cursor=0,ignored=0;
 while(cursor<bytes.length){
  if(bytes[cursor]!==253){ignored++;cursor++;continue;}
  if(captures.length>=500)throw new Error('More than 500 frames. Split the capture into smaller excerpts.');
  const offset=cursor,frame=bytes.slice(cursor,cursor+56),issues:string[]=[];
  const read=(start:number,width:number)=>frame.slice(start,start+width).reduce((sum,value,i)=>sum+value*256**(littleEndian?i:width-1-i),0);
  if(frame.length!==56)issues.push(`Incomplete frame: ${frame.length}/56 bytes.`);
  if(frame[2]!==90)issues.push(`Group code ${frame[2]??'missing'} is unsupported; this metadata describes GC 90 only.`);
  if(frame.length>=5&&read(3,2)!==56)issues.push(`Declared packet length ${read(3,2)} differs from metadata length 56.`);
  if(frame.length===56&&frame[55]!==240)issues.push(`End byte ${frame[55]} differs from 240 (F0).`);
  if(![1,2].includes(frame[1]))issues.push(`Node ${frame[1]??'missing'} has no RHS/LHS definition.`);
  const supported=frame[2]===90;
  const rows=RS485_FIELDS.map(([parameter,start,width],i):DecoderCsvRow=>{
   const complete=frame.length>=start+width;let decoded=complete?String(read(start,width)):'Unavailable';
   let finding=complete?'Decoded':'Incomplete field';
   if(!supported&&start>=5&&start<54){decoded='Not decoded';finding='Unsupported group; no matching metadata';}
   else if(start===54)finding=complete?'CRC algorithm not supplied; not verified':'Incomplete CRC';
   else if(start===1&&complete)decoded+=frame[1]===1?' (RHS)':frame[1]===2?' (LHS)':' (unknown node)';
   else if(start>=46&&start<=53)finding=complete?'Reserved; raw value only':'Incomplete field';
   else if(start===44||start===45)finding=complete?'Numeric code; meaning not supplied':'Incomplete field';
   if(start===2)finding='1-byte width follows explicit byte position; metadata type says unsigned short';
   const limit=start===7?12:[11,13,15,17,19].includes(start)?59:start===10?23:start===6?31:undefined;
   if(supported&&complete&&limit!==undefined&&(read(start,width)>limit||([6,7].includes(start)&&read(start,width)<1)))finding=`Outside expected calendar/time range (maximum ${limit})`;
   return {tag:i+1,parameter,offset:String(start),type:width===1?'UINT8':'UINT16',rawDecimal:frame.slice(start,start+width).join(' '),decoded,finding};
  });
  captures.push({bytes:frame,rows,issues,offset});cursor+=56;
 }
 if(ignored)notices.push(`${ignored} bytes outside FD-start frames were skipped.`);
 if(skippedTx)notices.push(`${skippedTx} TX lines excluded; this decoder reads received response frames.`);
 if(!captures.length)notices.push('No FD (253) start byte found. Check the selected byte format.');
 return {captures,notices};
}
