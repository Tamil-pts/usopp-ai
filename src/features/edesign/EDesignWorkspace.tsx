import {useEffect,useRef,useState,type PointerEvent,type CSSProperties} from 'react';
import {ArrowLeft,Upload,FilePenLine,MousePointer2,Plus,Minus,Pencil,MessageSquare,ZoomIn,ZoomOut,PanelRightClose,PanelRightOpen,Pin,PinOff,Share2,Download,Save,Trash2,RefreshCw,X,Check,Undo2,Redo2,History,SlidersHorizontal} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {userStorage} from '../../shared/userStorage';
import './edesign.css';

type Kind='modify'|'add'|'remove'|'comment';
type Shape='rectangle'|'cloud'|'arrow'|'note';
type Commands={undo:{id:number;label:string}|null;redo:{id:number;label:string}|null};
type Revision={version:number;action:string;actor:string;at:number;origin:string;snapshot:Draft};
type Mark={deleted?:boolean;commands?:Commands;id:string;page:number;kind:Kind;shape:Shape;box:number[];body:string;status:'open'|'resolved';author:string;author_id:number;created:number;updated:number;version:number;reverseX:boolean;reverseY:boolean};
type Draft=Omit<Mark,'id'|'author'|'author_id'|'created'|'updated'>&Partial<Pick<Mark,'id'|'author'|'author_id'>>;
type Review={commands?:Commands;importSummary?:{updated:number;unchanged:number;unmatched:number};id:string;name:string;ownerId:number;owner:string;created:number;pages:{number:number;width:number;height:number}[];access:'owner'|'review'|'view';marks:Mark[];members:{user_id:number;access:'view'|'review'}[];open?:number;resolved?:number};
type Person={id:number;username:string;designation:string};
const kinds:{id:Kind;label:string;Icon:typeof Pencil}[]=[{id:'modify',label:'Modify',Icon:Pencil},{id:'add',label:'Add',Icon:Plus},{id:'remove',label:'Remove',Icon:Minus},{id:'comment',label:'Comment',Icon:MessageSquare}];
const colours:Record<Kind,string>={modify:'#bb8100',add:'#008152',remove:'#d12b45',comment:'#2369b3'};
const linkId=()=>/^#e-design\/(edesign_[a-f0-9]{32})$/.exec(window.location.hash)?.[1]||'';
async function api<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api/e-design'+url,options);let data:any={};try{data=await response.json()}catch{/* preserve HTTP status */}
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`Drawing review request failed (${response.status}).`);
 return data as T;
}
const body=(value:unknown,method='POST'):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
const bound=(n:number)=>Math.max(0,Math.min(1,n));
function cloud(box:number[]){
 const [x0,y0,x1,y1]=box;let path=`M${x0*1000} ${y0*1000}`;
 for(const [ax,ay,bx,by,nx,ny] of [[x0,y0,x1,y0,0,-1],[x1,y0,x1,y1,1,0],[x1,y1,x0,y1,0,1],[x0,y1,x0,y0,-1,0]]){
  const n=Math.max(2,Math.min(18,Math.ceil(Math.hypot(bx-ax,by-ay)/.025)));
  for(let i=0;i<n;i++){const sx=ax+(bx-ax)*i/n,sy=ay+(by-ay)*i/n,ex=ax+(bx-ax)*(i+1)/n,ey=ay+(by-ay)*(i+1)/n,depth=Math.min(.009,Math.hypot(ex-sx,ey-sy)*.5);path+=` Q${((sx+ex)/2+nx*depth)*1000} ${((sy+ey)/2+ny*depth)*1000} ${ex*1000} ${ey*1000}`;}
 }
 return path+' Z';
}

export function EDesignWorkspace({active}:{active:boolean}){
 const {user}=useAccount();
 const [reviews,setReviews]=useState<Review[]>([]),[drawing,setDrawing]=useState<Review|null>(null);
 const [page,setPage]=useState(1),[zoom,setZoom]=useState(0),[tool,setTool]=useState<Kind|'select'>('select'),[shape,setShape]=useState<Shape>('cloud');
 const [comments,setComments]=useState(true),[pinned,setPinned]=useState(()=>userStorage.getItem('usopp_edesign_pin')!=='false');
 const [draft,setDraft]=useState<Draft|null>(null),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [popup,setPopup]=useState(false),[revisions,setRevisions]=useState<Revision[]>([]);
 const edits=useRef<{past:{draft:Draft|null;dirty:boolean}[];future:{draft:Draft|null;dirty:boolean}[]}>({past:[],future:[]});
 const resetEdits=()=>{edits.current={past:[],future:[]}};
 const remember=(value={draft,dirty})=>{edits.current.past.push(structuredClone(value));edits.current.past=edits.current.past.slice(-100);edits.current.future=[]};
 const [scope,setScope]=useState('page'),[filter,setFilter]=useState('all'),[search,setSearch]=useState('');
 const [share,setShare]=useState(false),[people,setPeople]=useState<Person[]>([]),[person,setPerson]=useState(''),[access,setAccess]=useState('review');
 const canvas=useRef<HTMLDivElement>(null),dialog=useRef<HTMLDialogElement>(null),epoch=useRef(0),initialized=useRef(false);
 const drag=useRef<{action:'draw'|'move'|'resize';point:number[];original:Draft;previous:Draft|null;wasDirty:boolean;recorded?:boolean}|null>(null);
 const editable=!!drawing&&drawing.access!=='view';
 const canEdit=(_mark:{author_id?:number})=>editable;
 const discard=()=>!dirty||window.confirm('Discard the unsaved correction changes?');
 const list=async()=>{try{setReviews((await api<{reviews:Review[]}>('')).reviews)}catch(e){setError((e as Error).message)}};
 const load=async(id:string)=>{
  const ticket=++epoch.current;setError('');setBusy(true);
  try{const value=await api<Review>('/'+id);if(ticket!==epoch.current)return;setDrawing(value);resetEdits();setPopup(false);setDraft(null);setDirty(false);setPage(1);setTool('select');userStorage.setItem('usopp_edesign_review',id);history.replaceState(null,'','#e-design/'+id)}
  catch(e){if(ticket===epoch.current)setError((e as Error).message)}finally{if(ticket===epoch.current)setBusy(false)}
 };
 useEffect(()=>{
  if(!active)return;void list();
  if(!initialized.current){initialized.current=true;const id=linkId()||userStorage.getItem('usopp_edesign_review');if(id)void load(id)}
 },[active]);
 useEffect(()=>{const open=()=>{const id=linkId();if(id&&id!==drawing?.id&&discard())void load(id)};window.addEventListener('hashchange',open);return()=>window.removeEventListener('hashchange',open)},[drawing?.id,dirty]);
 useEffect(()=>{const before=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before)},[dirty]);
 useEffect(()=>{if(share){dialog.current?.showModal();void api<{people:Person[]}>('/people').then(v=>setPeople(v.people)).catch(e=>setError(e.message))}else dialog.current?.close()},[share]);
 const upload=async(file:File)=>{
  if(!discard())return;if(file.size>75*1024*1024){setError('Upload a PDF of 75 MB or smaller.');return}
  ++epoch.current;setBusy(true);setError('');const form=new FormData();form.append('file',file);
  try{const value=await api<Review>('',{method:'POST',body:form});setDrawing(value);resetEdits();setPopup(false);setPage(1);setDraft(null);setDirty(false);setTool('select');userStorage.setItem('usopp_edesign_review',value.id);history.replaceState(null,'','#e-design/'+value.id);void list();setNotice(value.marks.length?`${value.marks.length} editable PDF comments imported with available revision history.`:'Drawing uploaded. Choose a correction tool and drag over an area.')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 };
 const choosePage=(n:number)=>{if(n===page||!discard())return;setPage(n);resetEdits();setPopup(false);setDraft(null);setDirty(false);setNotice('')};
 const select=(mark:Mark)=>{if(!discard())return;setPage(mark.page);resetEdits();setPopup(true);setDraft({...mark,box:[...mark.box]});setDirty(false);setComments(true);setTool('select')};
 const newDraft=(kind:Kind,box:number[],markShape=shape):Draft=>{const x0=Math.min(.997,box[0]),y0=Math.min(.997,box[1]);return {page,kind,shape:kind==='comment'?'note':markShape,box:[x0,y0,Math.max(x0+.003,box[2]),Math.max(y0+.003,box[3])],body:'',status:'open',version:0,reverseX:false,reverseY:false}};
 const centreComment=()=>{if(!discard())return;resetEdits();remember({draft:null,dirty:false});setPopup(true);setDraft(newDraft(tool==='select'?'comment':tool,[.35,.35,.55,.5]));setDirty(true);setComments(true);setNotice('Enter a comment, then save the correction.')};
 const point=(e:PointerEvent)=>{const rect=canvas.current!.getBoundingClientRect();return [bound((e.clientX-rect.left)/rect.width),bound((e.clientY-rect.top)/rect.height)]};
 const pointerDown=(e:PointerEvent<SVGSVGElement>)=>{
  if(e.button!==0||!drawing||saving)return;
  const target=e.target as Element,handle=!!target.closest('[data-resize]'),id=target.closest('[data-mark]')?.getAttribute('data-mark');
  if(!editable){if(id){const m=drawing.marks.find(v=>v.id===id);if(m)select(m)}return}
  const at=point(e);
  if(handle&&draft&&canEdit(draft))drag.current={action:'resize',point:at,original:{...draft,box:[...draft.box]},previous:draft,wasDirty:dirty};
  else if(id){
   const mark=id==='draft'?draft:drawing.marks.find(m=>m.id===id);if(!mark)return;
   if(draft?.id!==mark.id&&!discard())return;
   const copy={...mark,box:[...mark.box]};if(draft?.id!==mark.id)resetEdits();setPopup(true);setDraft(copy);setComments(true);setDirty(draft?.id===mark.id?dirty:false);
   if(canEdit(mark))drag.current={action:'move',point:at,original:copy,previous:copy,wasDirty:draft?.id===mark.id?dirty:false};
  }else if(tool!=='select'){
   if(!discard())return;const value=newDraft(tool,[at[0],at[1],Math.min(1,at[0]+.025),Math.min(1,at[1]+.025)]);
   resetEdits();remember({draft:null,dirty:false});drag.current={action:'draw',point:at,original:value,previous:draft,wasDirty:dirty,recorded:true};setPopup(true);setDraft(value);setDirty(true);setComments(true);
  }else return;
  if(drag.current){e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault()}
 };
 const pointerMove=(e:PointerEvent<SVGSVGElement>)=>{
  const value=drag.current;if(!value)return;if(!value.recorded){remember({draft:value.original,dirty:value.wasDirty});value.recorded=true}const at=point(e),[ax,ay]=value.point,box=[...value.original.box];
  if(value.action==='draw'){
   const x0=Math.min(.997,ax,at[0]),y0=Math.min(.997,ay,at[1]);box.splice(0,4,x0,y0,Math.min(1,Math.max(x0+.003,Math.max(ax,at[0]))),Math.min(1,Math.max(y0+.003,Math.max(ay,at[1]))));
  }else if(value.action==='move'){
   const dx=Math.max(-box[0],Math.min(1-box[2],at[0]-ax)),dy=Math.max(-box[1],Math.min(1-box[3],at[1]-ay));box.splice(0,4,box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy);
  }else{box[2]=Math.max(box[0]+.003,at[0]);box[3]=Math.max(box[1]+.003,at[1])}
  setDraft({...value.original,box,reverseX:value.action==='draw'?at[0]<ax:value.original.reverseX,reverseY:value.action==='draw'?at[1]<ay:value.original.reverseY});setDirty(true);
 };
 const pointerUp=(e:PointerEvent<SVGSVGElement>)=>{if(!drag.current)return;drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)};
 const save=async(value:Draft|null=draft)=>{
  if(!value||!drawing||!value.body.trim())return;setSaving(true);setError('');
  try{const saved=await api<Mark>(`/${drawing.id}/marks${value.id?'/'+value.id:''}`,body(value,value.id?'PUT':'POST'));setDrawing(v=>v?{...v,commands:saved.commands,marks:[...v.marks.filter(m=>m.id!==saved.id),saved].sort((a,b)=>a.page-b.page||a.created-b.created)}:v);setDraft(saved);resetEdits();setDirty(false);setNotice(`Correction saved as revision ${saved.version}.`);void list()}
  catch(e){setError((e as Error).message)}finally{setSaving(false)}
 };
 const remove=async()=>{
  if(!drawing||!draft?.id||!window.confirm('Delete this correction comment? The original PDF remains unchanged.'))return;
  setSaving(true);try{const result=await api<{commands:Commands}>(`/${drawing.id}/marks/${draft.id}?version=${draft.version}`,{method:'DELETE'});setDrawing(v=>v?{...v,commands:result.commands,marks:v.marks.filter(m=>m.id!==draft.id)}:v);resetEdits();setPopup(false);setDraft(null);setDirty(false);setNotice('Correction removed.');void list()}catch(e){setError((e as Error).message)}finally{setSaving(false)}
 };
 const shareWith=async(userId:number,role:string)=>{
  if(!drawing)return;setSaving(true);setError('');try{await api('/'+drawing.id+'/share',body({userId,access:role}));setDrawing(v=>v?{...v,members:[...v.members.filter(m=>m.user_id!==userId),...(role==='remove'?[]:[{user_id:userId,access:role as 'review'|'view'}])]}:v);setNotice(role==='remove'?'Access removed.':'Review shared. Copy the link to send it to the reviewer.')}catch(e){setError((e as Error).message)}finally{setSaving(false)}
 };
 const updateDraft=(value:Partial<Draft>)=>{remember();setDraft(v=>v?{...v,...value}:v);setDirty(true)};
 useEffect(()=>{
  if(!drawing||!draft?.id){setRevisions([]);return}
  const controller=new AbortController();
  void api<{revisions:Revision[]}>(`/${drawing.id}/marks/${draft.id}/history`,{signal:controller.signal}).then(v=>setRevisions(v.revisions)).catch(e=>{if(!controller.signal.aborted)setError(e.message)});
  return()=>controller.abort();
 },[drawing?.id,draft?.id,draft?.version]);
 const travel=async(direction:'undo'|'redo')=>{
  if(saving||busy)return;
  const from=direction==='undo'?edits.current.past:edits.current.future,to=direction==='undo'?edits.current.future:edits.current.past;
  if(from.length){to.push(structuredClone({draft,dirty}));const state=from.pop()!;setDraft(state.draft);setDirty(state.dirty);setPopup(!!state.draft);setNotice(direction==='undo'?'Draft change undone.':'Draft change redone.');return}
  const command=drawing?.commands?.[direction];if(!drawing||!command||dirty)return;
  setSaving(true);setError('');
  try{const next=await api<Review>(`/${drawing.id}/history/${direction}`,body({commandId:command.id}));setDrawing(next);setDraft(next.marks.find(m=>m.id===draft?.id)||null);resetEdits();setDirty(false);setNotice(`${direction==='undo'?'Undo':'Redo'} completed; a new comment revision was recorded.`);void list()}catch(e){setError((e as Error).message)}finally{setSaving(false)}
 };
 useEffect(()=>{
  const key=(e:KeyboardEvent)=>{if(!active||!(e.ctrlKey||e.metaKey)||e.altKey)return;const tag=(e.target as Element)?.tagName;if(['TEXTAREA','INPUT','SELECT'].includes(tag)||(e.target as HTMLElement)?.isContentEditable)return;
   if(e.key.toLowerCase()==='z'){e.preventDefault();void travel(e.shiftKey?'redo':'undo')}else if(e.key.toLowerCase()==='y'){e.preventDefault();void travel('redo')}};
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
 });
 const restoreRevision=async(revision:number)=>{
  if(!drawing||!draft?.id||!discard())return;setSaving(true);setError('');
  try{const next=await api<Review>(`/${drawing.id}/marks/${draft.id}/restore`,body({revision,version:draft.version}));setDrawing(next);setDraft(next.marks.find(m=>m.id===draft.id)||null);resetEdits();setDirty(false);setNotice('Previous comment restored as a new revision.')}catch(e){setError((e as Error).message)}finally{setSaving(false)}
 };
 const importFeedback=async(file:File)=>{
  if(!drawing||!discard())return;setSaving(true);setError('');const data=new FormData();data.append('file',file);
  try{const next=await api<Review>(`/${drawing.id}/import`,{method:'POST',body:data});setDrawing(next);setDraft(null);setPopup(false);resetEdits();setDirty(false);setNotice(`${next.importSummary?.updated||0} feedback comments imported; ${next.importSummary?.unchanged||0} unchanged. ${next.importSummary?.unmatched?`${next.importSummary.unmatched} missing annotations were left unchanged.`:''}`);void list()}catch(e){setError((e as Error).message)}finally{setSaving(false)}
 };
 const visible=(drawing?.marks||[]).filter(m=>(scope==='all'||m.page===page)&&(filter==='all'||m.status===filter||m.kind===filter)&&`${m.body} ${m.author}`.toLowerCase().includes(search.toLowerCase()));
 const info=drawing?.pages[page-1];
 const shown=[...(drawing?.marks||[]).filter(m=>m.page===page&&m.id!==draft?.id),...(draft?.page===page?[draft]:[])];
 const markShape=(mark:Draft,index:number)=>{
  const [x0,y0,x1,y1]=mark.box.map(n=>n*1000);const selected=draft===mark;
  const start=[mark.reverseX?x1:x0,mark.reverseY?y1:y0],end=[mark.reverseX?x0:x1,mark.reverseY?y0:y1];
  return <g key={mark.id||'draft'} data-mark={mark.id||'draft'} className={`edMark ${selected?'selected':''} ${mark.status}`} style={{color:colours[mark.kind]}}>
   <title>{mark.kind}: {mark.body||'New correction'}</title>
   {mark.shape==='cloud'?<path d={cloud(mark.box)}/>:mark.shape==='arrow'?<><rect x={x0} y={y0} width={x1-x0} height={y1-y0} className="edArrowHit"/><path d={`M${start[0]} ${start[1]} L${end[0]} ${end[1]}`} markerEnd={`url(#ed-arrow-${mark.kind})`}/></>:mark.shape==='note'?<circle cx={x0+10} cy={y0+10} r={14}/>:<rect x={x0} y={y0} width={x1-x0} height={y1-y0}/>}
   <text x={x0+3} y={Math.max(17,y0-6)}> {mark.id?'R'+String((drawing?.marks.findIndex(m=>m.id===mark.id)??index)+1).padStart(3,'0'):'New'}</text>
   {selected&&editable&&canEdit(mark)&&<rect data-resize="true" className="edResize" x={x1-7} y={y1-7} width={14} height={14}/>}
  </g>;
 };
 return <div className="edWorkspace">
  <header className="edHeading"><div><span className="edEyebrow">ENGINEERING / DRAWING REVIEW</span><h1><FilePenLine/>e-design review</h1><p>Review circuit drawings. Mark corrections, additions and removals with page-linked comments.</p></div><label className={`btn primary edUpload ${busy?'disabled':''}`}><Upload size={16}/>{busy?'Opening drawing…':'Upload circuit PDF'}<input type="file" accept="application/pdf,.pdf" disabled={busy} aria-label="Upload circuit PDF" onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void upload(f)}}/></label></header>
  {error&&<div className="edError" role="alert">{error}<button aria-label="Dismiss error" onClick={()=>setError('')}><X size={16}/></button></div>}
  {notice&&<p className="edNotice" role="status">{notice}</p>}
  {!drawing?<section className="edLibrary"><h2>Drawing reviews</h2>{!reviews.length?<div className="edEmpty"><FilePenLine size={38}/><h3>Start with a circuit drawing</h3><p>Upload a PDF, mark an area and enter the correction in the comments panel.</p></div>:reviews.map(r=><button className="edReviewCard" key={r.id} disabled={busy} onClick={()=>void load(r.id)}><FilePenLine/><span><b>{r.name}</b><small>{r.pages.length} pages · {r.open} open · {r.resolved} resolved · {r.owner}</small></span><span>{r.access==='owner'?'My drawing':'Shared with me'}</span></button>)}</section>:<>
   <div className="edDocumentBar"><button className="btn" onClick={()=>{if(discard()){++epoch.current;setDrawing(null);setDraft(null);setDirty(false);history.replaceState(null,'',location.pathname+location.search);void list()}}}><ArrowLeft size={16}/>Reviews</button><select aria-label="Open drawing review" value={drawing.id} disabled={busy} onChange={e=>{if(discard())void load(e.target.value)}}>{!reviews.some(r=>r.id===drawing.id)&&<option value={drawing.id}>{drawing.name}</option>}{reviews.map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select><span className="edAccess">{drawing.access==='view'?'View only':drawing.access==='review'?'Reviewer':'Owner'}</span><button className="btn" onClick={()=>{if(discard())void load(drawing.id)}}><RefreshCw size={15}/>Refresh</button>{editable&&<label className="btn edUpload"><Upload size={15}/>Import feedback PDF<input aria-label="Import feedback PDF" type="file" accept="application/pdf,.pdf" disabled={saving||busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void importFeedback(file)}}/></label>}<button className="btn" onClick={()=>setShare(true)}><Share2 size={15}/>Share</button><details className="edExports"><summary className="btn"><Download size={15}/>Export</summary><div><a href={`/api/e-design/${drawing.id}/export/pdf`}>Review PDF (editable comments)</a><a href={`/api/e-design/${drawing.id}/export/report`}>PDF correction report</a><a href={`/api/e-design/${drawing.id}/export/docx`}>Corrections in Word</a><a href={`/api/e-design/${drawing.id}/export/csv`}>Correction list (CSV)</a><a href={`/api/e-design/${drawing.id}/export/html`}>Drawing review (HTML)</a><a href={`/api/e-design/${drawing.id}/original`}>Original PDF</a></div></details></div>
   <div className="edToolbar" role="toolbar" aria-label="Drawing review tools"><button className="btn" aria-pressed={tool==='select'} onClick={()=>setTool('select')}><MousePointer2 size={16}/>Select / move</button>{kinds.map(({id,label,Icon})=><button disabled={!editable} key={id} style={{'--ed-tool':colours[id]} as CSSProperties} className="btn edTool" aria-pressed={tool===id} onClick={()=>setTool(id)}><Icon size={16}/>{label}</button>)}<label>Shape<select aria-label="Markup shape" value={shape} onChange={e=>setShape(e.target.value as Shape)}><option value="cloud">Revision cloud</option><option value="rectangle">Rectangle</option><option value="arrow">Arrow</option></select></label><button className="btn" aria-label="Undo review change" title="Undo (Ctrl+Z)" disabled={!editable||saving||busy||(!edits.current.past.length&&(!drawing.commands?.undo||dirty))} onClick={()=>void travel('undo')}><Undo2 size={16}/>Undo</button><button className="btn" aria-label="Redo review change" title="Redo (Ctrl+Y / Ctrl+Shift+Z)" disabled={!editable||saving||busy||(!edits.current.future.length&&(!drawing.commands?.redo||dirty))} onClick={()=>void travel('redo')}><Redo2 size={16}/>Redo</button><div className="edToolSpacer"/><button className="btn" onClick={()=>setZoom(v=>Math.max(50,(v||100)-25))} aria-label="Zoom out PDF"><ZoomOut size={16}/></button><select aria-label="PDF zoom" value={zoom} onChange={e=>setZoom(Number(e.target.value))}><option value={0}>Fit width</option>{[50,75,100,125,150,200,300].map(v=><option key={v} value={v}>{v}%</option>)}</select><button className="btn" onClick={()=>setZoom(v=>Math.min(300,(v||100)+25))} aria-label="Zoom in PDF"><ZoomIn size={16}/></button><button className="btn" aria-pressed={comments} onClick={()=>setComments(v=>!v)}>{comments?<PanelRightClose size={16}/>:<PanelRightOpen size={16}/>}Comments ({drawing.marks.length})</button></div>
   <div className={`edLayout ${comments?'hasComments':''} ${pinned?'pinned':'floating'}`}>
    <nav className="edPages" aria-label="Drawing review pages">{drawing.pages.map(p=><button key={p.number} aria-current={page===p.number?'page':undefined} onClick={()=>choosePage(p.number)}><span>Page {p.number}</span><small>{drawing.marks.filter(m=>m.page===p.number).length} comments</small></button>)}</nav>
    <section className="edDrawing"><header><b>{drawing.name}</b><span>Page {page} / {drawing.pages.length}</span></header><div className="edViewport"><div className={`edCanvas ${tool!=='select'&&editable?'drawing':''}`} ref={canvas} style={{width:zoom?`${(info?.width||800)*zoom/100}px`:'100%',aspectRatio:info?`${info.width}/${info.height}`:undefined}}>
     <img src={`/api/e-design/${drawing.id}/page/${page}`} alt={`${drawing.name}, page ${page}`} draggable={false}/>
     <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Drawing markup canvas" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{if(drag.current){setDraft(drag.current.previous);setDirty(drag.current.wasDirty);drag.current=null}}}>
      <defs>{kinds.map(k=><marker id={`ed-arrow-${k.id}`} key={k.id} markerWidth={8} markerHeight={8} refX={7} refY={4} orient="auto" markerUnits="strokeWidth"><path d="M0 0 L8 4 L0 8" fill="none" stroke={colours[k.id]}/></marker>)}</defs>{shown.map(markShape)}
     </svg>
     {draft?.page===page&&popup&&<section className="edInlineComment" aria-label="Comment beside selected shape" style={{left:`clamp(6px,${draft.box[2]*100}%,calc(100% - 270px))`,top:`${Math.min(.75,draft.box[1])*100}%`,borderColor:colours[draft.kind]}}>
      <header><b>{draft.kind} | {draft.id?`Revision ${draft.version}`:'New comment'}</b><button aria-label="Hide shape comment" onClick={()=>setPopup(false)}><X size={14}/></button></header>
      <textarea aria-label="Shape comment" rows={3} maxLength={6000} readOnly={!editable||saving} placeholder="Comment on this area..." value={draft.body} onChange={e=>updateDraft({body:e.target.value})}/>
      <footer><button className="btn" disabled={!editable||saving||!dirty||!draft.body.trim()} onClick={()=>void save()}>Save</button><button className="btn" onClick={()=>setComments(true)}><SlidersHorizontal size={14}/>Properties</button>{draft.id&&<button className="btn" disabled={!editable||saving||!draft.body.trim()} onClick={()=>void save({...draft,status:draft.status==='open'?'resolved':'open'})}>{draft.status==='open'?'Resolve':'Reopen'}</button>}</footer>
     </section>}
    </div></div><footer><span className="edColour remove">Red: remove</span><span className="edColour add">Green: add</span><span className="edColour modify">Amber: modify</span><span>Drag to mark an area. Select a markup to move or resize it.</span></footer></section>
    {comments&&<aside className="edComments" aria-label="Drawing correction comments"><header><h2>Properties &amp; comments <small>{drawing.marks.length}</small></h2><div><button className="btn" aria-label={pinned?'Unpin comments panel':'Pin comments panel'} aria-pressed={pinned} onClick={()=>setPinned(v=>{userStorage.setItem('usopp_edesign_pin',String(!v));return !v})}>{pinned?<Pin size={16}/>:<PinOff size={16}/>}</button><button className="btn" aria-label="Hide comments panel" onClick={()=>setComments(false)}><PanelRightClose size={16}/></button></div></header>
     {draft&&<section className="edComposer" aria-label="Correction editor">
      <div className="edComposerHeading"><b>{draft.id?'Comment properties':'New comment properties'} | Page {draft.page}</b><button className="btn" aria-label="Close correction editor" onClick={()=>{if(discard()){setDraft(null);setDirty(false);setPopup(false);resetEdits()}}}><X size={15}/></button></div>
      <label>Shape<select aria-label="Selected markup shape" disabled={!editable} value={draft.shape} onChange={e=>updateDraft({shape:e.target.value as Shape})}><option value="cloud">Revision cloud</option><option value="rectangle">Rectangle</option><option value="arrow">Arrow</option><option value="note">Comment pin</option></select></label>
      <label>Correction type<select aria-label="Correction type" disabled={!editable||saving} value={draft.kind} onChange={e=>updateDraft({kind:e.target.value as Kind})}>{kinds.map(k=><option key={k.id} value={k.id}>{k.label}</option>)}</select></label>
      <label>Comment<textarea aria-label="Correction comment" rows={4} maxLength={6000} readOnly={!editable||saving} value={draft.body} placeholder="Describe what needs to change..." onChange={e=>updateDraft({body:e.target.value})}/></label>
      <label>Status<select aria-label="Correction status" disabled={!editable||saving} value={draft.status} onChange={e=>updateDraft({status:e.target.value as 'open'|'resolved'})}><option value="open">Open</option><option value="resolved">Resolved</option></select></label>
      {editable&&<div className="edEditorActions"><button className="btn primary" disabled={saving||!draft.body.trim()||!dirty} onClick={()=>void save()}><Save size={15}/>{saving?'Saving...':'Save correction'}</button>{draft.id&&<button className="btn edDelete" disabled={saving} onClick={()=>void remove()}><Trash2 size={15}/>Delete</button>}</div>}
      <small>{dirty?'Unsaved changes':draft.author?`Revision ${draft.version} | ${draft.author}`:''}</small>
      {draft.id&&<><button className="btn edResolve" disabled={saving||!editable||!draft.body.trim()} onClick={()=>void save({...draft,status:draft.status==='open'?'resolved':'open'})}><Check size={15}/>{draft.status==='open'?'Resolve comment':'Reopen comment'}</button>
       <details className="edRevisionHistory"><summary><History size={15}/>Comment revision history ({revisions.length})</summary>{revisions.map((revision,i)=><article key={`${revision.origin}-${revision.version}-${i}`}>
        <b>{revision.origin.startsWith('Imported')?'PDF revision':'Revision'} {revision.version} | {revision.action}</b><small>{revision.actor} | {new Date(revision.at*1000).toLocaleString()}</small>{revision.origin&&<small>{revision.origin}</small>}
        <p>{revision.snapshot.body}</p><small>{revision.snapshot.kind} | {revision.snapshot.status} | {revision.snapshot.deleted?'deleted':'retained'}</small>
        {editable&&!revision.origin.startsWith('Imported')&&revision.version!==draft.version&&<button className="btn" disabled={saving} onClick={()=>void restoreRevision(revision.version)}>Restore as new revision</button>}
       </article>)}</details></>}
     </section>}
     <div className="edCommentFilters"><input aria-label="Search correction comments" placeholder="Search comments or author" value={search} onChange={e=>setSearch(e.target.value)}/><div><select aria-label="Comments page filter" value={scope} onChange={e=>setScope(e.target.value)}><option value="page">Current page</option><option value="all">All pages</option></select><select aria-label="Comments status filter" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All corrections</option><option value="open">Open</option><option value="resolved">Resolved</option>{kinds.map(k=><option key={k.id} value={k.id}>{k.label}</option>)}</select></div>{editable&&<button className="btn" onClick={centreComment}><Plus size={15}/>Add comment at page centre</button>}</div>
     <div className="edCommentList">{Array.from(new Set(visible.map(m=>m.page))).sort((a,b)=>a-b).map(n=><section key={n}><h3>Page {n}</h3>{visible.filter(m=>m.page===n).map(mark=><button className={`edComment ${draft?.id===mark.id?'active':''}`} key={mark.id} style={{'--ed-tool':colours[mark.kind]} as CSSProperties} onClick={()=>select(mark)}><span><b>R{String(drawing.marks.indexOf(mark)+1).padStart(3,'0')} · {mark.kind}</b><small>{mark.status==='resolved'?<Check size={13}/>:null}{mark.status}</small></span><p>{mark.body}</p><small>{mark.author} · {new Date(mark.updated*1000).toLocaleString()}</small></button>)}</section>)}{!visible.length&&<p className="edEmptyComments">No comments match this view. {editable?'Mark an area or add a comment to start the review.':''}</p>}</div>
    </aside>}
   </div>
  </>}
  <dialog className="edShareDialog" ref={dialog} onCancel={()=>setShare(false)}><header><h2>Share drawing review</h2><button className="btn" aria-label="Close sharing" onClick={()=>setShare(false)}><X size={18}/></button></header>{drawing&&<><p>The review link requires sign-in. To share outside uSOPp, export the editable review PDF; the recipient can comment in a PDF reader and return the saved PDF.</p><label>Review link<input aria-label="Review sharing link" readOnly value={`${location.origin}/#e-design/${drawing.id}`}/></label><button className="btn" onClick={()=>void navigator.clipboard.writeText(`${location.origin}/#e-design/${drawing.id}`).then(()=>setNotice('Review link copied.')).catch(()=>setNotice('Select and copy the review link.'))}>Copy link</button>{drawing.access==='owner'&&<><div className="edShareControls"><label>Reviewer<select aria-label="Share with reviewer" value={person} onChange={e=>setPerson(e.target.value)}><option value="">Select account</option>{people.filter(p=>p.id!==drawing.ownerId).map(p=><option key={p.id} value={p.id}>{p.username} · {p.designation}</option>)}</select></label><label>Access<select aria-label="Reviewer access" value={access} onChange={e=>setAccess(e.target.value)}><option value="review">Edit comments and review</option><option value="view">View only</option></select></label><button className="btn primary" disabled={!person||saving} onClick={()=>void shareWith(Number(person),access)}>Grant access</button></div><h3>Shared accounts</h3>{drawing.members.map(m=><div className="edMember" key={m.user_id}><span>{people.find(p=>p.id===m.user_id)?.username||'Account '+m.user_id} · {m.access}</span><button className="btn" disabled={saving} onClick={()=>void shareWith(m.user_id,'remove')}>Remove access</button></div>)}{!drawing.members.length&&<p>This drawing has not been shared.</p>}</>}<small>Import the returned review PDF to merge feedback, or upload it as a new review. Editing support depends on the recipient's PDF application; printing or flattening removes editable comments.</small></>}</dialog>
 </div>;
}
