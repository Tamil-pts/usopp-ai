import {useState} from 'react';

export function HistoryResultDialog({result,onClose}:{result:any;onClose:()=>void}) {
 const [showJson,setShowJson]=useState(false);
 const modelRows=result.model?.parameters&&result.result?.rows;
 return <div role="dialog" aria-modal="true" aria-label="Stored test result" style={{position:'fixed',inset:0,background:'#0008',zIndex:1000,display:'grid',placeItems:'center',padding:24}}>
  <section className="card inputCard" style={{width:'min(1100px,95vw)',maxHeight:'90vh',overflow:'auto'}}>
   <div className="pageHead"><div><h2>{result.projectName||'Stored test result'}</h2><p className="mono">Test ID: {result.testId}</p></div><button className="btn" onClick={onClose}>Close</button></div>
   {result.error&&<p role="alert" className="failText">{result.error}</p>}
   {result.message&&<p>{result.message}</p>}
   <p>Status: {result.runStatus||'completed'}</p>
   {Object.entries(result.summary||{}).map(([name,count])=><span key={name} style={{marginRight:16}}>{name}: {String(count)}</span>)}
   {modelRows&&<><h3>{result.model.service}: {result.model.source}</h3><div className="tableWrap"><table className="table"><thead><tr><th>Reference parameter</th><th>Expected type</th><th>Group codes</th><th>Status</th><th>Evidence / details</th></tr></thead><tbody>{modelRows.map((row:any,index:number)=><tr key={index}><td>{row.name}</td><td>{row.plcType}</td><td>{row.groupCodes?.join(', ')}</td><td>{row.status||row.kind}</td><td>{row.detail}<small>{row.source} / {row.sheet}:{row.row}</small></td></tr>)}</tbody></table></div></>}
   <a className="btn" href={`/api/history/${result.historyId}/json`}>Download complete JSON</a>
   <button className="btn" onClick={()=>setShowJson(value=>!value)}>{showJson?'Hide saved data':'View complete saved data'}</button>
   {showJson&&<pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(result,null,2)}</pre>}
  </section>
 </div>;
}
