import {useEffect,useState} from 'react';
import {Download,RefreshCw} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {apiJson} from '../rules/library';
import './chopper-training.css';

type Example={id:string;question:string;answer:string;projectName:string;intent:string;ownerId:number;status:string;revision:number;createdAt:string;evidence:any[];helpEvidence:any[]};
export function ChopperTraining(){
 const {user}=useAccount();const admin=user.role==='admin';
 const [summary,setSummary]=useState<any>(null),[examples,setExamples]=useState<Example[]>([]),[selected,setSelected]=useState<Example|null>(null),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function load(){setBusy(true);setError('');try{const [s,e]=await Promise.all([apiJson('/api/assist/training'),apiJson('/api/assist/training/examples')]);setSummary(s);setExamples(e.examples||[])}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 useEffect(()=>{void load()},[]);
 function open(example:Example){setSelected(example);setAnswer(example.answer);setError('')}
 async function review(status:string){if(!selected)return;setBusy(true);setError('');try{await apiJson(`/api/assist/training/examples/${selected.id}/review`,{revision:selected.revision,status,answer});setSelected(null);await load()}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 return <section className="chopperTraining card" aria-label="Chopper training examples">
  <header><div><h3>Project answers and model training</h3><p>Backend analysis covers machine functions, communication traces and improvement reviews. Model weights remain unchanged until a separate training run is completed.</p></div><div className="actions"><button className="btn" disabled={busy} onClick={()=>void load()}><RefreshCw size={14}/> Refresh</button>{admin&&!!summary?.counts?.approved&&<a className="btn primary" href="/api/assist/training/export"><Download size={14}/> Export approved Q&amp;A</a>}<a className="btn" href="/api/assist/training/guide">Training instructions</a></div></header>
  <p className="muted">Source-backed project replies are saved as pending drafts. {admin?'Admin reviews drafts from all users. Approval checks citation identity; you must also check the engineering conclusion.':'You can view your own drafts. Ask Admin to review a corrected answer.'} Approved exports may contain project source excerpts and stay within your installation.</p>
  <p role="status">{summary?`${summary.counts.pending||0} pending · ${summary.counts.approved||0} approved · ${summary.counts.rejected||0} rejected`:'Loading examples…'}</p>
  {error&&<p role="alert">{error}</p>}
  <div className="chopperTrainingLayout"><aside aria-label="Saved project questions">{examples.map(example=><button className={selected?.id===example.id?'active':''} key={example.id} onClick={()=>open(example)}><b>{example.question}</b><small>{example.projectName} · {example.intent} · {example.status}{admin&&` · user ${example.ownerId}`}</small></button>)}{!examples.length&&!busy&&<p>No project answer drafts yet. Ask Chopper a question with a selected project.</p>}</aside>
   {selected?<article><h4>{selected.question}</h4><p>{selected.projectName} · {new Date(selected.createdAt).toLocaleString()} · {selected.status}</p><label>Reviewed answer<textarea value={answer} readOnly={!admin} onChange={e=>setAnswer(e.target.value)} maxLength={30000}/></label>{admin&&<div className="actions"><button className="btn primary" disabled={busy} onClick={()=>void review('approved')}>Approve corrected answer</button><button className="btn" disabled={busy} onClick={()=>void review('rejected')}>Reject</button><button className="btn" disabled={busy} onClick={()=>void review('pending')}>Keep pending</button></div>}{selected.evidence.map((item,index)=><details key={index}><summary>[{item.sourceId}] {item.file}:{item.line}{item.network&&` · network ${item.network}`}</summary><p>{item.ownership}{item.enabled===false?' · commented out':''}</p><pre>{item.excerpt}</pre></details>)}{selected.helpEvidence.map((item,index)=><details key={index}><summary>[{item.sourceId}] {item.title} · help</summary><p>{item.file}</p><pre>{item.excerpt}</pre></details>)}</article>:<div className="empty">Select a saved question to review its answer and evidence.</div>}
  </div>
 </section>;
}
