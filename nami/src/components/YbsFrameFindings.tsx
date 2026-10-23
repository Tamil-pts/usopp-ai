import React from 'react';
import {parseYbsFrame} from '../utils/ybsProtocol';
import './ybs-findings.css';

export function YbsFrameFindings({bytes,machine,group,metadataBytes}:{bytes:number[];machine?:number;group:number;metadataBytes?:number}){
 if(!bytes.length)return null;
 const frame=parseYbsFrame(new Uint8Array(bytes),machine,group);
 if(frame.success)return null;
 return <section className="ybsFrameFindings" aria-label="YBS frame error explanation">
  <h4>Why GC {group} was rejected</h4>
  <p>The received frame failed integrity checks. Parameter readings are withheld until a valid frame is available.</p>
  <div className="ybsChecks"><table><thead><tr><th>Check</th><th>Byte index (from 0)</th><th>Expected</th><th>Received</th><th>Result</th></tr></thead><tbody>
   {frame.checks.map(check=><tr key={check.name} data-result={check.passed?'pass':'fail'}><td>{check.name}</td><td>{check.offset??'—'}</td><td>{check.expected}</td><td>{check.actual}</td><td>{check.passed?'PASS':'FAIL'}</td></tr>)}
  </tbody></table></div>
  {metadataBytes!==undefined&&<p>Header-declared data length: {frame.dataLength} bytes. Metadata layout: {metadataBytes} bytes. {frame.dataLength===metadataBytes?'These lengths match; they do not establish frame integrity.':'The metadata length also differs and needs review.'}</p>}
  {frame.trailerNote&&<p><strong>Possible cause: </strong>{frame.trailerNote}</p>}
  <h5>Next checks</h5><ol>{frame.nextActions.map(action=><li key={action}>{action}</li>)}</ol>
  <p className="ybsTail">Received tail: [{bytes.slice(-8).join(' ')}]. Device, receiver and logging code must be compared to confirm the cause.</p>
 </section>;
}
