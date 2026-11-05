import {YbsFrameFindings} from '../../../nami/src/components/YbsFrameFindings';
import {parseYbsFrame} from '../../../nami/src/utils/ybsProtocol';
import {useMemo,useState} from 'react';
import type {MetadataItem} from '../../../nami/src/types';
import {decodeCollectedLog} from './logDecoder';
import {logValueRows,logValuesText} from './logValueView';
import {copyChatText} from './chatFiles';
import {decoderValueRow,decoderFrameRow,downloadDecoderCsv,type DecoderCsvRow} from '../../../nami/src/utils/decoderCsv';
import type {LogCapture} from './logDecoder';
import './log-decoder.css';

const labels={received:'Response received',failed:'Request / frame failed',mismatch:'Mapping / data issue',unconfirmed:'Reply unconfirmed',close_requested:'Close requested'};
export interface ChatLogData {text:string;logName:string;metadata:MetadataItem[];metadataName:string}
export function ChatLogReply({data,busy,onExplain}:{data:ChatLogData;busy?:boolean;onExplain?:(capture:Record<string,unknown>)=>void}) {
 const [endian,setEndian]=useState('little'),[variant,setVariant]=useState('all'),[group,setGroup]=useState('all'),[asset,setAsset]=useState('all');
 const [selected,setSelected]=useState<number|null>(null),[view,setView]=useState('table'),[precision,setPrecision]=useState(false),[copied,setCopied]=useState('');
 const variants=useMemo(()=>[...new Set(data.metadata.map(m=>m.machineVariants))].filter(v=>!/^(both|all)$/i.test(v)),[data]);
 const analysis=useMemo(()=>decodeCollectedLog(data.text,data.metadata.filter(m=>variant==='all'||/^(both|all)$/i.test(m.machineVariants)||m.machineVariants===variant),endian==='little'),[data,variant,endian]);
 const visible=analysis.captures.filter(c=>(group==='all'||String(c.groupCode)===group)&&(asset==='all'||c.asset===asset));
 const current=visible.find(c=>c.id===selected)||visible.find(c=>c.responseBytes)||visible[0];
 const rows=current?logValueRows(current,data.metadata,precision):[];
 const frame=current?.protocol==='ybs'&&current.responseBytes?parseYbsFrame(new Uint8Array(current.responseBytes),current.requestBytes?.[1],current.groupCode):undefined;
 const explanation=frame&&!frame.success?[...(frame.trailerNote?['Possible cause: '+frame.trailerNote]:[]),'Next checks:',...frame.nextActions]:[];
 const issues=analysis.captures.filter(c=>c.status==='failed'||c.status==='mismatch'||c.status==='unconfirmed');
 const summary=`${data.logName}: ${analysis.captures.length} captures, ${new Set(analysis.captures.map(c=>c.groupCode)).size} Group Codes. ${analysis.captures.filter(c=>c.status==='failed').length} failed; ${analysis.captures.filter(c=>c.status==='mismatch').length} mapping / data issues; ${analysis.captures.filter(c=>c.status==='unconfirmed').length} unconfirmed.`;
 const resultText=current?[summary,labels[current.status],...current.issues,...current.logErrors,...explanation,'',logValuesText(current,rows)].join('\n'):summary;
 function exportCsv(all=false){
  const exported:DecoderCsvRow[]=(all?visible:current?[current]:[]).flatMap((capture:LogCapture)=>{
   const notes=[...capture.issues,...capture.logErrors];
   const values=logValueRows(capture,data.metadata,precision).map(row=>decoderValueRow(row.value,row.rawDecimal,row.decoded));
   const records=values.length?values.map(row=>({...row,finding:[row.finding,...notes].join('; ')})):[decoderFrameRow(capture.groupCode,capture.responseBytes,notes)];
   return all?records.map(row=>({...row,finding:[`GC ${capture.groupCode}`,capture.timestamp,capture.asset,row.finding].filter(Boolean).join(' · ')})):records;
  });
  downloadDecoderCsv(exported,`${data.logName.replace(/\.[^.]+$/,'')}-${all?'filtered-captures':`GC${current?.groupCode}-capture${current?.id}`}.csv`);
 }
 return <section className="chatLogResult">
  <b>Log decoder</b><p>{summary}</p><small>{data.metadataName||'No metadata: request/frame checks only. Attach a workbook to map parameter values.'} · Recorded readings, not a live PLC connection.</small>
  {!analysis.captures.length&&<p>No complete buffers found. Include the decimal buffer, Group Code and timestamp in the log.</p>}
  <details><summary>Request failures and mapping findings ({issues.length})</summary><div className="logTable"><table><thead><tr><th>Group / time</th><th>Result</th><th>Meaning</th></tr></thead><tbody>{issues.slice(0,200).map(c=><tr key={c.id}><td><button className="btn" onClick={()=>{setGroup(String(c.groupCode));setAsset(c.asset);setSelected(c.id)}}>GC {c.groupCode}</button><small>{c.timestamp} · {c.asset}</small></td><td>{labels[c.status]}{c.resultCode!==undefined?` (code ${c.resultCode})`:''}</td><td>{[...c.issues,...c.logErrors].join('\n')||'Review decoded field issues below.'}</td></tr>)}</tbody></table></div>{issues.length>200&&<small>Showing the first 200 findings. Choose a Group Code to review its captures.</small>}</details>
  {analysis.warnings.length>0&&<details><summary>Log / workbook warnings ({analysis.warnings.length})</summary><pre>{analysis.warnings.join('\n')}</pre></details>}
  {analysis.metadataOnlyGroups.length>0&&<details><summary>Metadata groups absent from this excerpt</summary><p>{analysis.metadataOnlyGroups.join(', ')}. A missing log capture does not prove a failed PLC request.</p></details>}
  {current&&<>
   <div className="chatResultChoices"><label>Group Code<select value={group} onChange={e=>{setGroup(e.target.value);setSelected(null);setCopied('')}}><option value="all">All groups</option>{[...new Set(analysis.captures.map(c=>c.groupCode))].sort((a,b)=>a-b).map(g=><option key={g} value={g}>GC {g}</option>)}</select></label>
    <label>Asset<select value={asset} onChange={e=>{setAsset(e.target.value);setSelected(null);setCopied('')}}><option value="all">All assets</option>{[...new Set(analysis.captures.map(c=>c.asset))].map(a=><option key={a} value={a}>{a||'Not recorded'}</option>)}</select></label>
    <label>Captured time<select value={current.id} onChange={e=>{setSelected(Number(e.target.value));setCopied('')}}>{visible.map(c=><option key={c.id} value={c.id}>GC {c.groupCode} · {c.timestamp} · {labels[c.status]}</option>)}</select></label>
   </div>
   <details><summary>Decoding options</summary><div className="chatResultChoices"><label>Byte order<select disabled={current.protocol==='ybs'} value={current.protocol==='ybs'?'big':endian} onChange={e=>{setEndian(e.target.value);setCopied('')}}><option value="little">Little-endian</option><option value="big">Big-endian</option></select></label>{variants.length>0&&<label>Machine variant<select value={variant} onChange={e=>{setVariant(e.target.value);setCopied('')}}><option value="all">All workbook rows</option>{variants.map(v=><option key={v}>{v}</option>)}</select></label>}<label><input type="checkbox" checked={precision} onChange={e=>{setPrecision(e.target.checked);setCopied('')}}/> Full REAL precision</label></div></details>
   <div className="actions"><b>GC {current.groupCode} · {labels[current.status]}</b><button className={'btn '+(view==='table'?'primary':'')} onClick={()=>setView('table')}>Table</button><button className={'btn '+(view==='text'?'primary':'')} onClick={()=>setView('text')}>Simple text</button><button className="btn" onClick={()=>void copyChatText(resultText).then(ok=>setCopied(ok?'Result copied.':'Select Simple text and copy it manually.'))}>Copy result</button><button type="button" className="btn" onClick={()=>exportCsv()}>Export capture (CSV)</button><button type="button" className="btn" onClick={()=>exportCsv(true)}>Export filtered captures (CSV)</button>{onExplain&&<button className="btn" disabled={busy} onClick={()=>onExplain({groupCode:current.groupCode,machineId:current.requestBytes?.[1],responseBytes:current.responseBytes,requestLine:current.requestLine,responseLine:current.responseLine,timestamp:current.timestamp,asset:current.asset,status:current.status,resultCode:current.resultCode,issues:current.issues,logErrors:current.logErrors,payloadLength:current.payloadLength,expectedLength:current.expectedLength,protocol:current.protocol,byteOrder:current.protocol==='ybs'?'big':endian,variant,values:rows.map(r=>({parameter:r.value.parameter,tagCode:r.value.tagCode,offset:r.value.offset,dataType:r.value.dataType,rawValue:r.value.rawValue,actualValue:r.value.actualValue,divideFactor:r.value.divideFactor,multiplyFactor:r.value.multiplyFactor,sourceRow:r.value.sourceRow,value:r.decoded,rawDecimal:r.rawDecimal,qualityIssue:r.value.qualityIssue}))})}>Explain this capture</button>}<small role="status">{copied}</small></div>
   {current.protocol==='ybs'&&current.responseBytes&&<YbsFrameFindings bytes={current.responseBytes} machine={current.requestBytes?.[1]} group={current.groupCode} metadataBytes={current.expectedLength}/>}
   {view==='text'?<textarea className="logResultText textInput" aria-label="Copyable decoded log result" readOnly rows={12} value={resultText}/>:<>
    <p>{[...current.issues,...current.logErrors].join('\n')}</p>
    {rows.length?<div className="logTable"><table><thead><tr><th>Tag</th><th>Parameter</th><th>Offset</th><th>Type</th><th>Raw decimal bytes</th><th>Decoded value</th><th>Finding</th></tr></thead><tbody>{rows.map(({value,rawDecimal,decoded},i)=><tr key={`${value.tagCode}:${value.offset}:${i}`}><td>{value.tagCode}</td><td>{value.parameter}<small className="logScreenName">{value.screenName}</small></td><td>+{value.offset} B</td><td>{value.dataType}</td><td className="logBytes">{rawDecimal||'Unavailable'}</td><td className="logDecodedValue">{decoded}{value.protocol==='ybs'&&<small>Raw {String(value.rawValue??'unavailable')} / {value.divideFactor} * {value.multiplyFactor} {value.units}</small>}</td><td>{value.qualityIssue|| (value.isInRange?'Decoded':'Data issue')}</td></tr>)}</tbody></table></div>:<p>{data.metadata.length?'No valid mapped values for this capture. Review the frame findings above.':'Attach the matching metadata to decode parameter values.'}</p>}
   </>}
   <small>{current.protocol==='ybs'?'YBS: offset 0 follows the seven-byte header. Actual values use division/multiplication factors; limits apply to actual values. Type widths and bit names come from YBS metadata.':'Offset 0 starts after the five-byte response header. Default numeric display uses up to four decimals. MIN/MAX are reference values.'}</small>
   <details><summary>All received raw bytes</summary><pre>{current.responseBytes?.join(' ')||'No response bytes recorded.'}</pre></details>
  </>}
 </section>;
}
