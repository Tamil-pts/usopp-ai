import {useEffect,useRef,useState} from 'react';
import {ChevronLeft,ChevronRight,Download,LoaderCircle,ZoomIn,ZoomOut} from 'lucide-react';

const API='/api/assist/document-comparisons';
type Status='added'|'removed'|'modified'|'unchanged'|'unresolved';
export type PDFInfo={ignore_page_numbers:boolean;pages:Record<'base'|'compared',{number:number;width:number;height:number}[]>;pairs:{id:number;base:number|null;compared:number|null;change_count:number;counts:Partial<Record<Status,number>>}[];ignored_page_numbers:Record<'base'|'compared',{page:number;text:string}[]>};
type Highlight={row_id:number;status:Status;bbox:number[]};
type Note={id:number;status:Status;base:string;compared:string;base_ref:string;compared_ref:string};
type Detail={id:number;base_highlights:Highlight[];compared_highlights:Highlight[];rows:Note[]};

function included(status:string,actual:Status){return status==='all'||status==='differences'&&actual!=='unchanged'||status===actual;}

export function DocumentPDFExports({id}:{id:string}){
 const [pending,setPending]=useState(''),[error,setError]=useState('');
 async function download(file:string){
  setPending(file);setError('');
  try{const response=await fetch(`${API}/results/${id}/${file}`,{credentials:'same-origin'});if(!response.ok){const value=await response.json();throw Error(value.detail||'Could not export this comparison.');}const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=`pdf-comparison-${id.slice(0,8)}-${file}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(problem){setError((problem as Error).message);}finally{setPending('');}
 }
 return <details className="dc-pdf-exports"><summary className="btn"><Download size={15}/>PDF exports</summary><div className="dc-pdf-export-options"><small>Includes all changes and original source references.</small>{[['report.pdf','Comparison report (PDF)'],['highlighted-base.pdf','Highlighted Base PDF'],['highlighted-compared.pdf','Highlighted Compared PDF'],['report.html','Change notes (HTML)']].map(([file,label])=><button type="button" className="btn" disabled={!!pending} key={file} onClick={()=>void download(file)}>{pending===file?<LoaderCircle size={14} className="spin"/>:<Download size={14}/>} {label}</button>)}{pending&&<span role="status">Preparing download…</span>}{error&&<p role="alert">{error}</p>}</div></details>;
}

export default function DocumentPDFCompare({id,pdf,status,names}:{id:string;pdf:PDFInfo;status:string;names:{base:string;compared:string}}){
 const [pairId,setPairId]=useState(1),[detail,setDetail]=useState<Detail|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[zoom,setZoom]=useState(0),[highlights,setHighlights]=useState(true),[linked,setLinked]=useState(true),[selected,setSelected]=useState<number|null>(null);
 const left=useRef<HTMLDivElement>(null),right=useRef<HTMLDivElement>(null),scrolling=useRef(false);
 const pairs=pdf.pairs.filter(pair=>status==='all'||(status==='differences'?pair.change_count>0:!!pair.counts[status as Status]));
 const pair=pairs.find(pair=>pair.id===pairId)||pairs[0];
 useEffect(()=>{if(pair&&pair.id!==pairId)setPairId(pair.id);},[pair?.id,pairId]);
 useEffect(()=>{
  if(!pair){setDetail(null);return;}const controller=new AbortController();setLoading(true);setError('');setDetail(null);setSelected(null);
  void fetch(`${API}/results/${id}/pdf-pairs/${pair.id}`,{signal:controller.signal,credentials:'same-origin',cache:'no-store'}).then(async response=>{const value=await response.json();if(!response.ok)throw Error(value.detail||'Could not load this page pair.');setDetail(value);}).catch(problem=>{if(problem.name!=='AbortError')setError(problem.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  left.current?.scrollTo(0,0);right.current?.scrollTo(0,0);return()=>controller.abort();
 },[id,pair?.id]);
 function sync(side:'base'|'compared'){
  if(!linked||scrolling.current)return;const a=side==='base'?left.current:right.current,b=side==='base'?right.current:left.current;
  if(!a||!b)return;scrolling.current=true;
  b.scrollTop=a.scrollTop/Math.max(1,a.scrollHeight-a.clientHeight)*Math.max(0,b.scrollHeight-b.clientHeight);
  b.scrollLeft=a.scrollLeft/Math.max(1,a.scrollWidth-a.clientWidth)*Math.max(0,b.scrollWidth-b.clientWidth);
  requestAnimationFrame(()=>{scrolling.current=false;});
 }
 const index=pairs.findIndex(item=>item.id===pair?.id);
 function focusNote(note:Note){setSelected(note.id);for(const pane of [left.current,right.current]){const mark=pane?.querySelector<HTMLElement>(`[data-row="${note.id}"]`);if(pane&&mark){const parent=pane.getBoundingClientRect(),bounds=mark.getBoundingClientRect();pane.scrollTo({top:pane.scrollTop+bounds.top-parent.top-pane.clientHeight*.35,left:Math.max(0,pane.scrollLeft+bounds.left-parent.left-pane.clientWidth*.3),behavior:'smooth'});}}}
 return <section className="dc-pdf-review" aria-label="Original PDF comparison">
  <div className="dc-pdf-toolbar"><label>Page pair<select aria-label="PDF page pair" value={pair?.id||''} onChange={e=>setPairId(Number(e.target.value))}>{pairs.map(pair=><option key={pair.id} value={pair.id}>{pair.base?`Base ${pair.base}`:'No Base page'} ↔ {pair.compared?`Compared ${pair.compared}`:'No Compared page'} · {pair.change_count} changes</option>)}</select></label><button type="button" className="btn" aria-label="Previous PDF page pair" disabled={index<=0} onClick={()=>setPairId(pairs[index-1].id)}><ChevronLeft size={16}/></button><button type="button" className="btn" aria-label="Next PDF page pair" disabled={index<0||index>=pairs.length-1} onClick={()=>setPairId(pairs[index+1].id)}><ChevronRight size={16}/></button><small>{pairs.length} page pairs</small><label>Zoom<select aria-label="PDF zoom" value={zoom} onChange={e=>setZoom(Number(e.target.value))}><option value="0">Fit width</option>{[75,100,125,150,200].map(value=><option key={value} value={value}>{value}%</option>)}</select></label><button type="button" className="btn" aria-label="Zoom PDF out" onClick={()=>setZoom(Math.max(75,(zoom||100)-25))}><ZoomOut size={16}/></button><button type="button" className="btn" aria-label="Zoom PDF in" onClick={()=>setZoom(Math.min(200,(zoom||100)+25))}><ZoomIn size={16}/></button><label><input type="checkbox" checked={linked} onChange={e=>setLinked(e.target.checked)}/>Linked scroll</label><label><input type="checkbox" checked={highlights} onChange={e=>setHighlights(e.target.checked)}/>Text highlights</label></div>
  <div className="dc-pdf-legend"><span className="removed">Removed</span><span className="added">Added</span><span className="modified">Modified words</span><small>Printed page counters {pdf.ignore_page_numbers?'excluded':'included'} · Page pairing follows shared text.</small></div>
  {loading&&<p role="status">Loading text changes…</p>}{error&&<p role="alert" className="wh-error">{error}</p>}
  {pair?<><div className="dc-pdf-panes">{(['base','compared'] as const).map(side=>{
   const number=pair[side],page=number?pdf.pages[side][number-1]:null,marks=detail?.id===pair.id?detail[side+'_highlights' as 'base_highlights'|'compared_highlights']:[];
   return <article className={'dc-pdf-pane '+side} key={side}><header><b>{side==='base'?'Base':'Compared'} · {number?`Page ${number}`:'No paired page'}</b><small>{names[side]}</small></header><div className="dc-pdf-scroll" ref={side==='base'?left:right} onScroll={()=>sync(side)} aria-label={`${side} PDF page`} tabIndex={0}>{page&&number?<div key={`${side}-${number}`} className="dc-pdf-sheet" style={{width:zoom?`${page.width*zoom/100}px`:'100%',aspectRatio:`${page.width}/${page.height}`}}><img alt={`${side==='base'?'Base':'Compared'} PDF page ${number}`} src={`${API}/results/${id}/pdf-pages/${side}/${number}.png`} onLoad={event=>{if(event.currentTarget.parentElement)event.currentTarget.parentElement.dataset.ready='true';}} onError={()=>setError('Could not load the original page. Reload the comparison; the source may have changed.')} draggable={false}/>{highlights&&marks.filter(mark=>included(status,mark.status)).map((mark,index)=><button type="button" key={index} data-row={mark.row_id} className={`dc-pdf-highlight ${mark.status}${mark.row_id===selected?' selected':''}`} title={`Change ${mark.row_id} · ${mark.status}`} aria-label={`Change ${mark.row_id}, ${mark.status}`} style={{left:`${100*mark.bbox[0]/page.width}%`,top:`${100*mark.bbox[1]/page.height}%`,width:`${100*(mark.bbox[2]-mark.bbox[0])/page.width}%`,height:`${100*(mark.bbox[3]-mark.bbox[1])/page.height}%`}} onClick={()=>{setSelected(mark.row_id);document.getElementById(`pdf-note-${id}-${mark.row_id}`)?.scrollIntoView({behavior:'smooth',block:'nearest'});}}/>)}</div>:<p className="dc-empty">This page has no text-matched counterpart. Use the neighbouring pairs to review continued content.</p>}</div></article>;
  })}</div><section className="dc-pdf-notes" aria-label="PDF change notes"><h4>Text changes on these pages</h4><small>Click a note to locate its highlighted words. References show the actual source pages.</small>{(detail?.id===pair.id?detail.rows:[]).filter(row=>included(status,row.status)).map(row=><article id={`pdf-note-${id}-${row.id}`} key={row.id} className={`dc-pdf-note ${row.status}${selected===row.id?' selected':''}`}><button type="button" onClick={()=>focusNote(row)} className="btn">Change {row.id} · {row.status}</button><div className="dc-text-pair"><div><small>Before · {row.base_ref||'No corresponding text'}</small><pre>{row.base||'—'}</pre></div><div><small>After · {row.compared_ref||'No corresponding text'}</small><pre>{row.compared||'—'}</pre></div></div></article>)}{!loading&&!detail?.rows.some(row=>included(status,row.status))&&<p>No changed text matches this filter on these pages.</p>}</section></>:<p className="dc-empty">No PDF pages match this filter. Choose All to review the original pages.</p>}
 </section>;
}
