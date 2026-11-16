import {useEffect,useRef,useState} from 'react';
import {downloadDecoderCsv} from '../../../nami/src/utils/decoderCsv';
import {decodeRs485,RS485_FIELDS} from './rs485Decoder';
import './rs485-decoder.css';

export function Rs485LogDecoder({onClose}:{onClose:()=>void}) {
 const dialog=useRef<HTMLDialogElement>(null),file=useRef<HTMLInputElement>(null);
 const [text,setText]=useState(''),[format,setFormat]=useState<'hex'|'decimal'>('hex'),[order,setOrder]=useState('');
 const [result,setResult]=useState<ReturnType<typeof decodeRs485>|null>(null),[error,setError]=useState('');
 useEffect(()=>{dialog.current?.showModal();},[]);
 const reset=()=>{setResult(null);setError('');};
 const decode=()=>{reset();try{if(!order)throw new Error('Select the device byte order for 2-byte fields.');setResult(decodeRs485(text,format,order==='little'));}catch(e){setError(e instanceof Error?e.message:String(e));}};
 return <dialog ref={dialog} className="rs485Decoder" onCancel={onClose} aria-labelledby="rs485Title">
  <header><div><h2 id="rs485Title">Log Decoder 2 · RS-485 / Docklight</h2><p>RAP shift packet · GC 90 · 56 bytes · received captures</p></div><button className="btn" aria-label="Close Log Decoder 2" onClick={onClose}>Close</button></header>
  <div className="rs485Body">
   <p>Connect and capture through Docklight, then paste the received bytes here. Processing stays in this browser; this tool does not open a serial connection.</p>
   <div className="rs485Options"><label>Input byte format<select className="textInput" value={format} onChange={e=>{setFormat(e.target.value as 'hex'|'decimal');reset();}}><option value="hex">Hexadecimal (FD 01 5A…)</option><option value="decimal">Decimal (253 1 90…)</option></select></label><label>Device byte order<select className="textInput" value={order} onChange={e=>{setOrder(e.target.value);reset();}}><option value="">Select from device specification</option><option value="little">Little-endian</option><option value="big">Big-endian</option></select></label><button className="btn" onClick={()=>file.current?.click()}>Upload Docklight text</button></div>
   <input hidden ref={file} type="file" accept=".txt,.log,.csv" onChange={async e=>{const f=e.target.files?.[0];if(!f)return;reset();if(f.size>1_000_000){setError('Select a text capture smaller than 1 MB.');return;}try{setText(await f.text());}catch{setError('The capture could not be read.');}e.target.value='';}}/>
   <label>Received bytes / Docklight RX log<textarea className="textInput" rows={7} value={text} placeholder="FD 01 5A … F0" onChange={e=>{setText(e.target.value);reset();}} spellCheck={false}/></label>
   <div className="rs485Options"><button className="btn primary" disabled={!text.trim()} onClick={decode}>Decode received frames</button><button className="btn" onClick={()=>{setText('');reset();}}>Clear capture</button>{result?.captures.length?<button className="btn" onClick={()=>downloadDecoderCsv(result.captures.flatMap((c,i)=>c.rows.map(row=>({...row,finding:[`Capture ${i+1}`,row.finding,...c.issues].join('; ')}))),'log-decoder-2-gc90.csv')}>Export all captures CSV</button>:null}</div>
   <p><b>Metadata notice:</b> Byte positions are absolute, starting at frame byte 0. Group code occupies one byte at position 2 despite the supplied unsigned-short label. CRC at byte 54 is displayed but <b>not verified</b>; its algorithm is unknown. No scale or percentage conversion is assumed. The Tag column uses the supplied S No; device tag codes are not defined.</p>
   <details><summary>View supplied metadata · 40 fields</summary><div className="rs485Table"><table><thead><tr><th>S No</th><th>Description</th><th>Data type</th><th>No of bytes</th><th>Byte position</th></tr></thead><tbody>{RS485_FIELDS.map(([name,start,width],i)=><tr key={start}><td>{i+1}</td><td>{name}</td><td>{width===1?'UINT8':'UINT16'}</td><td>{width}</td><td>{width===1?start:`${start},${start+1}`}</td></tr>)}</tbody></table></div></details>
   {error&&<p role="alert">{error}</p>}
   {result&&<section aria-label="RS-485 decoded results"><p role="status">{result.captures.length} captures · CRC unverified</p>{result.notices.map(n=><p key={n}>{n}</p>)}{result.captures.map((capture,index)=><details key={index} open><summary>Capture {index+1} · Node {capture.bytes[1]??'?'} · GC {capture.bytes[2]??'?'} · {capture.bytes.length}/56 bytes · {capture.issues.length?'Frame issues':'Structure checked; CRC unverified'}</summary>{capture.issues.map(issue=><p role="alert" key={issue}>{issue}</p>)}<div className="rs485Table"><table><thead><tr>{['Tag','Parameter','Offset','Type','Raw decimal bytes','Decoded value','Finding'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{capture.rows.map(row=><tr key={String(row.tag)}><td>{String(row.tag)}</td><td>{row.parameter}</td><td>{row.offset}</td><td>{row.type}</td><td>{row.rawDecimal||'Unavailable'}</td><td>{row.decoded}</td><td>{row.finding}</td></tr>)}</tbody></table></div></details>)}</section>}
  </div>
 </dialog>;
}
