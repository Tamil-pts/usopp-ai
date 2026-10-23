import type {MetadataItem} from '../types';

export function ybsChecksum(bytes:Uint8Array|number[],end=bytes.length){let checksum=255;for(let i=0;i<end;i++)checksum^=bytes[i];return checksum&255;}
export const ybsByte=(value:number|undefined)=>value===undefined?'Unavailable':`${value} (0x${value.toString(16).padStart(2,'0').toUpperCase()})`;
export interface YbsFrameCheck {name:string;offset?:number;expected:string;actual:string;passed:boolean}
export function buildYbsReadRequest(machine:number,group:number){
 if(!Number.isInteger(machine)||machine<0||machine>255||!Number.isInteger(group)||group<0||group>65535)throw new Error('Invalid YBS machine ID or group code.');
 const bytes=new Uint8Array([241,machine,1,0,9,(group>>8)&255,group&255,0,240]);bytes[7]=ybsChecksum(bytes,7);return bytes;
}

export function ybsMetadataTable(items:MetadataItem[]){
 return [...items].sort((a,b)=>(a.sourceRow??a.tagCode)-(b.sourceRow??b.tagCode)).map(item=>({
  Screenname:item.screenName,Parameter:item.parameter,UNITS:item.units,MIN:item.min??'<null>',MAX:item.max??'<null>',TAG_DATA_TYPE:item.wireDataType,
  'Group code':item.groupCode,'Divison factor':item.divideFactor??1,'Multiplication factor':item.multiplyFactor??1,
  IS_VISIBLE:item.isVisible?'YES':'NO',IS_WRITABLE:item.isWritable?'YES':'NO','Is shown value is different':item.isShownValueDifferent?'YES':'NO',
  ...Object.fromEntries(Array.from({length:16},(_,bit)=>[`Bit: ${bit}`,item.bitDefinitions?.find(entry=>entry.bit===bit)?.label||'']))
 }));
}
export function parseYbsFrame(bytes:Uint8Array,machine?:number,group?:number){
 const total=bytes.length>=5?bytes[3]*256+bytes[4]:0,gc=bytes.length>=7?bytes[5]*256+bytes[6]:undefined;
 const issues:string[]=[];
 const calculated=bytes.length>=9?ybsChecksum(bytes,bytes.length-2):undefined;
 if(bytes.length<9)issues.push('YBS frame needs at least 9 bytes.');
 if(bytes[0]!==241)issues.push('YBS start marker must be F1.');
 if(total!==bytes.length)issues.push(`YBS total length ${bytes.length} differs from header ${total}.`);
 if(bytes.at(-1)!==240)issues.push(`YBS end marker F0 is missing at byte ${bytes.length-1}: expected ${ybsByte(240)}, received ${ybsByte(bytes.at(-1))}.`);
 const checksumValid=bytes.length>=9&&calculated===bytes.at(-2);
 if(!checksumValid)issues.push(`YBS checksum mismatch at byte ${bytes.length-2}: expected ${ybsByte(calculated)}, received ${ybsByte(bytes.at(-2))} (XOR seed FF).`);
 if(bytes[2]!==1)issues.push(`Unsupported YBS function ${bytes[2]}.`);
 if(machine!==undefined&&bytes[1]!==machine)issues.push('YBS machine ID mismatch.');
 if(group!==undefined&&gc!==group)issues.push(`YBS embedded GC ${gc} differs from selected GC ${group}.`);
 const checks:YbsFrameCheck[]=[
  {name:'Captured frame length',expected:`${total} bytes from header`,actual:`${bytes.length} bytes`,passed:bytes.length>=9&&total===bytes.length},
  {name:'Start marker',offset:0,expected:ybsByte(241),actual:ybsByte(bytes[0]),passed:bytes[0]===241},
  {name:'Function',offset:2,expected:'1 (read)',actual:String(bytes[2]??'Unavailable'),passed:bytes[2]===1},
  ...(machine===undefined?[]:[{name:'Machine ID',offset:1,expected:String(machine),actual:String(bytes[1]??'Unavailable'),passed:bytes[1]===machine}]),
  ...(group===undefined?[]:[{name:'Embedded group code',offset:5,expected:String(group),actual:String(gc??'Unavailable'),passed:gc===group}]),
  {name:'Checksum (XOR seed FF)',offset:bytes.length-2,expected:ybsByte(calculated),actual:ybsByte(bytes.at(-2)),passed:checksumValid},
  {name:'End marker',offset:bytes.length-1,expected:ybsByte(240),actual:ybsByte(bytes.at(-1)),passed:bytes.at(-1)===240},
 ];
 const trailerNote=bytes.length>=9&&bytes.at(-1)!==240&&ybsChecksum(bytes,bytes.length-1)===bytes.at(-1)?'The last byte matches the XOR checksum over the preceding bytes, but it occupies the F0 end-marker position. A trailer index or send/read length error is possible; the capture alone cannot confirm its source.':undefined;
 const nextActions=issues.length?[
  'Embedded C: verify checksum at frame[length - 2], F0 at frame[length - 1], and transmit exactly the advertised frame length.',
  ...(total>=9?[`Check the C payload size and any struct padding: this header declares ${total} bytes = 7 header + ${total-9} data + 2 trailer bytes.`]:[]),
  'Go socket receiver: accumulate the advertised total length across TCP reads before validating the checksum; retain the complete raw frame in the log.',
  'Compare the GC-specific bytes before device send and after server receive. If transmit bytes are already wrong, inspect C frame construction; if transmit is correct, inspect receiver framing and logging.',
 ]:[];
 return {success:!issues.length,resultCode:issues.length?-1:0,dataLength:Math.max(0,total-9),frameLength:total,protocol:'ybs' as const,groupCode:gc,checks,trailerNote,nextActions,
  dataBytes:issues.length?new Uint8Array():bytes.slice(7,-2),checksumValid,error:issues.join(' ')||undefined};
}
export function parseYbsMetadata(rows:string[][]):MetadataItem[]{
 const header=rows[0].map(v=>v.trim().toLowerCase()),offsets=new Map<number,number>();
 const types:Record<string,[string,number]>={UCHAR:['USINT',1],USINT:['UINT',2],UINT:['UDINT',4],FLOAT:['REAL',4]};
 const clean=(v:string|undefined)=>!v||v.trim().toLowerCase()==='<null>'?'':v.trim();
 const num=(v:string|undefined,fallback:number|null=null)=>{const text=clean(v);if(!text)return fallback;const value=Number(text);if(!Number.isFinite(value))throw new Error('YBS limits/factors must be finite numbers.');return value};
 return rows.slice(1).flatMap((cells,index)=>{
  if(cells.every(v=>!clean(v)))return [];
  const value=(name:string)=>cells[header.indexOf(name)],sourceRow=index+2,group=num(value('group code')),wire=clean(value('tag_data_type')).toUpperCase(),type=types[wire];
  if(group===null||!Number.isInteger(group)||group<0||group>65535||!type)throw new Error(`YBS row ${sourceRow}: invalid group or datatype.`);
  const divide=num(value('divison factor'),1)!,multiply=num(value('multiplication factor'),1)!;
  if(divide<=0)throw new Error(`YBS row ${sourceRow}: division factor must be positive.`);
  const offset=offsets.get(group)||0;offsets.set(group,offset+type[1]);
  return [{sNo:sourceRow-1,tagCode:sourceRow-1,screenName:clean(value('screenname')),machineVariants:'YBS',parameter:clean(value('parameter')),units:clean(value('units')),
   min:num(value('min')),max:num(value('max')),groupCode:group,offset,dataType:type[0],wireDataType:wire,protocol:'ybs',divideFactor:divide,multiplyFactor:multiply,offsetFactor:1,scaleFactor:1,
   isVisible:clean(value('is_visible')).toLowerCase()==='yes',isWritable:clean(value('is_writable')).toLowerCase()==='yes',isShownValueDifferent:clean(value('is shown value is different')).toLowerCase()==='yes',
   bitDefinitions:Array.from({length:type[1]*8},(_,bit)=>({bit,label:clean(value(`bit: ${bit}`))})).filter(bit=>bit.label),
   fromVersion:'',toVersion:'',sourceRow,sourceSheet:'Sheet1',layoutInferred:true} satisfies MetadataItem];
 });
}
