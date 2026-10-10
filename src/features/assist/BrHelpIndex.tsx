import {useEffect,useRef,useState} from 'react';
import {BookOpen,Download,RefreshCw,Search} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {apiJson} from '../rules/library';
import './br-help.css';

type Topic={id:string;title:string;category:string;kind?:string;library?:string;file?:string;excerpt?:string};
type Document=Topic&{text:string;helpSet:string;digest:string;truncated:boolean;images:{file:string;caption:string}[]};
export function BrHelpIndex(){
 const {user}=useAccount();
 const [state,setState]=useState<any>(null),[query,setQuery]=useState(''),[category,setCategory]=useState(''),[results,setResults]=useState<Topic[]>([]),[document,setDocument]=useState<Document|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const requestId=useRef(0);
 useEffect(()=>{
  let active=true,timer:ReturnType<typeof setTimeout>;
  async function load(){try{const data=await apiJson('/api/knowledge/br-help');if(active){setState(data);if(data.phase==='building')timer=setTimeout(()=>void load(),4000)}}catch(e:any){if(active)setError(e.message)}}
  void load();return()=>{active=false;clearTimeout(timer)};
 },[state?.phase==='building']);
 useEffect(()=>{
  let active=true;
  const timer=setTimeout(()=>{void apiJson('/api/knowledge/br-help/search?'+new URLSearchParams({q:query,category})).then(data=>{if(active)setResults(data.results||[])}).catch(e=>{if(active)setError(e.message)})},300);
  return()=>{active=false;clearTimeout(timer)};
 },[query,category,state?.index?.builtAt]);
 async function open(topic:Topic){
  const id=++requestId.current;setLoading(true);setError('');
  try{const data=await apiJson('/api/knowledge/br-help/document/'+encodeURIComponent(topic.id));if(id===requestId.current)setDocument(data)}catch(e:any){if(id===requestId.current)setError(e.message)}finally{if(id===requestId.current)setLoading(false)}
 }
 async function rebuild(){try{setError('');setState(await apiJson('/api/knowledge/br-help/rebuild',{}))}catch(e:any){setError(e.message)}}
 const counts=state?.index?.counts;
 const groups=[...new Set<string>((state?.topics||[]).map((t:Topic)=>t.category))];
 return <section className="brHelp card" aria-label="B&R help index">
  <header className="brHelpHead"><div><h3><BookOpen size={19}/> B&amp;R help index</h3><p>Project formats, decoding, language syntax and supplied library manuals.</p></div><div className="actions"><a className="btn" href="/api/knowledge/br-help/guide"><Download size={14}/> Download complete guide</a>{user.role==='admin'&&<button className="btn" disabled={state?.phase==='building'} onClick={()=>void rebuild()}><RefreshCw size={14}/> Rebuild index</button>}</div></header>
  <div className="brHelpStatus" role="status">{counts?<span>{counts.vendor.toLocaleString()} vendor topics · {counts.guide} guide topics · {counts.skipped.toLocaleString()} skipped · {counts.truncated.toLocaleString()} truncated</span>:<span>Compact guide available. Vendor index is being prepared when help files are present.</span>}{state?.phase==='building'&&<div>{state.stage} · {state.current.toLocaleString()} / {state.total.toLocaleString()}<progress max={state.total||1} value={state.current}/></div>}{state?.error&&<p className="brHelpError">{state.error}</p>}{state?.guideOutdated&&<p>Updated guide available. Rebuild the search index to include it.</p>}{state&&!state.vendorHelpAvailable&&<p>Add the supplied B&amp;R manuals to the server’s knowledge/br_help folder to enable vendor topic search.</p>}<small>{state?.notice} Limits: 5 MiB per source and 100,000 extracted characters per topic. Binary assets and images are not language lessons.</small></div>
  {error&&<p className="brHelpError" role="alert">{error}</p>}
  <div className="brHelpLayout">
   <aside className="brHelpTree" aria-label="Guide contents"><b>Guide contents</b>{groups.map(group=><details key={group} open><summary>{group}</summary>{(state.topics as Topic[]).filter(t=>t.category===group).map(t=><button key={t.id} className={document?.id===t.id?'active':''} onClick={()=>void open(t)}>{t.title}</button>)}</details>)}</aside>
   <div className="brHelpMain"><form className="brHelpSearch" onSubmit={e=>e.preventDefault()}><label><Search size={16}/><input aria-label="Search B&R help" placeholder="Search IcmpPing, RETAIN, arrays, ladder…" value={query} onChange={e=>setQuery(e.target.value)}/></label><select aria-label="Reference category" value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option>{(state?.categories||[]).map((c:string)=><option key={c}>{c}</option>)}</select></form>
    <div className="brHelpResults" aria-label="Search results">{results.map(t=><button key={t.id} onClick={()=>void open(t)}><b>{t.title}</b><small>{t.kind==='guide'?'uSOPp guide':t.library||t.category}</small><span>{t.excerpt}</span></button>)}{!results.length&&<p className="muted">No matching topics.</p>}</div>
    {loading?<p role="status">Opening reference topic…</p>:document?<article className="brHelpDocument"><h3>{document.title}</h3><p className="muted">{document.helpSet} · {document.category}{document.library&&' · '+document.library}</p><p className="brHelpPath">{document.file}</p>{document.truncated&&<p className="brHelpError">This indexed topic is truncated. Consult the original manual for complete details.</p>}<pre>{document.text}</pre>{document.images.map((img,index)=><figure key={index}><img loading="lazy" src={'/api/knowledge/br-help/image/'+encodeURIComponent(document.id)+'/'+index} alt={img.caption||document.title}/>{img.caption&&<figcaption>{img.caption}</figcaption>}</figure>)}<details><summary>Source digest</summary><code>{document.digest}</code></details></article>:<div className="empty"><BookOpen size={28}/><p>Select a guide topic or search the supplied manuals.</p></div>}
   </div>
  </div>
 </section>;
}
