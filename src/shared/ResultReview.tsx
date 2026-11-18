import {useMemo,useState} from 'react';
import {Download,Search} from 'lucide-react';
import {downloadCSV} from './download';
import {evidenceText,orderedFindings,type ReviewFinding,type ReviewStatus} from './resultEvidence';
import './result-review.css';
const labels:Record<ReviewStatus,string>={fail:'Failed',not_found:'Not found',warn:'Warnings',unknown:'Unclassified',pass:'Passed',skipped:'Skipped / optional'};

export function ResultReview({title,rows,sourceKind,onSource}:{title:string;rows:ReviewFinding[];sourceKind:'issues'|'checks';onSource?:(file:string,line:number)=>void}){
 const [status,setStatus]=useState('action'),[query,setQuery]=useState(''),[limit,setLimit]=useState(12);
 const sorted=useMemo(()=>orderedFindings(rows),[rows]);
 const visible=sorted.filter(r=>(status==='all'||status==='action'&&!['pass','skipped'].includes(r.status)||r.status===status)&&
  `${r.title} ${r.scope} ${r.file} ${evidenceText(r.expected)} ${evidenceText(r.actual)} ${r.recommendations.join(' ')}`.toLowerCase().includes(query.toLowerCase()));
 return <section className="resultReview card" aria-label={`${title} evidence review`}>
  <header><div><h2>{title} · Review & next actions</h2><p>{rows.length} reported {sourceKind}. Original engine statuses and values are retained.</p></div><button type="button" className="btn" disabled={!visible.length} onClick={()=>downloadCSV(visible.map(r=>({Status:r.engineStatus,Finding:r.title,Scope:r.scope,File:r.file,Line:r.line||'',Expected:evidenceText(r.expected),Actual:evidenceText(r.actual),Recommendation:r.recommendations.join('\n')})),`${title}_finding_review.csv`)}><Download size={15}/>Export findings CSV</button></header>
  <div className="resultReviewCounts">{(Object.keys(labels) as ReviewStatus[]).map(s=><button type="button" className={s} aria-pressed={status===s} key={s} onClick={()=>{setStatus(s);setLimit(12)}}><strong>{rows.filter(r=>r.status===s).length}</strong>{labels[s]}</button>)}</div>
  <div className="resultReviewFilters"><label>Show<select aria-label={`${title} review status`} value={status} onChange={e=>{setStatus(e.target.value);setLimit(12)}}><option value="action">Action required</option><option value="all">All reported results</option>{Object.entries(labels).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label><label><Search size={15}/><input aria-label={`Search ${title} findings`} placeholder="Tag, Group Code, rule, source or finding" value={query} onChange={e=>{setQuery(e.target.value);setLimit(12)}}/></label></div>
  {!rows.length?<p role="status">No finding records were supplied. Check the run summary and detailed results; this alone does not establish a pass.</p>:!visible.length?<p role="status">No results match this view. Choose All reported results to inspect passed, skipped or optional checks.</p>:<><p className="resultReviewCount">{visible.length} matching {sourceKind}</p><div className="resultReviewList">{visible.slice(0,limit).map(r=><details key={r.id} className={r.status}>
   <summary><span className="resultReviewState">{labels[r.status]}</span><strong>{r.title}</strong><small>{r.scope}</small></summary>
   <div className="resultReviewBody"><p><b>Engine status:</b> {r.engineStatus}</p><p><b>Source:</b> {r.file||'Not reported'}{r.line>0?` · line ${r.line}`:''}</p>{r.file&&r.line>0&&onSource&&<button className="btn" type="button" onClick={()=>onSource(r.file,r.line)}>Open reported source</button>}
    <div className="resultReviewComparison"><section><h3>Expected</h3><pre>{evidenceText(r.expected)}</pre></section><section><h3>Actual</h3><pre>{evidenceText(r.actual)}</pre></section></div>
    <aside><h3>Recommended next action</h3>{r.recommendations.map((action,i)=><p key={i}>{action}</p>)}</aside>
    {!['pass','skipped'].includes(r.status)&&<p className="resultReviewRecheck">After review or correction, rerun the affected checks against the same project, target and packet branch. A suggested action does not change this result or grant approval.</p>}
   </div></details>)}</div>{visible.length>limit&&<button type="button" className="btn" onClick={()=>setLimit(v=>v+24)}>Show 24 more findings</button>}</>}
 </section>;
}
