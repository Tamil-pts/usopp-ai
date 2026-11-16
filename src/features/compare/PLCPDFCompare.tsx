import {ComparisonCoverFields,ComparisonExportDialog,type ComparisonDetails} from './ComparisonExportDialog';
import {memo,useCallback,useEffect,useMemo,useRef,useState,type RefObject} from 'react';
import {ChevronDown,ChevronUp,Download,FileDiff,LoaderCircle,Upload,ZoomIn,ZoomOut} from 'lucide-react';
import {userStorage} from '../../shared/userStorage';
import './plc-pdf-compare.css';

const API='/api/local/compare/plc-pdf';
const SAVED='usopp_plc_pdf_comparison';
type Source={id:string;name:string;sha256:string;size:number};
type Status='added'|'removed'|'modified'|'unchanged'|'unresolved';
type Segment={page:number;bbox:number[]};
type Row={id:number;status:Status;block:string;unit:'network'|'block';base:string;compared:string;base_network:number|null;compared_network:number|null;base_ref:string;compared_ref:string;base_segments:Segment[];compared_segments:Segment[];text_changed:boolean;base_references?:{page:number;text:string}[];compared_references?:{page:number;text:string}[];pixels:{changed_pixels:number;total_pixels:number;threshold:number}|null};
type Result={id:string;base:Source;compared:Source;rows:Row[];total:number;summary:Record<Status,number>;notices:string[];pdf:{comparison_version?:number;comparison_fields?:Record<string,boolean>;pixel_compare:boolean;blocks:{name:string;base_address:string;compared_address:string}[]}};
type PdfMetadata={project_name:string;project_id:string;department:string;base:string;description:string;approved_by:string;objective_scope:string;developed:string;reviewed_by:string};
const metadataKeys={projectName:'project_name',projectId:'project_id',department:'department',base:'base',developed:'developed',description:'description',objectiveScope:'objective_scope',reviewedBy:'reviewed_by',approvedBy:'approved_by'} as const;
const filters=['all','differences','modified','added','removed','unchanged','unresolved'];
const statusName=(status:string)=>status==='unresolved'?'Needs review':status[0].toUpperCase()+status.slice(1);
const matchesStatus=(row:Row,status:string)=>status==='all'||status==='differences'&&row.status!=='unchanged'||status===row.status;
const label=(row:Row)=>row.unit==='network'?`Network ${row.base_network??'—'} → ${row.compared_network??'—'}`:'Block information';

async function json<T>(url:string,init?:RequestInit):Promise<T>{
 const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...init}),value=await response.json();
 if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Could not complete PLC PDF comparison.');
 return value;
}

function evidence(row:Row,highlight:boolean){
 if(row.status==='unresolved')return 'The block or network identity is ambiguous. Review the source before accepting this comparison.';
 if(row.status==='added')return 'Added in the compared PDF. No corresponding network exists in the base PDF.';
 if(row.status==='removed')return 'Removed from the compared PDF. No corresponding network exists in the compared PDF.';
 if(row.pixels)return `${row.text_changed?'Text changed.':'Extracted text unchanged.'} ${row.pixels.changed_pixels.toLocaleString()} rendered pixels differ.${row.pixels.changed_pixels?' Network position is aligned before highlighting; one-pixel raster tolerance applies.':''}`;
 return `${row.text_changed?'Text changed.':'Extracted text unchanged.'} Pixel comparison was not performed.${highlight&&row.status==='modified'?' The whole changed network is highlighted; individual wire changes have not been located.':''}`;
}

/** All rows stay in the scroll document; off-screen raster images are unloaded. */
function changedLines(source:string,other:string){const counts=new Map<string,number>();other.split('\n').map(v=>v.trim()).filter(Boolean).forEach(v=>counts.set(v,(counts.get(v)||0)+1));return source.split('\n').map(v=>v.trim()).filter(Boolean).filter(v=>{const n=counts.get(v)||0;if(n){counts.set(v,n-1);return false}return true});}
const NetworkSection=memo(function NetworkSection({row,result,highlight,overlay,viewport,register,onError}:{row:Row;result:Result;highlight:boolean;overlay:boolean;viewport:RefObject<HTMLDivElement|null>;register:(id:number,node:HTMLElement|null)=>void;onError:()=>void}){
 const section=useRef<HTMLElement>(null),pictures=useRef<HTMLDivElement>(null),height=useRef(280);
 const [visible,setVisible]=useState(false),[text,setText]=useState(false);
 useEffect(()=>{
  const node=section.current;if(!node)return;
  const observer=new IntersectionObserver(entries=>setVisible(entries[0].isIntersecting),{root:viewport.current,rootMargin:'1000px 0px'});
  observer.observe(node);return()=>observer.disconnect();
 },[viewport]);
 useEffect(()=>{
  const node=pictures.current;if(!visible||!node)return;
  const observer=new ResizeObserver(()=>{if(node.offsetHeight>0)height.current=node.offsetHeight;});
  observer.observe(node);return()=>observer.disconnect();
 },[visible]);
 return <section className={`plcPDFSection ${row.status}${highlight?' highlighted':''}`} data-row-id={row.id} data-status={row.status} aria-label={`${row.block} ${label(row)}`} ref={node=>{section.current=node;register(row.id,node);}}>
  <header className="plcPDFSectionHeading"><div><strong>{row.block}</strong><span>{label(row)}</span></div><span className={`plcPDFBadge ${row.status}`}>{statusName(row.status)}</span></header>
  <p className="plcPDFEvidence">{evidence(row,highlight)} Both sides use the same drawing scale.</p>
  {row.text_changed&&<details className="plcPDFChangeSummary"><summary>Changed content / source text</summary><div><section><b>Removed / Before</b>{changedLines(row.base,row.compared).map((line,index)=><code key={index}>{line}</code>)}</section><section><b>Added / After</b>{changedLines(row.compared,row.base).map((line,index)=><code key={index}>{line}</code>)}</section></div></details>}
  <div className="plcPDFPanes">{(['base','compared'] as const).map(side=><header key={side}><b>{side==='base'?'Before · Base':'After · Compared'}</b><small>{row[`${side}_ref`]||'Absent on this side'}</small></header>)}</div>
  {visible?<div className="plcPDFPairImages" ref={pictures}>{(['base','compared'] as const).map(side=>{
   const present=!!row[`${side}_segments`].length,params=new URLSearchParams();
   if(overlay&&side==='compared'&&row.pixels)params.set('overlay','true');
   else if(highlight&&row.status!=='unchanged')params.set('highlight','true');
   const source=`${API}/results/${result.id}/networks/${row.id}/${side}.png${params.size?'?'+params:''}`;
   return <div key={side} className={`plcPDFPicture ${side}${present?'':' absent'}`}>
    {present?<img src={source} alt={`${side} ${row.block} ${label(row)}`} decoding="async" onError={onError}/>:<p><b>{row.status==='added'?'Added network':row.status==='removed'?'Removed network':'No network'}</b><br/>This section is absent on this side.</p>}
   </div>;
  })}</div>:<div className="plcPDFPreviewPlaceholder" style={{height:height.current}} aria-hidden="true">Network preview loads as you scroll</div>}
  {(row.base_references?.length||row.compared_references?.length)?<details className="plcPDFText"><summary>Symbol references / separate from Ladder drawing</summary><div>{(['base','compared'] as const).map(side=><pre key={side}>{row[`${side}_references`]?.map(r=>r.text).join('\n')||'No printed symbol table'}</pre>)}</div></details>:null}
  <details className="plcPDFText" onToggle={event=>setText(event.currentTarget.open)}><summary>Extracted network text · Before and After</summary>{text&&<div>{(['base','compared'] as const).map(side=><pre key={side}>{row[side]||'(Network absent)'}</pre>)}</div>}</details>
 </section>;
});

export default function PLCPDFCompare(){
 const [exportProgress,setExportProgress]=useState({done:0,total:0,phase:'starting'}),[exportSeconds,setExportSeconds]=useState(0);
 const [files,setFiles]=useState<Partial<Record<'base'|'compared',Source>>>({}),[uploading,setUploading]=useState(''),[pixels,setPixels]=useState(true),[ignorePages,setIgnorePages]=useState(true),[result,setResult]=useState<Result|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[download,setDownload]=useState(''),[pendingExport,setPendingExport]=useState<string|null>(null),[exportScope,setExportScope]=useState('differences'),[pdfMetadata,setPdfMetadata]=useState<PdfMetadata>({project_name:'',project_id:'',department:'',base:'',description:'',approved_by:'',objective_scope:'',developed:'',reviewed_by:''});
 const [fields,setFields]=useState<Record<string,boolean>>({author:false,created:false,modified:false,comments:false,references:false});
 const [status,setStatus]=useState('all'),[treeStatus,setTreeStatus]=useState('all'),[block,setBlock]=useState(''),[search,setSearch]=useState(''),[selected,setSelected]=useState(0),[zoom,setZoom]=useState(100),[overlay,setOverlay]=useState(false),[highlight,setHighlight]=useState(true);
 const stream=useRef<HTMLDivElement>(null),sections=useRef(new Map<number,HTMLElement>()),pendingJump=useRef<number|null>(null),scrollFrame=useRef<number|null>(null),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;if(scrollFrame.current!==null)cancelAnimationFrame(scrollFrame.current);};},[]);
 async function load(id:string){
  const first=await json<Result>(`${API}/results/${id}?status=all&limit=200`);
  if(first.pdf.comparison_version!==5){userStorage.removeItem(SAVED);setFiles({base:first.base,compared:first.compared});setResult(null);setPendingExport(null);setError('This saved comparison predates the shared-scale Ladder and reference-table comparison. The source PDFs are retained; choose Compare PLC PDFs again to recalculate block/network matches and highlights.');return;}
  const rows=[...first.rows];
  for(let offset=200;offset<first.total;offset+=200){const page=await json<Result>(`${API}/results/${id}?status=all&limit=200&offset=${offset}`);rows.push(...page.rows);}
  if(mounted.current){setResult({...first,rows});setFiles({base:first.base,compared:first.compared});setSelected(rows[0]?.id||0);setBlock('');setSearch('');setOverlay(false);setStatus('all');setTreeStatus('all');setZoom(100);if(first.pdf.comparison_fields)setFields(first.pdf.comparison_fields);}
 }
 useEffect(()=>{const id=userStorage.getItem(SAVED);if(id){setBusy(true);void load(id).catch(problem=>{if(mounted.current)setError(problem.message);}).finally(()=>{if(mounted.current)setBusy(false);});}},[]);
 async function upload(side:'base'|'compared',file:File){
  if(file.size>25*1024**2){setError('Choose a PDF up to 25 MB.');return;}
  setUploading(side);setError('');setResult(null);userStorage.removeItem(SAVED);setFiles(current=>({...current,[side]:undefined}));
  const data=new FormData();data.append('file',file);
  try{const value=await json<Source>(API+'/uploads',{method:'POST',body:data});setFiles(current=>({...current,[side]:value}));}
  catch(problem){setError((problem as Error).message);}finally{setUploading('');}
 }
 async function run(){
  if(!files.base||!files.compared)return;setBusy(true);setError('');setResult(null);userStorage.removeItem(SAVED);
  try{const response=await json<Result>(API+'/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base:{id:files.base.id},compared:{id:files.compared.id},pixel_compare:pixels,ignore_page_numbers:ignorePages,...Object.fromEntries(Object.entries(fields).map(([name,value])=>['compare_'+name,value]))})});await load(response.id);userStorage.setItem(SAVED,response.id);}
  catch(problem){setError((problem as Error).message);}finally{setBusy(false);}
 }
 async function exportFile(file:string,scope=exportScope,metadata=pdfMetadata){
  if(!result)return;setDownload(file);setError('');
  const token=Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
  const start=Date.now();let polling=false,active=true;setExportProgress({done:0,total:0,phase:'starting'});setExportSeconds(0);
  const timer=setInterval(()=>{setExportSeconds(Math.floor((Date.now()-start)/1000));if(!file.startsWith('report.')||polling)return;polling=true;void fetch(`${API}/results/${result.id}/export-progress/${token}`,{cache:'no-store'}).then(async response=>{if(response.ok){const value=await response.json();if(active)setExportProgress(value)}}).catch(()=>{}).finally(()=>{polling=false})},1500);
  try{const query=new URLSearchParams({status:scope});if(file.startsWith('report.'))query.set('progress_id',token);if(file.startsWith('report.'))Object.entries(metadata).forEach(([key,value])=>query.set(key,value));const response=await fetch(`${API}/results/${result.id}/${file}?${query.toString()}`,{credentials:'same-origin'});if(!response.ok){const body=await response.json();throw Error(body.detail||'Could not export comparison.');}const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=`PLC_MatchView_${result.id.slice(0,8)}_${scope}_${file}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setPendingExport(null);}
  catch(problem){setError((problem as Error).message);}finally{active=false;clearInterval(timer);setDownload('');}
 }
 const rows=useMemo(()=>(result?.rows||[]).filter(row=>matchesStatus(row,status)),[result,status]);
 const treeRows=useMemo(()=>(result?.rows||[]).filter(row=>(!block||row.block===block)&&matchesStatus(row,treeStatus)&&(!search||`${row.block} ${row.base_network??''} ${row.compared_network??''} ${row.base} ${row.compared}`.toLowerCase().includes(search.toLowerCase()))),[result,block,treeStatus,search]);
 const currentIndex=rows.findIndex(row=>row.id===selected),previous=rows.slice(0,Math.max(0,currentIndex)).reverse().find(row=>row.status!=='unchanged'),next=rows.slice(currentIndex+1).find(row=>row.status!=='unchanged');
 const register=useCallback((id:number,node:HTMLElement|null)=>{if(node)sections.current.set(id,node);else sections.current.delete(id);},[]);
 const imageError=useCallback(()=>setError('A network image could not load. Reopen the comparison or check whether a source snapshot changed.'),[]);
 function scrollTo(id:number){const node=sections.current.get(id);if(node&&stream.current){stream.current.scrollTo({top:node.offsetTop,left:stream.current.scrollLeft});setSelected(id);}}
 function jump(id:number){if(rows.some(row=>row.id===id))scrollTo(id);else{pendingJump.current=id;setStatus('all');}}
 useEffect(()=>{stream.current?.scrollTo(0,0);if(pendingJump.current!==null){scrollTo(pendingJump.current);pendingJump.current=null;}else setSelected(rows[0]?.id||0);},[rows]);
 function trackScroll(){
  if(scrollFrame.current!==null)return;
  scrollFrame.current=requestAnimationFrame(()=>{scrollFrame.current=null;const top=(stream.current?.scrollTop||0)+30;const row=rows.find(row=>{const node=sections.current.get(row.id);return node&&node.offsetTop+node.offsetHeight>top;});if(row)setSelected(row.id);});
 }
 return <section className="plcPDF" aria-label="PLC PDF MatchView">
  <header><div className="eyebrow">PLC MATCHVIEW</div><h2>Compare printed PLC logic</h2><p>Compare two program PDFs by block and network. Scroll all networks together and review highlighted changes with their source-page references.</p></header>
  <div className="plcPDFInputs">{(['base','compared'] as const).map(side=><fieldset key={side} disabled={busy||!!uploading}><legend>{side==='base'?'Base / reference':'Developed / compare'}</legend><label className="plcPDFUpload"><Upload size={20}/><span>{files[side]?.name||'Choose PLC program PDF'}<small>{files[side]?`${(files[side]!.size/1024).toFixed(1)} KB`:'PDF · up to 25 MB'}</small></span><input type="file" accept=".pdf" aria-label={`${side==='base'?'Base':'Compared'} PLC PDF`} onChange={event=>{const file=event.target.files?.[0];event.target.value='';if(file)void upload(side,file);}}/></label>{uploading===side&&<span role="status">Reading PDF…</span>}</fieldset>)}</div>
  <div className="plcPDFOptions"><label><input type="checkbox" checked={pixels} disabled={busy} onChange={e=>setPixels(e.target.checked)}/>Compare pixels (wiring and symbols)</label><label><input type="checkbox" checked={ignorePages} disabled={busy} onChange={e=>setIgnorePages(e.target.checked)}/>Ignore printed page numbers</label><details className="plcPDFAdvanced"><summary>Optional details</summary><p>Include these only when they are part of this review. Ladder instructions and wiring are always retained.</p>{Object.entries({references:'Symbol reference tables',comments:'Comments',author:'Author',created:'Created date',modified:'Modified date'}).map(([key,name])=><label key={key}><input type="checkbox" checked={!!fields[key]} disabled={busy} onChange={e=>setFields(v=>({...v,[key]:e.target.checked}))}/>{name}</label>)}</details><button className="btn primary" type="button" disabled={busy||!!uploading||!files.base||!files.compared} onClick={()=>void run()}>{busy?<LoaderCircle size={16} className="spin"/>:<FileDiff size={16}/>}Compare PLC PDFs</button></div>
  {busy&&<p role="status">Reading blocks and networks{pixels?' and comparing their rendered pixels':''}. Large programs can take a few minutes.</p>}{error&&<p role="alert" className="wh-error">{error}</p>}
  {result&&<><div className="plcPDFSummary">{(['modified','added','removed','unchanged','unresolved'] as Status[]).map(value=><button type="button" key={value} aria-pressed={status===value} className={`plcPDFCount ${value}`} onClick={()=>setStatus(value)}><b>{result.summary[value]}</b>{statusName(value)}</button>)}</div>
   <div className="plcPDFOptions"><span>Export comparison</span>{[['report.pdf','PDF'],['report.docx','Word'],['report.html','HTML'],['export.csv','CSV'],['highlighted-base.pdf','Marked Base PDF'],['highlighted-compared.pdf','Marked Compared PDF']].map(([file,name])=><button className="btn" type="button" key={file} disabled={!!download} onClick={()=>{setExportScope('differences');if(file.startsWith('report.'))setPdfMetadata(value=>({...value,base:result.base.name,developed:result.compared.name}));setPendingExport(file);}}>{download===file?<LoaderCircle size={14} className="spin"/>:<Download size={14}/>} {name}</button>)}</div>
   <details className="plcPDFScope"><summary>Compared content and source snapshots</summary>{result.notices.map((note,index)=><p key={index}>{note}</p>)}{(['base','compared'] as const).map(side=><p key={side}>{side}: {result[side].name}<br/><code>SHA256 {result[side].sha256}</code></p>)}</details>
   <div className="plcPDFReview"><aside aria-label="PLC blocks and networks"><b>Jump to a network</b><label>Block<select aria-label="PLC PDF block" value={block} onChange={e=>setBlock(e.target.value)}><option value="">All blocks</option>{Array.from(new Set(result.pdf.blocks.map(item=>item.name))).map(name=><option key={name}>{name}</option>)}</select></label><label>Find network or operand<input aria-label="Find PLC network or operand" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Network, VW4008…"/></label><label>Tree: show<select aria-label="PLC PDF tree status" value={treeStatus} onChange={e=>setTreeStatus(e.target.value)}>{filters.map(value=><option value={value} key={value}>{statusName(value)}</option>)}</select></label><small>Filters this list only. Selecting a network scrolls the workspace to it.</small><small>{treeRows.length} sections in the list</small><div className="plcPDFNetworkList">{treeRows.map(item=><button type="button" key={item.id} data-status={item.status} className={selected===item.id?'selected':''} aria-current={selected===item.id?'true':undefined} onClick={()=>jump(item.id)}><b>{item.block}</b><span>{label(item)}</span><small className={item.status}>{statusName(item.status)}</small></button>)}{!treeRows.length&&<p>No networks match the list filters.</p>}</div></aside>
    <div className="plcPDFDetail"><div className="plcPDFToolbar"><label>Workspace: show<select aria-label="PLC PDF workspace status" value={status} onChange={e=>setStatus(e.target.value)}>{filters.map(value=><option value={value} key={value}>{statusName(value)}</option>)}</select></label><button type="button" className="btn" aria-label="Previous PLC change" disabled={!previous} onClick={()=>previous&&jump(previous.id)}><ChevronUp size={16}/></button><button type="button" className="btn" aria-label="Next PLC change" disabled={!next} onClick={()=>next&&jump(next.id)}><ChevronDown size={16}/></button><button type="button" className="btn" aria-label="Zoom networks out" disabled={zoom<=100} onClick={()=>setZoom(z=>Math.max(100,z-25))}><ZoomOut size={16}/></button><button type="button" className="btn" onClick={()=>{setZoom(100);stream.current?.scrollTo({left:0});}}>Fit width</button><button type="button" className="btn" aria-label="Zoom networks in" onClick={()=>setZoom(z=>Math.min(250,z+25))}><ZoomIn size={16}/></button><small>{zoom}%</small><label><input type="checkbox" checked={highlight} onChange={e=>setHighlight(e.target.checked)}/>Highlight changes</label><label><input type="checkbox" checked={overlay} disabled={!result.pdf.pixel_compare} onChange={e=>setOverlay(e.target.checked)}/>Pixel overlay</label></div>
     <div className="plcPDFStreamInfo"><strong>{status==='all'?'All networks':statusName(status)} · {rows.length} sections</strong><span>Shared scroll keeps Before and After together. Includes block information.</span><div className="plcPDFLegend" aria-label="Change colours">{(['modified','added','removed','unresolved'] as Status[]).map(value=><span className={value} key={value}>{statusName(value)}</span>)}</div>{overlay&&<small>Red pixel overlay replaces the yellow pixel marks on the compared side.</small>}</div>
     <div className="plcPDFStream" ref={stream} onScroll={trackScroll} tabIndex={0} role="region" aria-label="Continuous PLC network comparison"><div className="plcPDFStreamCanvas" style={{width:`${zoom}%`}}>{rows.map(row=><NetworkSection key={`${result.id}-${row.id}`} row={row} result={result} highlight={highlight} overlay={overlay} viewport={stream} register={register} onError={imageError}/>)}{!rows.length&&<p className="plcPDFEmpty">No networks match this workspace filter. Choose All to restore the full comparison.</p>}</div></div>
    </div>
   </div></>}
  {pendingExport&&result&&<ComparisonExportDialog title="Export PLC comparison" progressText={`${exportProgress.phase==='formatting'?'Writing report pages':exportProgress.phase==='complete'?'Downloading report':exportProgress.total?`Prepared ${exportProgress.done} of ${exportProgress.total} sections`:'Starting export'} / ${exportSeconds}s elapsed`} subtitle="Choose your content and add the details for the report cover." busy={!!download} error={error} onClose={()=>setPendingExport(null)} onSubmit={()=>void exportFile(pendingExport,exportScope)} submitLabel={'Download '+(pendingExport.endsWith('.docx')?'Word':pendingExport.endsWith('.html')?'HTML':pendingExport.endsWith('.csv')?'CSV':'PDF')} hint={pendingExport.startsWith('report.')?'Before and After remain side by side, with changes highlighted and added/removed text identified. Cover details appear before the comparison.':pendingExport.endsWith('.csv')?'CSV includes the selected statuses and Before/After evidence. Cover details are not added to CSV.':'The original PDF is preserved with marks for the selected changes. This source PDF export does not add a report cover.'} options={<><label>Include<select aria-label="Comparison sections to export" value={exportScope} onChange={event=>setExportScope(event.target.value)}><option value="all">All sections ({result.total})</option><option value="differences">Differences only ({result.total-result.summary.unchanged})</option><option value="modified">Modified ({result.summary.modified})</option><option value="added">Added ({result.summary.added})</option><option value="removed">Removed ({result.summary.removed})</option><option value="unresolved">Needs review ({result.summary.unresolved})</option></select></label><small>Differences include modified, added, removed and unresolved sections.</small></>}>{pendingExport.startsWith('report.')?<ComparisonCoverFields disabled={!!download} value={Object.fromEntries(Object.entries(metadataKeys).map(([key,name])=>[key,pdfMetadata[name]])) as ComparisonDetails} onChange={(key,text)=>setPdfMetadata(previous=>({...previous,[metadataKeys[key]]:text}))}/>:<section><h3>Compared sources</h3><p>Base: {result.base.name}</p><p>Compared: {result.compared.name}</p><small>Choose the content to include using the export options.</small></section>}</ComparisonExportDialog>}
 </section>;
}
