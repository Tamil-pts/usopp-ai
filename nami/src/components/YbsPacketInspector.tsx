import React,{useState} from 'react';
import type {GroupResponseData} from '../types';
import {YbsFrameFindings} from './YbsFrameFindings';
import {buildYbsReadRequest,parseYbsFrame} from '../utils/ybsProtocol';

const hex=(bytes:number[]|Uint8Array)=>Array.from(bytes,b=>b.toString(16).padStart(2,'0').toUpperCase()).join(' ');
export function YbsPacketInspector({response,group,machine}:{response?:GroupResponseData;group:number;machine:number}){
 const [open,setOpen]=useState(false),bytes=response?.rawBytes||[],parsed=parseYbsFrame(new Uint8Array(bytes),machine,group);
 const sent=response?.sentBytes?.length?response.sentBytes:Array.from(buildYbsReadRequest(machine,group));
 return <section className="bg-slate-900 text-slate-200 border-t border-slate-700 p-3 text-xs">
  <button onClick={()=>setOpen(!open)} className="font-semibold">{open?'▾':'▸'} YBS F1/F0 packet inspector · GC {group} · {bytes.length?parsed.success?'Valid frame':'Invalid frame':'Not read'}</button>
  {open&&<div className="space-y-3 mt-3">
   <p>7-byte header · total frame length in bytes 3–4 · embedded GC in bytes 5–6 · big-endian data · XOR seed FF · F0 end marker.</p>
   <p className="font-mono break-all">Request: {hex(sent)}</p>
   {!!bytes.length&&<><p role={parsed.success?undefined:'alert'} className={parsed.success?'text-emerald-400':'text-red-400'}>{parsed.error||`Frame ${parsed.frameLength} bytes; data ${parsed.dataLength} bytes. Metadata expects ${response?.expectedLength??'unknown'} data bytes.`}</p>
    <YbsFrameFindings bytes={bytes} machine={machine} group={group} metadataBytes={response?.expectedLength}/>
    {response&&!response.lengthMatch&&<p className="text-amber-400">Metadata length differs from the received data. Missing fields remain unavailable; extra bytes are unmapped.</p>}
    <p>Machine {bytes[1]} · Function {bytes[2]} · Embedded GC {parsed.groupCode} · Last byte {hex(bytes.slice(-1))}</p>
    <details><summary>Received frame ({bytes.length} bytes)</summary><pre className="whitespace-pre-wrap break-all max-h-52 overflow-auto mt-2">{hex(bytes)}</pre></details>
    {parsed.success&&<details><summary>Data at frame byte 7 ({parsed.dataLength} bytes)</summary><pre className="whitespace-pre-wrap break-all max-h-52 overflow-auto mt-2">{hex(parsed.dataBytes)}</pre></details>}
   </>}
   <p>Actual = raw / division factor × multiplication factor. Offsets are inferred from worksheet order. Status names come only from the YBS workbook. Session closes locally; no SpinConnect GC 11 is sent.</p>
  </div>}
 </section>;
}
