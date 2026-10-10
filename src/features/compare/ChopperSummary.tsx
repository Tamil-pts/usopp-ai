import {useEffect,useRef,useState} from 'react';
import {X} from 'lucide-react';
import {requestChopper} from '../assist/chopperRequest';
import {copyChatText} from '../assist/chatFiles';
import './chopper-summary.css';

export function ChopperSummary({open,result,onClose}:{open:boolean;result:any;onClose:()=>void}) {
 const [answer,setAnswer]=useState<any>(null),[progress,setProgress]=useState<any>(null),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const scope=useRef(''),controller=useRef<AbortController|null>(null),pending=useRef(false);
 const session=result?.sessionId||'';
 const generate=async()=>{
  if(!session||pending.current)return;
  const abort=new AbortController();controller.current=abort;pending.current=true;setError('');setProgress({stage:'Preparing comparison summary',elapsedSeconds:0});
  try{const data=await requestChopper({question:'Explain what changed between these compared projects in plain language. Categorise variable additions/removals/type changes, PLC logic, ladder, HMI position/alignment, HMI behaviour, hardware and configuration. Include specific before/after examples, source filenames and inferred impact. Use only the stored comparison evidence.',context:{comparisonSessionId:session,comparisonFocus:true}},abort.signal,setProgress);if(!abort.signal.aborted)setAnswer(data);}
  catch(e:any){if(!abort.signal.aborted)setError(e.message)}finally{if(!abort.signal.aborted){pending.current=false;setProgress(null)}}
 };
 useEffect(()=>{
  const changed=scope.current!==session;
  if(changed){controller.current?.abort();scope.current=session;pending.current=false;setAnswer(null);setError('');setNotice('');}
  if(open&&session&&!pending.current&&(changed||!answer)&&(changed||!error))void generate();
 },[open,session]);
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{if(!open)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')onClose()};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape)},[open,onClose]);
 if(!open)return null;
 return <div className="chopperSummaryOverlay"><section className="chopperSummaryDialog" role="dialog" aria-modal="true" aria-labelledby="chopper-summary-title"><header><div><h2 id="chopper-summary-title">Chopper · Project changes</h2><p>{result?.baseName||'Base project'} → {result?.newName||'Developed project'}</p></div><button className="btn" autoFocus aria-label="Close Chopper summary" onClick={onClose}><X size={18}/></button></header>
  <div className="chopperSummaryBody" aria-live="polite">{progress&&<p role="status">{progress.stage} | {progress.elapsedSeconds||0}s elapsed</p>}{error&&<div role="alert"><p>{error}</p><button className="btn" onClick={()=>void generate()}>Retry summary</button></div>}
   {answer&&<><p className="chopperSummaryText">{[answer.result.modelNotice,answer.result.answer].filter(Boolean).join('\n\n')}</p><p className="muted">Completed in {answer.elapsedSeconds}s{answer.result.semanticReviewRequired?' · Explanation requires engineer review.':''}</p>{!!answer.result.evidence?.length&&<details><summary>Source evidence</summary>{answer.result.evidence.map((e:any,i:number)=><div key={i}><b>{e.file}:{e.line||''}</b><pre>{e.excerpt}</pre></div>)}</details>}</>}
  </div><footer><span role="status">{notice}</span><button className="btn" disabled={!answer} onClick={()=>void copyChatText(answer.result.answer).then(ok=>setNotice(ok?'Summary copied.':'Select the summary and copy it manually.'))}>Copy summary</button><button className="btn primary" onClick={onClose}>Close</button></footer>
 </section></div>;
}
