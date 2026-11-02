import {defaultCallout,calloutLeader,moveMarkup} from './calloutGeometry';
import {ReviewSidebar} from './ReviewSidebar';
import {ReviewExportDialog,type Cover,type ExportFormat} from './ReviewExportDialog';
import {shapeOptions,regionShape,optionalComment,markColor,markOpacity,reference,referenceColor,type Shape} from './reviewTools';
import {useEffect,useRef,useState,type PointerEvent,type CSSProperties} from 'react';
import {ArrowLeft,Upload,FilePenLine,MousePointer2,Plus,Minus,Pencil,MessageSquare,ZoomIn,ZoomOut,PanelRightClose,PanelRightOpen,Pin,PinOff,Share2,Download,Save,Trash2,RefreshCw,X,Check,Undo2,Redo2,History,SlidersHorizontal} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {userStorage} from '../../shared/userStorage';
import './edesign.css';
import './review-workspace.css';

type Kind='modify'|'add'|'remove'|'comment';
type Commands={undo:{id:number;label:string}|null;redo:{id:number;label:string}|null};
export type Revision={version:number;action:string;actor:string;at:number;origin:string;snapshot:Draft};
export type Mark={color?:string|null;opacity?:number|null;points?:number[][]|null;reference?:string;referenceNo?:number;callout?:number[]|null;deleted?:boolean;commands?:Commands;id:string;page:number;kind:Kind;shape:Shape;box:number[];body:string;status:'open'|'resolved';author:string;author_id:number;created:number;updated:number;version:number;reverseX:boolean;reverseY:boolean};
export type Draft=Omit<Mark,'id'|'author'|'author_id'|'created'|'updated'>&Partial<Pick<Mark,'id'|'author'|'author_id'>>;
type Review={cover:Cover;coverVersion:number;nextReference:string;calloutSetupNeeded?:boolean;calloutsPrepared?:number;commands?:Commands;importSummary?:{updated:number;unchanged:number;unmatched:number};id:string;name:string;ownerId:number;owner:string;created:number;pages:{number:number;width:number;height:number}[];access:'owner'|'review'|'view';marks:Mark[];members:{user_id:number;access:'view'|'review'}[];open?:number;resolved?:number};
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
 const [exportFormat,setExportFormat]=useState<ExportFormat|null>(null);
 const [sidebarWidth,setSidebarWidth]=useState(()=>Math.max(280,Math.min(650,Number(userStorage.getItem('usopp_edesign_sidebar_width'))||390)));
 const [inkColor,setInkColor]=useState('#e6a100');
 const [comments,setComments]=useState(true),[pinned,setPinned]=useState(()=>userStorage.getItem('usopp_edesign_pin')!=='false');
 const [draft,setDraft]=useState<Draft|null>(null),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const textInput=useRef<HTMLTextAreaElement>(null),[focusText,setFocusText]=useState(0);
 const [popup,setPopup]=useState(false),[revisions,setRevisions]=useState<Revision[]>([]);
 const edits=useRef<{past:{draft:Draft|null;dirty:boolean}[];future:{draft:Draft|null;dirty:boolean}[]}>({past:[],future:[]});
 const resetEdits=()=>{edits.current={past:[],future:[]}};
 const remember=(value={draft,dirty})=>{edits.current.past.push(structuredClone(value));edits.current.past=edits.current.past.slice(-100);edits.current.future=[]};
 const [scope,setScope]=useState('page'),[filter,setFilter]=useState('all'),[search,setSearch]=useState('');
 const [share,setShare]=useState(false),[people,setPeople]=useState<Person[]>([]),[person,setPerson]=useState(''),[access,setAccess]=useState('review');
 const canvas=useRef<HTMLDivElement>(null),dialog=useRef<HTMLDialogElement>(null),epoch=useRef(0),initialized=useRef(false);
 const drag=useRef<{action:'draw'|'move'|'resize'|'label'|'label-resize';point:number[];original:Draft;previous:Draft|null;wasDirty:boolean;recorded?:boolean;points?:number[][]}|null>(null);
 useEffect(()=>{if(focusText){textInput.current?.focus({preventScroll:true});textInput.current?.scrollIntoView({block:'nearest',inline:'nearest'});}},[focusText]);
 const editable=!!drawing&&drawing.access!=='view';
 const canEdit=(_mark:{author_id?:number})=>editable;
 const discard=()=>!dirty||window.confirm('Discard the unsaved correction changes?');
 const list=async()=>{try{setReviews((await api<{reviews:Review[]}>('')).reviews)}catch(e){setError((e as Error).message)}};
 const isRegion=(mark:{shape:Shape})=>regionShape(mark.shape);
 const placeCallout=(box:number[],number=page)=>defaultCallout(box,(drawing?.pages[number-1]?.width||1)/(drawing?.pages[number-1]?.height||1),(drawing?.marks||[]).filter(m=>m.page===number).flatMap(m=>[m.box,...(m.callout?[m.callout]:[])]));
 const prepareCallouts=async(value:Review)=>{const marks=value.marks.filter(m=>isRegion(m)&&!m.callout);if(!marks.length||value.access==='view')return value;const next=await api<Review>('/'+value.id+'/callouts',body({versions:Object.fromEntries(marks.map(m=>[m.id,m.version]))}));setNotice(`${next.calloutsPrepared||0} existing bubble comments now show their arrow and text on the drawing.`);return next;};
 const prepareOnOpen=(value:Review)=>value.calloutSetupNeeded?prepareCallouts(value):Promise.resolve(value);
 const load=async(id:string)=>{
  const ticket=++epoch.current;setError('');setBusy(true);
  try{const value=await prepareOnOpen(await api<Review>('/'+id));if(ticket!==epoch.current)return;setDrawing(value);resetEdits();setPopup(false);setDraft(null);setDirty(false);setPage(1);setTool('select');userStorage.setItem('usopp_edesign_review',id);history.replaceState(null,'','#e-design/'+id)}
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
  try{const value=await prepareOnOpen(await api<Review>('',{method:'POST',body:form}));setDrawing(value);resetEdits();setPopup(false);setPage(1);setDraft(null);setDirty(false);setTool('select');userStorage.setItem('usopp_edesign_review',value.id);history.replaceState(null,'','#e-design/'+value.id);void list();setNotice(value.marks.length?`${value.marks.length} editable PDF comments imported with available revision history.`:'Drawing uploaded. Choose a correction tool and drag over an area.')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 };
 const choosePage=(n:number)=>{if(n===page||!discard())return;setPage(n);resetEdits();setPopup(false);setDraft(null);setDirty(false);setNotice('')};
  const select=(mark:Mark)=>{if(!discard())return;setPage(mark.page);resetEdits();setPopup(true);setDraft({...mark,box:[...mark.box]});setDirty(false);setComments(true);setTool('select');setFocusText(v=>v+1)};
 const newDraft=(kind:Kind,box:number[],markShape=shape):Draft=>{const x0=Math.min(.997,box[0]),y0=Math.min(.997,box[1]);return {page,kind,shape:markShape,box:[x0,y0,Math.max(x0+.003,box[2]),Math.max(y0+.003,box[3])],body:'',status:'open',version:0,reverseX:false,reverseY:false,callout:null,color:inkColor,opacity:markShape==='highlight'?.28:markShape==='marker'?.7:1,reference:drawing?.nextReference,points:markShape==='marker'?[[x0,y0],[Math.min(1,x0+.003),Math.min(1,y0+.003)]]:null}};
 const centreComment=()=>{if(!discard())return;resetEdits();remember({draft:null,dirty:false});setPopup(true);const value=newDraft(tool==='select'?'comment':tool,[.35,.35,.55,.5],tool==='select'?'note':shape);if(isRegion(value))value.callout=placeCallout(value.box);setDraft(value);setFocusText(v=>v+1);setDirty(true);setComments(true);setNotice('Enter a comment, then save the correction.')};
 const point=(e:PointerEvent)=>{const rect=canvas.current!.getBoundingClientRect();return [bound((e.clientX-rect.left)/rect.width),bound((e.clientY-rect.top)/rect.height)]};
 const pointerDown=(e:PointerEvent<SVGSVGElement|HTMLDivElement>)=>{
  if(e.button!==0||!drawing||saving)return;
  const target=e.target as Element;if(target.closest('textarea,button,input,select'))return;const handle=!!target.closest('[data-resize]'),label=!!target.closest('[data-callout]'),labelResize=!!target.closest('[data-label-resize]'),id=target.closest('[data-mark]')?.getAttribute('data-mark');
  if(!editable){if(id){const m=drawing.marks.find(v=>v.id===id);if(m)select(m)}return}
  const at=point(e);
  if(handle&&draft&&canEdit(draft))drag.current={action:'resize',point:at,original:{...draft,box:[...draft.box]},previous:draft,wasDirty:dirty};
  else if(id){
   const mark=id==='draft'||id===draft?.id?draft:drawing.marks.find(m=>m.id===id);if(!mark)return;
   if(draft?.id!==mark.id&&!discard())return;
   const copy={...mark,box:[...mark.box]};if(draft?.id!==mark.id)resetEdits();setPopup(true);setDraft(copy);setComments(true);setDirty(draft?.id===mark.id&&dirty);
   if(canEdit(mark))drag.current={action:labelResize?'label-resize':label?'label':'move',point:at,original:copy,previous:copy,wasDirty:draft?.id===mark.id?dirty:false};
  }else if(tool!=='select'){
   if(!discard())return;const value=newDraft(tool,[at[0],at[1],Math.min(1,at[0]+.025),Math.min(1,at[1]+.025)]);
   resetEdits();remember({draft:null,dirty:false});drag.current={action:'draw',point:at,original:value,previous:draft,wasDirty:dirty,recorded:true,points:[at]};setPopup(true);setDraft(value);setDirty(true);setComments(true);
  }else return;
  if(drag.current){e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault()}
 };
 const pointerMove=(e:PointerEvent<SVGSVGElement|HTMLDivElement>)=>{
  const value=drag.current;if(!value)return;if(!value.recorded){remember({draft:value.original,dirty:value.wasDirty});value.recorded=true}const at=point(e),[ax,ay]=value.point,box=[...value.original.box];let callout=value.original.callout,points=value.original.points;
  if(value.action==='draw'&&value.original.shape==='marker'){let stroke=value.points||[value.point];if(Math.hypot(at[0]-stroke[stroke.length-1][0],at[1]-stroke[stroke.length-1][1])>.0008)stroke=[...stroke,at];if(stroke.length>1900)stroke=stroke.filter((_,i)=>i%2===0||i===stroke.length-1);value.points=stroke;points=stroke.length>1?stroke:[stroke[0],[Math.min(1,stroke[0][0]+.003),Math.min(1,stroke[0][1]+.003)]];const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);box.splice(0,4,Math.min(.997,...xs),Math.min(.997,...ys),Math.min(1,Math.max(Math.min(...xs)+.003,...xs)),Math.min(1,Math.max(Math.min(...ys)+.003,...ys)));setDraft({...value.original,box,points});setDirty(true);return;}
  if(value.action==='draw'){
   const x0=Math.min(.997,ax,at[0]),y0=Math.min(.997,ay,at[1]);box.splice(0,4,x0,y0,Math.min(1,Math.max(x0+.003,Math.max(ax,at[0]))),Math.min(1,Math.max(y0+.003,Math.max(ay,at[1]))));
  }else if(value.action==='move'){
   const moved=moveMarkup(box,callout,at[0]-ax,at[1]-ay);box.splice(0,4,...moved.box);callout=moved.callout;points=points?.map(([x,y])=>[bound(x+box[0]-value.original.box[0]),bound(y+box[1]-value.original.box[1])]);
  }else if(value.action==='label'&&callout){callout=moveMarkup(callout,null,at[0]-ax,at[1]-ay).box;
  }else if(value.action==='label-resize'&&callout){callout=[callout[0],callout[1],Math.min(1,Math.max(callout[0]+.06,at[0])),Math.min(1,Math.max(callout[1]+.035,at[1]))];
  }else{box[2]=Math.max(box[0]+.003,at[0]);box[3]=Math.max(box[1]+.003,at[1]);points=points?.map(([x,y])=>[bound(box[0]+(x-value.original.box[0])/(value.original.box[2]-value.original.box[0])*(box[2]-box[0])),bound(box[1]+(y-value.original.box[1])/(value.original.box[3]-value.original.box[1])*(box[3]-box[1]))])}
  setDraft({...value.original,box,callout,points,reverseX:value.action==='draw'?at[0]<ax:value.original.reverseX,reverseY:value.action==='draw'?at[1]<ay:value.original.reverseY});setDirty(true);
 };
 const pointerUp=(e:PointerEvent<SVGSVGElement|HTMLDivElement>)=>{const gesture=drag.current;if(!gesture)return;drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(gesture.action==='draw'){setDraft(current=>current?{...current,callout:isRegion(current)?placeCallout(current.box):current.callout}:current);setPopup(true);setFocusText(v=>v+1);}else if(!gesture.recorded){setPopup(true);setFocusText(v=>v+1);}};
 const save=async(value:Draft|null=draft)=>{
  if(!value||!drawing||(!value.body.trim()&&!optionalComment(value.shape)))return;setSaving(true);setError('');
  try{const saved=await api<Mark>(`/${drawing.id}/marks${value.id?'/'+value.id:''}`,body({...value,callout:value.shape==='cloud-only'?null:value.callout},value.id?'PUT':'POST'));setDrawing(v=>v?{...v,nextReference:'R'+String((saved.referenceNo||0)+1).padStart(3,'0'),commands:saved.commands,marks:[...v.marks.filter(m=>m.id!==saved.id),saved].sort((a,b)=>a.page-b.page||a.created-b.created)}:v);setDraft(saved);resetEdits();setDirty(false);setPopup(false);setNotice(`Correction saved as revision ${saved.version}.`);void list()}
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
 const visible=(drawing?.marks||[]).filter(m=>(scope==='all'||m.page===page)&&(filter==='all'||m.status===filter||m.kind===filter)&&`${reference(m)} ${m.body} ${m.author}`.toLowerCase().includes(search.toLowerCase()));
 const info=drawing?.pages[page-1];
 const shown=[...(drawing?.marks||[]).filter(m=>m.page===page&&m.id!==draft?.id),...(draft?.page===page?[draft]:[])];
 const markShape=(mark:Draft,index:number)=>{
  const [x0,y0,x1,y1]=mark.box.map(n=>n*1000);const selected=draft===mark;
  const start=[mark.reverseX?x1:x0,mark.reverseY?y1:y0],end=[mark.reverseX?x0:x1,mark.reverseY?y0:y1];
  return <g key={mark.id||'draft'} data-mark={mark.id||'draft'} className={`edMark ${selected?'selected':''} ${mark.status}`} style={{color:markColor(mark)}}>
   <defs><marker id={"ed-tip-"+(mark.id||"draft")} markerWidth={5} markerHeight={4} refX={4.5} refY={2} orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L4.5 2 L0 4" fill="none" stroke={markColor(mark)} strokeWidth={1.2}/></marker></defs><title>{mark.kind}: {mark.body||'New correction'}</title>
   {(mark.shape==='cloud'||mark.shape==='cloud-only')?<path d={cloud(mark.box)}/>:mark.shape==='arrow'?<><rect x={x0} y={y0} width={x1-x0} height={y1-y0} className="edArrowHit"/><path d={`M${start[0]} ${start[1]} L${end[0]} ${end[1]}`} markerEnd={`url(#ed-tip-${mark.id||'draft'})`}/></>:mark.shape==='highlight'?<rect x={x0} y={y0} width={x1-x0} height={y1-y0} style={{fill:markColor(mark),fillOpacity:markOpacity(mark),stroke:'none'}}/>:mark.shape==='underline'?<><rect className="edArrowHit" x={x0} y={y0} width={x1-x0} height={y1-y0}/><path d={`M${x0} ${y1} L${x1} ${y1}`}/></>:mark.shape==='marker'?<><path className="edMarkerHit" d={'M'+(mark.points||[[x0/1000,y0/1000],[x1/1000,y1/1000]]).map(p=>p.map(v=>v*1000).join(' ')).join(' L')}/><polyline points={(mark.points||[[x0/1000,y0/1000],[x1/1000,y1/1000]]).map(p=>p.map(v=>v*1000).join(',')).join(' ')} style={{stroke:markColor(mark),strokeWidth:5,strokeOpacity:markOpacity(mark),strokeLinecap:'round',strokeLinejoin:'round',fill:'none'}}/></>:mark.shape==='note'?<circle cx={x0+10} cy={y0+10} r={14}/>:<rect x={x0} y={y0} width={x1-x0} height={y1-y0}/>}
   <text style={{fill:referenceColor(mark)}} x={x0+3} y={Math.max(17,y0-6)}> {reference(mark)}</text>
   {mark.callout&&<polyline className="edCalloutLeader" points={calloutLeader(mark.box,mark.callout).map(p=>p.map(v=>v*1000).join(',')).join(' ')} markerEnd={`url(#ed-tip-${mark.id||'draft'})`}/>}
   {selected&&editable&&canEdit(mark)&&<rect data-resize="true" className="edResize" x={x1-7} y={y1-7} width={14} height={14}/>}
  </g>;
 };
 return <div className="edWorkspace">
  <header className="edHeading"><div><span className="edEyebrow">ENGINEERING / DRAWING REVIEW</span><h1><FilePenLine/>e-design review</h1><p>Review circuit drawings. Mark corrections, additions and removals with page-linked comments.</p></div><label className={`btn primary edUpload ${busy?'disabled':''}`}><Upload size={16}/>{busy?'Opening drawing…':'Upload circuit PDF'}<input type="file" accept="application/pdf,.pdf" disabled={busy} aria-label="Upload circuit PDF" onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void upload(f)}}/></label></header>
  {error&&<div className="edError" role="alert">{error}<button aria-label="Dismiss error" onClick={()=>setError('')}><X size={16}/></button></div>}
  {notice&&<p className="edNotice" role="status">{notice}</p>}
  {!drawing?<section className="edLibrary"><h2>Drawing reviews</h2>{!reviews.length?<div className="edEmpty"><FilePenLine size={38}/><h3>Start with a circuit drawing</h3><p>Upload a PDF, draw a revision bubble and enter its comment directly on the drawing.</p></div>:reviews.map(r=><button className="edReviewCard" key={r.id} disabled={busy} onClick={()=>void load(r.id)}><FilePenLine/><span><b>{r.name}</b><small>{r.pages.length} pages · {r.open} open · {r.resolved} resolved · {r.owner}</small></span><span>{r.access==='owner'?'My drawing':'Shared with me'}</span></button>)}</section>:<>
   <div className="edDocumentBar"><button className="btn" onClick={()=>{if(discard()){++epoch.current;setDrawing(null);setDraft(null);setDirty(false);history.replaceState(null,'',location.pathname+location.search);void list()}}}><ArrowLeft size={16}/>Reviews</button><select aria-label="Open drawing review" value={drawing.id} disabled={busy} onChange={e=>{if(discard())void load(e.target.value)}}>{!reviews.some(r=>r.id===drawing.id)&&<option value={drawing.id}>{drawing.name}</option>}{reviews.map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select><span className="edAccess">{drawing.access==='view'?'View only':drawing.access==='review'?'Reviewer':'Owner'}</span><button className="btn" onClick={()=>{if(discard())void load(drawing.id)}}><RefreshCw size={15}/>Refresh</button>{editable&&<label className="btn edUpload"><Upload size={15}/>Import feedback PDF<input aria-label="Import feedback PDF" type="file" accept="application/pdf,.pdf" disabled={saving||busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void importFeedback(file)}}/></label>}<button className="btn" onClick={()=>setShare(true)}><Share2 size={15}/>Share</button><details className="edExports"><summary className="btn"><Download size={15}/>Export</summary><div>{([['pdf','Review PDF (editable comments)'],['report','PDF correction report'],['docx','Corrections in Word'],['html','Drawing review (HTML)'],['details','Edit front page']] as [ExportFormat,string][]).map(([format,label])=><button key={format} onClick={()=>{if(dirty){setError('Save the comment before exporting.');return;}setExportFormat(format)}}>{label}</button>)}<a href={`/api/e-design/${drawing.id}/export/csv`}>Correction list (CSV)</a><a href={`/api/e-design/${drawing.id}/original`}>Original PDF</a></div></details></div>
   <div className="edToolbar" role="toolbar" aria-label="Drawing review tools"><button className="btn" aria-pressed={tool==='select'} onClick={()=>setTool('select')}><MousePointer2 size={16}/>Select / move</button>{kinds.map(({id,label,Icon})=><button disabled={!editable} key={id} style={{'--ed-tool':colours[id]} as CSSProperties} className="btn edTool" aria-pressed={tool===id} onClick={()=>setTool(id)}><Icon size={16}/>{label}</button>)}<label className="edToolPicker">Drawing tool<select aria-label="Markup shape" value={shape} onChange={e=>{setShape(e.target.value as Shape);if(tool==='select')setTool('modify')}}>{shapeOptions.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><label className="edToolbarColour">Colour<input type="color" aria-label="New markup colour" value={inkColor} disabled={!editable} onChange={e=>setInkColor(e.target.value)}/></label><button className="btn" aria-label="Undo review change" title="Undo (Ctrl+Z)" disabled={!editable||saving||busy||(!edits.current.past.length&&(!drawing.commands?.undo||dirty))} onClick={()=>void travel('undo')}><Undo2 size={16}/>Undo</button><button className="btn" aria-label="Redo review change" title="Redo (Ctrl+Y / Ctrl+Shift+Z)" disabled={!editable||saving||busy||(!edits.current.future.length&&(!drawing.commands?.redo||dirty))} onClick={()=>void travel('redo')}><Redo2 size={16}/>Redo</button><div className="edToolSpacer"/><button className="btn" onClick={()=>setZoom(v=>Math.max(50,(v||100)-25))} aria-label="Zoom out PDF"><ZoomOut size={16}/></button><select aria-label="PDF zoom" value={zoom} onChange={e=>setZoom(Number(e.target.value))}><option value={0}>Fit width</option>{[50,75,100,125,150,200,300].map(v=><option key={v} value={v}>{v}%</option>)}</select><button className="btn" onClick={()=>setZoom(v=>Math.min(300,(v||100)+25))} aria-label="Zoom in PDF"><ZoomIn size={16}/></button><button className="btn" aria-pressed={comments} onClick={()=>setComments(v=>!v)}>{comments?<PanelRightClose size={16}/>:<PanelRightOpen size={16}/>}Comments ({drawing.marks.length})</button></div>
   <div style={{'--ed-sidebar-width':`${sidebarWidth}px`} as CSSProperties} className={`edLayout ${comments?'hasComments':''} ${pinned?'pinned':'floating'}`}>
    <nav className="edPages" aria-label="Drawing review pages">{drawing.pages.map(p=><button key={p.number} aria-current={page===p.number?'page':undefined} onClick={()=>choosePage(p.number)}><span>Page {p.number}</span><small>{drawing.marks.filter(m=>m.page===p.number).length} comments</small></button>)}</nav>
    <section className="edDrawing"><header><b>{drawing.name}</b><span>Page {page} / {drawing.pages.length}</span></header><div className="edViewport"><div className={`edCanvas ${tool!=='select'&&editable?'drawing':''}`} ref={canvas} style={{width:zoom?`${(info?.width||800)*zoom/100}px`:'100%',aspectRatio:info?`${info.width}/${info.height}`:undefined}}>
     <img src={`/api/e-design/${drawing.id}/page/${page}`} alt={`${drawing.name}, page ${page}`} draggable={false}/>
     <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Drawing markup canvas" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{if(drag.current){setDraft(drag.current.previous);setDirty(drag.current.wasDirty);drag.current=null}}}>
      <defs>{kinds.map(k=><marker id={`ed-arrow-${k.id}`} key={k.id} markerWidth={5} markerHeight={4} refX={4.5} refY={2} orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L4.5 2 L0 4" fill="none" stroke={colours[k.id]}/></marker>)}</defs>{shown.map(markShape)}
     </svg>
     {shown.filter(mark=>mark.callout).map(mark=>{const [x0,y0,x1,y1]=mark.callout!,selected=draft===mark,editing=selected&&popup;return <div key={'text-'+(mark.id||'draft')} className={`edDrawingCallout ${selected?'selected':''} ${mark.status}`} data-mark={mark.id||'draft'} data-callout="true" aria-label="Comment text on drawing" style={{left:`${x0*100}%`,top:`${y0*100}%`,width:`${(x1-x0)*100}%`,height:`${(y1-y0)*100}%`,'--ed-callout':markColor(mark)} as CSSProperties} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{if(drag.current){setDraft(drag.current.previous);setDirty(drag.current.wasDirty);drag.current=null}}} onDoubleClick={()=>{setPopup(true);setFocusText(v=>v+1);}}>
      <small className="edCalloutReference">{reference(mark)}</small>{editing?<textarea ref={textInput} aria-label="Shape comment" maxLength={6000} readOnly={!editable||saving} placeholder="Enter comment here..." value={mark.body} onChange={e=>updateDraft({body:e.target.value})} onPointerDown={e=>e.stopPropagation()} onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();void save();}if(e.key==='Escape'){e.preventDefault();setPopup(false);}}}/>:<div className="edDrawingCalloutText">{mark.body||'Enter comment here...'}</div>}
      {selected&&editable&&<span data-label-resize="true" className="edCalloutResize" aria-label="Resize comment text box"/>}
      {editing&&<div className="edCalloutActions" style={{left:x0>.5?'auto':0,right:x0>.5?0:undefined,...(y1>.8?{top:'auto',bottom:'calc(100% + 9px)'}:{})}} onPointerDown={e=>e.stopPropagation()}><button className="btn primary" disabled={!editable||saving||!dirty||(!mark.body.trim()&&!optionalComment(mark.shape))} onClick={()=>void save()}><Save size={13}/>Save</button><button className="btn" aria-label="Finish editing drawing text" onClick={()=>setPopup(false)}><Check size={13}/>Done</button></div>}
     </div>;})}
     {draft?.page===page&&popup&&!draft.callout&&<section className="edInlineComment" aria-label="Comment beside selected shape" style={{left:`clamp(6px,${draft.box[2]*100}%,calc(100% - 270px))`,top:`${Math.min(.75,draft.box[1])*100}%`,borderColor:markColor(draft)}}>
      <header><b>{reference(draft)} | {draft.id?`Revision ${draft.version}`:'New comment'}</b><button aria-label="Hide shape comment" onClick={()=>setPopup(false)}><X size={14}/></button></header>
      <textarea ref={textInput} aria-label="Shape comment" rows={3} maxLength={6000} readOnly={!editable||saving} placeholder="Comment on this area..." value={draft.body} onChange={e=>updateDraft({body:e.target.value})}/>
      <footer><button className="btn" disabled={!editable||saving||!dirty||(!draft.body.trim()&&!optionalComment(draft.shape))} onClick={()=>void save()}>Save</button><button className="btn" onClick={()=>setComments(true)}><SlidersHorizontal size={14}/>Properties</button>{draft.id&&<button className="btn" disabled={!editable||saving||(!draft.body.trim()&&!optionalComment(draft.shape))} onClick={()=>void save({...draft,status:draft.status==='open'?'resolved':'open'})}>{draft.status==='open'?'Resolve':'Reopen'}</button>}</footer>
     </section>}
    </div></div><footer><span>Choose a colour in the toolbar.</span><span>Draw a bubble to add an arrow and text. Drag text to reposition it; double-click to edit.</span></footer></section>
    {comments&&<ReviewSidebar marks={drawing.marks} visible={visible} draft={draft} revisions={revisions} dirty={dirty} editable={editable} saving={saving} pinned={pinned} search={search} scope={scope} filter={filter} width={sidebarWidth}
     onWidth={value=>{setSidebarWidth(value);userStorage.setItem('usopp_edesign_sidebar_width',String(value))}} onSearch={setSearch} onScope={setScope} onFilter={setFilter}
     onPin={()=>setPinned(v=>{userStorage.setItem('usopp_edesign_pin',String(!v));return !v})} onHide={()=>setComments(false)} onCentre={centreComment} onSelect={select} onUpdate={updateDraft}
     onClose={()=>{if(discard()){setDraft(null);setDirty(false);setPopup(false);resetEdits()}}} onSave={()=>void save()} onDelete={()=>void remove()} onResolve={()=>draft&&void save({...draft,status:draft.status==='open'?'resolved':'open'})} onRestore={v=>void restoreRevision(v)}
     onText={()=>{setPopup(true);setFocusText(v=>v+1)}} onShape={next=>updateDraft({shape:next,callout:next==='cloud-only'?null:regionShape(next)&&draft&&!draft.callout?placeCallout(draft.box):draft?.callout})}
     onCallout={enabled=>{if(!draft)return;updateDraft({shape:!enabled&&draft.shape==='cloud'?'cloud-only':draft.shape,callout:enabled?placeCallout(draft.box):null});setPopup(enabled);setFocusText(v=>v+1)}}/>}
   </div>
  </>}
  {drawing&&<ReviewExportDialog review={drawing} format={exportFormat} onClose={()=>setExportFormat(null)} onSaved={setDrawing}/>}
  <dialog className="edShareDialog" ref={dialog} onCancel={()=>setShare(false)}><header><h2>Share drawing review</h2><button className="btn" aria-label="Close sharing" onClick={()=>setShare(false)}><X size={18}/></button></header>{drawing&&<><p>The review link requires sign-in. To share outside uSOPp, export the editable review PDF; the recipient can comment in a PDF reader and return the saved PDF.</p><label>Review link<input aria-label="Review sharing link" readOnly value={`${location.origin}/#e-design/${drawing.id}`}/></label><button className="btn" onClick={()=>void navigator.clipboard.writeText(`${location.origin}/#e-design/${drawing.id}`).then(()=>setNotice('Review link copied.')).catch(()=>setNotice('Select and copy the review link.'))}>Copy link</button>{drawing.access==='owner'&&<><div className="edShareControls"><label>Reviewer<select aria-label="Share with reviewer" value={person} onChange={e=>setPerson(e.target.value)}><option value="">Select account</option>{people.filter(p=>p.id!==drawing.ownerId).map(p=><option key={p.id} value={p.id}>{p.username} · {p.designation}</option>)}</select></label><label>Access<select aria-label="Reviewer access" value={access} onChange={e=>setAccess(e.target.value)}><option value="review">Edit comments and review</option><option value="view">View only</option></select></label><button className="btn primary" disabled={!person||saving} onClick={()=>void shareWith(Number(person),access)}>Grant access</button></div><h3>Shared accounts</h3>{drawing.members.map(m=><div className="edMember" key={m.user_id}><span>{people.find(p=>p.id===m.user_id)?.username||'Account '+m.user_id} · {m.access}</span><button className="btn" disabled={saving} onClick={()=>void shareWith(m.user_id,'remove')}>Remove access</button></div>)}{!drawing.members.length&&<p>This drawing has not been shared.</p>}</>}<small>Import the returned review PDF to merge feedback, or upload it as a new review. Editing support depends on the recipient's PDF application; printing or flattening removes editable comments.</small></>}</dialog>
 </div>;
}
