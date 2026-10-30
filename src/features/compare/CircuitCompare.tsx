import {useEffect,useRef,useState,type ReactNode} from 'react';
import {CircuitBoard,Upload,FileText,Download,Sparkles,Search,Link2,ZoomIn,ZoomOut,Maximize2,CheckCircle2,AlertTriangle} from 'lucide-react';
import {CircuitObjectInspector,type DrawingObjectOverlay} from './CircuitObjectInspector';
import {ResizeHandle} from './ResizeHandle';
import {useLinkedScroll} from './useLinkedScroll';
import {userStorage} from '../../shared/userStorage';
import {useCircuitMarkups} from './useCircuitMarkups';

type Source={page:number;text:string;bbox:number[];uncertain?:boolean};
type Change={id:string;pairId:string;category:string;status:string;label:string;before:Source|null;after:Source|null;evidenceKind:string;assessment?:string;issue?:string;extraction:string;review:string;note:string;possibleImpact:string;verification:string};
type Page={number:number;image:string;width:number;height:number;title:string;notices:string[];textWords:number;tables:number};
type Pair={id:string;base:number|null;developed:number|null;title:string;status:string;changeCount:number;match:string;matchReview:boolean;similarity:number;overlay?:string;reordered?:boolean};
type Result={engineVersion?:string;uncertainFindings?:Change[];sessionId:string;baseName:string;developedName:string;basePages:Page[];developedPages:Page[];pairs:Pair[];changes:Change[];summary:Record<string,number>;limitations:string[];elapsedSeconds:number};
type Area={category:string;count:number;sourceIds:string[];possibleImpact:string;verify:string};
type Findings={summary:string;areas:Area[];limitations:string[]};
type Prose={paragraphs:{text:string;sourceIds:string[]}[];notice:string;scope:string[]};
type Job={status:string;phase?:string;current?:number;total?:number;error?:string};

async function request<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch(url,options);let value:any={};try{value=await response.json()}catch{/* retain HTTP error */}
 if(response.status===404||response.status===405)throw new Error('Circuit Compare is unavailable on the running API, or this comparison session no longer exists. Check that UI and API versions match; restart uSOPp after updating.');
 if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:`Request failed (HTTP ${response.status}).`);
 return value as T;
}
const categories=['Connections','Components','Cable specifications','Terminal mapping','BOM','Drawing / annotations','Revision information'];

export function CircuitCompare({projectLink}:{projectLink?:ReactNode}={}){
 const [base,setBase]=useState<File|null>(null),[developed,setDeveloped]=useState<File|null>(null);
 const [session,setSession]=useState(()=>userStorage.getItem('usopp_circuit_compare_session')||'');
 const [result,setResult]=useState<Result|null>(null),[job,setJob]=useState<Job|null>(null),[starting,setStarting]=useState(false),[error,setError]=useState('');
 const [pairId,setPairId]=useState(''),[changeId,setChangeId]=useState('');
 const [category,setCategory]=useState('all'),[status,setStatus]=useState('all'),[reviewFilter,setReviewFilter]=useState('all'),[search,setSearch]=useState(''),[pageSearch,setPageSearch]=useState(''),[pageFilter,setPageFilter]=useState('all'),[limit,setLimit]=useState(50);
 const [zoom,setZoom]=useState(0),[height,setHeight]=useState(560),[linked,setLinked]=useState(true),[highlights,setHighlights]=useState(true),[overlay,setOverlay]=useState(false);
 const [review,setReview]=useState('pending'),[note,setNote]=useState(''),[saving,setSaving]=useState(false),[reviewNotice,setReviewNotice]=useState('');
 const [showUncertain,setShowUncertain]=useState(false),[objectOverlay,setObjectOverlay]=useState<[DrawingObjectOverlay|null,DrawingObjectOverlay|null]>([null,null]);
 const [findings,setFindings]=useState<Findings|null>(null),[prose,setProse]=useState<Prose|null>(null),[explaining,setExplaining]=useState(false),[reportBusy,setReportBusy]=useState(false);
 const scroll=useLinkedScroll<HTMLDivElement>();const epoch=useRef(0);
 const busy=starting||job?.status==='running';
 const pair=result?.pairs.find(p=>p.id===pairId)||result?.pairs[0];
 const selected=[...(result?.changes||[]),...(result?.uncertainFindings||[])].find(c=>c.id===changeId);
 const allFindings=[...(result?.changes||[]),...(showUncertain?result?.uncertainFindings||[]:[])];
 const outdated=!!result&&Number(result.engineVersion||1)<2.1;
 const selectChange=(change:Change)=>{setChangeId(change.id);setPairId(change.pairId)};
 const choosePair=(id:string)=>{setPairId(id);setChangeId('');scroll.refs.forEach(ref=>ref.current?.scrollTo({top:0,left:0}))};
 const markup=useCircuitMarkups(result?session:'',pair?.id||'',choosePair);

 useEffect(()=>{
  if(!session)return;
  let stopped=false;const abort=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
  const poll=async()=>{
   try{
    const next=await request<Job>(`/api/circuit-compare/${session}/status`,{signal:abort.signal});if(stopped)return;setJob(next);
    if(next.status==='complete'){
     const data=await request<Result>(`/api/circuit-compare/${session}/result`,{signal:abort.signal});if(stopped)return;
     setResult(data);setPairId(data.pairs[0]?.id||'');setError('');
     const areas=await request<Findings>(`/api/circuit-compare/${session}/analysis`,{signal:abort.signal});if(!stopped)setFindings(areas);
    }else if(next.status==='failed')setError(next.error||'Drawing comparison failed.');
    else timer=setTimeout(()=>void poll(),1000);
   }catch(e:any){if(!stopped)setError(e.message)}
  };
  void poll();return()=>{stopped=true;abort.abort();if(timer)clearTimeout(timer)};
 },[session]);
 useEffect(()=>{setLimit(50)},[category,status,reviewFilter,search]);
 useEffect(()=>{setReview(selected?.review||'pending');setNote(selected?.note||'');setReviewNotice('')},[changeId,session]);
 useEffect(()=>{epoch.current++;setProse(null)},[session]);

 const run=async()=>{
  if(!base||!developed||busy)return;
  if(![base,developed].every(f=>f.size<=75*1024*1024)){setError('Each drawing must be no larger than 75 MB.');return}
  setStarting(true);setError('');
  try{
   const body=new FormData();body.append('base',base);body.append('developed',developed);
   const next=await request<Job&{sessionId:string}>('/api/circuit-compare/start',{method:'POST',body});
   setResult(null);setFindings(null);setProse(null);setChangeId('');setJob(next);setSession(next.sessionId);userStorage.setItem('usopp_circuit_compare_session',next.sessionId);
  }catch(e:any){setError(e.message)}finally{setStarting(false)}
 };
 const recompare=async()=>{
  if(busy)return;setStarting(true);setError('');
  try{const next=await request<Job&{sessionId:string}>(`/api/circuit-compare/${session}/recompare`,{method:'POST'});
   setResult(null);setFindings(null);setProse(null);setChangeId('');setObjectOverlay([null,null]);setJob(next);setSession(next.sessionId);userStorage.setItem('usopp_circuit_compare_session',next.sessionId);
  }catch(e:any){setError(e.message)}finally{setStarting(false)}
 };
 const saveReview=async()=>{
  if(!selected||!result)return;setSaving(true);setReviewNotice('');const current=epoch.current;
  try{
   const updated=await request<Change>(`/api/circuit-compare/${session}/review/${selected.id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({review,note})});
   if(current!==epoch.current)return;
   setResult(previous=>previous?{...previous,changes:previous.changes.map(c=>c.id===updated.id?updated:c),uncertainFindings:previous.uncertainFindings?.map(c=>c.id===updated.id?updated:c),summary:{...previous.summary,pendingReview:previous.changes.reduce((count,c)=>count+((c.id===updated.id?updated:c).review==='pending'?1:0),0)}}:previous);
   setReviewNotice('Review saved.');setFindings(await request<Findings>(`/api/circuit-compare/${session}/analysis`));
  }catch(e:any){setReviewNotice(e.message)}finally{setSaving(false)}
 };
 const explain=async()=>{
  if(!result||explaining)return;setExplaining(true);const current=epoch.current;
  try{const data=await request<Prose>(`/api/circuit-compare/${session}/explain`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({changeIds:selected?[selected.id]:[]})});if(current===epoch.current)setProse(data)}
  catch(e:any){if(current===epoch.current)setProse({paragraphs:[],scope:[],notice:e.message})}finally{setExplaining(false)}
 };
 const downloadReport=async()=>{
  if(reportBusy)return;setReportBusy(true);setError('');
  try{
   const response=await fetch(`/api/circuit-compare/${session}/report`);
   if(!response.ok){let value:any={};try{value=await response.json()}catch{}throw new Error(value.detail||'PDF export failed.')}
   const url=URL.createObjectURL(await response.blob());const anchor=document.createElement('a');anchor.href=url;anchor.download='MatchView_Circuit_Comparison.pdf';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),20000);
  }catch(e:any){setError(e.message)}finally{setReportBusy(false)}
 };
 const filtered=allFindings.filter(c=>(category==='all'||c.category===category)&&(status==='all'||c.status===status)&&(reviewFilter==='all'||c.review===reviewFilter)&&`${c.id} ${c.label} ${c.category} ${c.before?.text||''} ${c.after?.text||''}`.toLowerCase().includes(search.toLowerCase()));
 const pairs=(result?.pairs||[]).filter(p=>(pageFilter==='all'||(pageFilter==='changed'?p.status!=='unchanged':p.status===pageFilter))&&`${p.base||''} ${p.developed||''} ${p.title}`.toLowerCase().includes(pageSearch.toLowerCase()));
 const pairChanges=allFindings.filter(c=>c.pairId===pair?.id);

 return <section className="circuitWorkspace" aria-label="Circuit Compare">
  <header className="circuitHeading"><div><span className="circuitEyebrow">MATCHVIEW / ELECTRICAL DRAWINGS</span><h1><CircuitBoard size={26}/>Circuit Compare</h1><p>Compare PDF drawings, engineering tables and revisions side by side.</p></div><div className="compareHeadingAside">{projectLink}
   {result&&<div className="circuitActions"><a className="btn" href={`/api/circuit-compare/${session}/export`} download><Download size={15}/>Change data</a><button className="btn primary" disabled={reportBusy} onClick={()=>void downloadReport()}><FileText size={16}/>{reportBusy?'Preparing PDF…':'PDF comparison report'}</button></div>}
  </div></header>
  <div className="circuitUploads">
   {(['base','developed'] as const).map(side=><label className="circuitUpload" key={side}><span><Upload size={17}/>{side==='base'?'Base drawing':'Developed drawing'}</span><input type="file" accept="application/pdf,.pdf" disabled={busy} aria-label={`${side==='base'?'Base':'Developed'} drawing PDF`} onChange={e=>(side==='base'?setBase:setDeveloped)(e.target.files?.[0]||null)}/><small>{(side==='base'?base:developed)?.name||'Choose a PDF · up to 75 MB / 200 pages'}</small></label>)}
   <button className="btn primary circuitRun" disabled={!base||!developed||busy} onClick={()=>void run()}>{busy?'Comparing…':'Compare drawings'}</button>
  </div>
  {busy&&<div className="circuitProgress" role="status"><span className="circuitSpinner"/><b>{job?.phase||'Uploading drawings'}</b>{!!job?.total&&<span>{job.current} / {job.total}</span>}<span>The original drawings remain unchanged.</span></div>}
  {error&&<p className="circuitError" role="alert">{error}</p>}
  {!result&&!busy&&<div className="circuitEmpty"><CircuitBoard size={40}/><h2>Choose two electrical drawings</h2><p>Match corresponding sheets, inspect visual changes and compare component, terminal, cable and BOM details.</p><p>Scanned pages use visual comparison. Connections that cannot be established from PDF text require engineer review.</p></div>}
  {result&&<>
   {outdated&&<div className="circuitAccuracyNotice"><b>Earlier comparison method</b><p>Recompare the stored originals to remove export noise and build the object graph. Previous reviews remain in the earlier session.</p><button className="btn primary" disabled={busy} onClick={()=>void recompare()}>Recompare original drawings</button></div>}
   <div className="circuitMetrics" aria-label="Comparison summary">{[['added','Added'],['removed','Removed'],['modified','Modified'],['pendingReview','Awaiting review']].map(([value,label])=><button className={value} key={value} aria-pressed={value==='pendingReview'?reviewFilter==='pending':status===value} onClick={()=>{if(value==='pendingReview')setReviewFilter(reviewFilter==='pending'?'all':'pending');else setStatus(status===value?'all':value)}}><strong>{result.summary[value]}</strong><span>{label}</span></button>)}<div><strong>{result.summary.matchedPages} / {Math.max(result.basePages.length,result.developedPages.length)}</strong><span>Sheets matched · {result.elapsedSeconds}s</span></div></div>
   <div className="circuitResultHeader"><div><b>{result.baseName}</b><span> → </span><b>{result.developedName}</b><p>{result.summary.changedPages} changed page pairs{result.summary.reorderedPages?` · ${result.summary.reorderedPages} reordered pages`:''}. {result.summary.uncertainFindings||0} uncertain extraction / geometry checks are listed separately.</p></div><details><summary>Comparison method & limits</summary><p>Decode embedded font maps ? align drawing frames ? compare labels and table fields ? inspect vector nodes and paths.</p><p>{result.summary.suppressedRenderArtifacts||0} text-layer / rendering artifacts suppressed. Plain crossings are not joined; candidate terminal bindings need review.</p>{result.limitations.map(text=><p key={text}>{text}</p>)}</details></div>
   <div className="circuitAccuracyControls"><label><input type="checkbox" checked={showUncertain} onChange={e=>setShowUncertain(e.target.checked)}/>Show uncertain extraction and geometry checks ({result.summary.uncertainFindings||0})</label>{!outdated&&<button className="btn" disabled={busy} onClick={()=>void recompare()}>Recompare original drawings</button>}</div>
   <div className="circuitViewerLayout">
    <aside className="circuitSheetList" aria-label="Drawing sheets"><h2>Drawing sheets</h2><label>Find sheet<input value={pageSearch} onChange={e=>setPageSearch(e.target.value)} placeholder="Sheet or drawing title"/></label><label>Page status<select value={pageFilter} onChange={e=>setPageFilter(e.target.value)}><option value="all">All sheets</option><option value="changed">Changed sheets</option><option value="unchanged">Unchanged sheets</option><option value="added">Added sheets</option><option value="removed">Removed sheets</option></select></label>
     <div className="circuitPageButtons">{pairs.map(p=><button key={p.id} aria-pressed={pair?.id===p.id} onClick={()=>choosePair(p.id)}><span>Base {p.base||'—'} ↔ Developed {p.developed||'—'}<i className={`circuitBadge ${p.status}`}>{p.status}</i></span><small>{p.title}</small><small>{p.changeCount} changes{(p as any).uncertainCount?` | ${(p as any).uncertainCount} uncertain checks`:''}{p.matchReview?' · verify page match':''}{p.reordered?' · reordered':''}</small></button>)}{!pairs.length&&<p>No matching sheets.</p>}</div>
    </aside>
    <div className="circuitDrawingArea">
     <div className="circuitViewerTools"><div><button className="btn" aria-label="Zoom out drawings" onClick={()=>setZoom(z=>Math.max(50,(z||100)-25))}><ZoomOut size={16}/></button><select aria-label="Drawing zoom" value={zoom} onChange={e=>setZoom(Number(e.target.value))}><option value={0}>Fit width</option>{[50,75,100,125,150,200,300].map(n=><option key={n} value={n}>{n}%</option>)}</select><button className="btn" aria-label="Zoom in drawings" onClick={()=>setZoom(z=>Math.min(300,(z||100)+25))}><ZoomIn size={16}/></button><button className="btn" onClick={()=>setZoom(0)}><Maximize2 size={15}/>Fit</button></div><label><input type="checkbox" checked={linked} onChange={e=>setLinked(e.target.checked)}/><Link2 size={14}/>Linked scroll</label><label><input type="checkbox" checked={highlights} onChange={e=>setHighlights(e.target.checked)}/>Highlights</label><label><input type="checkbox" checked={overlay} onChange={e=>setOverlay(e.target.checked)}/>Pixel overlay</label></div>
     {pair&&<>{markup.toolbar}<p className="circuitPageMatch">{pair.id} · Match: {pair.match}{pair.base&&pair.developed?` · text similarity ${Math.round(pair.similarity*100)}%`:''}{pair.matchReview&&<span><AlertTriangle size={14}/>Verify corresponding page identity</span>}</p>
      <div className="circuitSplit">
       {(['base','developed'] as const).map((side,index)=>{
        const number=pair[side];const page=number?(side==='base'?result.basePages:result.developedPages)[number-1]:undefined;
        const shown=pairChanges.filter(c=>side==='base'?c.before:c.after);
        return <section className={`circuitPane ${side}`} key={side} aria-label={`${side} drawing preview`}><header><b>{side==='base'?'Base':'Developed'} · {number?`Page ${number}`:'Page absent'}</b>{number&&<a href={`/api/circuit-compare/${session}/original/${side}`} target="_blank" rel="noreferrer">Original PDF ↗</a>}</header>
         <div className="circuitViewport" ref={scroll.refs[index]} onScroll={linked?scroll.onScroll(index):undefined} style={{height}}>
          {page?<div className="circuitCanvas" style={{width:zoom?`${Math.round(page.width*zoom/100)}px`:'100%'}}>
           <img draggable={false} src={`/api/circuit-compare/${session}/image/${overlay&&side==='base'&&pair.overlay?pair.overlay:page.image}`} alt={`${side==='base'?'Base':'Developed'} drawing, page ${page.number}`} loading="lazy"/>
           {highlights&&shown.filter(c=>c.assessment!=='uncertain'||showUncertain).filter(c=>{const b=(side==='base'?c.before:c.after)?.bbox;return !outdated||!b||(b[2]-b[0])*(b[3]-b[1])<.12}).map(c=>{const ref=side==='base'?c.before:c.after;if(!ref)return null;const [x0,y0,x1,y1]=ref.bbox;return <button key={c.id} aria-label={`${c.id} ${c.status}: ${ref.text}`} title={`${c.id} · ${c.category} · ${c.status}\n${ref.text}`} className={`circuitMark ${c.status} ${c.assessment==='uncertain'?'uncertain':''} ${selected?.id===c.id?'selected':''} ${c.review==='dismissed'?'dismissed':''}`} style={{left:`${x0*100}%`,top:`${y0*100}%`,width:`${(x1-x0)*100}%`,height:`${(y1-y0)*100}%`}} onClick={()=>selectChange(c)}/>})}
           {objectOverlay[index]?.paths&&<svg className="circuitObjectOverlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label={`${side} selected source path`}>{objectOverlay[index]?.paths?.map((points,i)=><polyline key={i} points={points.map(p=>`${p[0]*1000},${p[1]*1000}`).join(' ')} fill="none" stroke="#00a7d1" strokeWidth="3" vectorEffect="non-scaling-stroke"/>)}</svg>}
           {objectOverlay[index]?.bbox&&(()=>{const b=objectOverlay[index]!.bbox!;return <div className="circuitObjectMark" title={objectOverlay[index]?.label} style={{left:`${b[0]*100}%`,top:`${b[1]*100}%`,width:`${(b[2]-b[0])*100}%`,height:`${(b[3]-b[1])*100}%`}}/>})()}{markup.layer(side)}
          </div>:<div className="circuitAbsent">This page is {side==='base'?'new in the developed drawing':'removed from the developed drawing'}.</div>}
         </div>{page?.notices.map(text=><p className="circuitExtractionNotice" key={text}><AlertTriangle size={14}/>{text}</p>)}
        </section>;
       })}
      </div><ResizeHandle height={height} onChange={setHeight} label="drawing previews"/>
      <p className="circuitLegend"><span className="removed">Red: removed</span><span className="added">Green: added</span><span className="modified">Amber: modified</span><span>Dashed outlines: uncertain, needs review</span><span>Click a highlight or change row to inspect both sources.</span></p>
     </>}
    </div>
   </div>
   {pair&&<CircuitObjectInspector session={session} pair={pair} enabled={!outdated} onInspect={setObjectOverlay}/>}
   {selected&&<section className="circuitChangeDetail" aria-label="Selected change"><header><div><span className={`circuitBadge ${selected.assessment==='uncertain'?'uncertain':selected.status}`}>{selected.assessment==='uncertain'?'Uncertain check':selected.status}</span><h2>{selected.id} · {selected.category}</h2><p>{selected.label} · {selected.evidenceKind==='visual'?'Visual difference — verify the drawing':selected.extraction}</p></div><button className="btn" onClick={()=>setChangeId('')}>Close detail</button></header><div className="circuitValues">{(['before','after'] as const).map(side=><div key={side}><b>{side==='before'?'Base':'Developed'}{selected[side]?` · page ${selected[side]?.page}`:''}</b><p>{selected[side]?.text||'Absent'}</p>{selected[side]&&<small>Source region: {selected[side]?.bbox.map(n=>n.toFixed(3)).join(', ')}</small>}</div>)}</div>
    <p><b>Possible impact: </b>{selected.possibleImpact}</p><p><b>Verify: </b>{selected.verification}</p><div className="circuitReview"><label>Engineer review<select aria-label="Engineer review" value={review} onChange={e=>setReview(e.target.value)}><option value="pending">Pending review</option><option value="confirmed">Difference confirmed</option><option value="dismissed">Dismiss finding</option></select></label><label>Review note<textarea value={note} maxLength={2000} onChange={e=>setNote(e.target.value)} placeholder="What was verified or why this finding was dismissed"/></label><button className="btn primary" disabled={saving} onClick={()=>void saveReview()}><CheckCircle2 size={15}/>{saving?'Saving…':'Save review'}</button></div><p role="status">{reviewNotice}</p><small>Confirming a difference records this review; it does not approve the electrical design.</small>
   </section>}
   <section className="circuitChangeRegister" aria-label="Change register"><header><h2>Change register</h2><p>{filtered.length} of {result.changes.length} changes · select a row to locate its sources</p></header><div className="circuitFilters"><label>Category<select aria-label="Change category" value={category} onChange={e=>setCategory(e.target.value)}><option value="all">All categories</option>{categories.map(c=><option key={c}>{c}</option>)}</select></label><label>Change<select value={status} onChange={e=>setStatus(e.target.value)}><option value="all">All changes</option>{['added','removed','modified'].map(c=><option key={c}>{c}</option>)}</select></label><label>Review<select value={reviewFilter} onChange={e=>setReviewFilter(e.target.value)}><option value="all">All reviews</option>{['pending','confirmed','dismissed'].map(c=><option key={c}>{c}</option>)}</select></label><label><span><Search size={14}/>Find change</span><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Reference, material number or text"/></label><button className="btn" onClick={()=>{setCategory('all');setStatus('all');setReviewFilter('all');setSearch('')}}>Clear</button></div>
    <div className="circuitTableScroll"><table><thead><tr><th>Change / source</th><th>Category</th><th>Base value</th><th>Developed value</th><th>Review</th></tr></thead><tbody>{filtered.slice(0,limit).map(c=><tr key={c.id} className={selected?.id===c.id?'selected':''}><td><button className="circuitRowButton" onClick={()=>selectChange(c)}>{c.id}<span className={`circuitBadge ${c.assessment==='uncertain'?'uncertain':c.status}`}>{c.assessment==='uncertain'?'Check':c.status}</span><small>Pages {c.before?.page||'—'} → {c.after?.page||'—'}</small></button></td><td>{c.category}<small>{c.label}</small></td><td>{c.before?.text||'—'}</td><td>{c.after?.text||'—'}</td><td>{c.assessment==='uncertain'?'Uncertain check':c.review}<small>{c.issue||''} {c.evidenceKind==='visual'?'Visual only':c.extraction}</small></td></tr>)}</tbody></table></div>{!filtered.length&&<p className="circuitNoChanges">No changes match these filters.</p>}{filtered.length>limit&&<button className="btn" onClick={()=>setLimit(n=>n+100)}>Show more changes ({limit} / {filtered.length})</button>}
   </section>
   <section className="circuitChopper"><header><div><h2><Sparkles size={20}/>Chopper · Engineering review</h2><p>Source-based findings and checks for the detected changes.</p></div><button className="btn" disabled={explaining||selected?.assessment==='uncertain'} onClick={()=>void explain()}>{explaining?'Chopper is explaining…':selected?`Explain ${selected.id}`:'Explain first 20 changes'}</button></header>
    {findings&&<><p>{findings.summary}</p><div className="circuitInsightGrid">{findings.areas.map(area=><details key={area.category}><summary>{area.category}<b>{area.count}</b></summary><p><b>Possible impact: </b>{area.possibleImpact}</p><p><b>Check: </b>{area.verify}</p><div className="circuitSourceLinks">{area.sourceIds.map(id=><button key={id} onClick={()=>{const c=result.changes.find(v=>v.id===id);if(c)selectChange(c)}}>{id}</button>)}</div></details>)}</div></>}
    {prose&&<div className="circuitProse"><p role="status">{prose.notice}</p>{prose.paragraphs.map((p,i)=><div key={i}><p>{p.text}</p>{p.sourceIds.map(id=><button className="circuitSourceButton" key={id} onClick={()=>{const c=result.changes.find(v=>v.id===id);if(c)selectChange(c)}}>{id}</button>)}</div>)}<small>Explanation scope: {prose.scope.join(', ')||'No model sources supplied'}</small></div>}
   </section>
  </>}
 </section>;
}
