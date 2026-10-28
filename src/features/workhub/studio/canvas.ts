import type {RefObject} from 'react';
import type {HubRow as Row} from '../projectApi';
import {plain,readRuns,unlocked,type Cursor,type Run} from './model';

type Options={frame:RefObject<HTMLIFrameElement|null>;metadata:()=>Row;layout:()=>Row;selected:()=>string;select:(id:string,cursor:Cursor|null,cells?:string[])=>void;text:(cursor:Cursor,runs:Run[])=>void;move:(id:string,target:string)=>void;insert:(type:string,target?:string)=>void;resize:(id:string,width:number,height:number)=>void;toggle:(id:string,cell?:string)=>void;save:()=>Promise<unknown>;blur:()=>void;error:(message:string)=>void};
export function createCanvas(options:Options){
 let detach=()=>{},range:Range|null=null,current:Cursor|null=null,activeDocument:Document|null=null;
 const selection=()=>{
  const doc=activeDocument,sel=doc?.getSelection();if(!doc||!sel?.rangeCount)return;
  const r=sel.getRangeAt(0),node=r.startContainer.nodeType===1?r.startContainer as Element:r.startContainer.parentElement;
  const el=node?.closest<HTMLElement>('[data-text-key]'),endNode=r.endContainer.nodeType===1?r.endContainer as Element:r.endContainer.parentElement;
  const block=node?.closest<HTMLElement>('[data-block-id]');if(!block)return;
  if(!el||endNode?.closest('[data-text-key]')?.getAttribute('data-text-key')!==el.dataset.textKey){current=null;options.select(block.dataset.blockId!,null);return;}
  const key=el.dataset.textKey!,all=[...doc.querySelectorAll<HTMLElement>('[data-text-key]')].filter(e=>e.dataset.textKey===key),heading=!!el.closest('thead');
  const earlier=heading?[]:all.slice(0,all.indexOf(el));
  const prefix=doc.createRange();prefix.selectNodeContents(el);prefix.setEnd(r.startContainer,r.startOffset);const before=doc.createElement('div');before.append(prefix.cloneContents());
  const selected=doc.createElement('div');selected.append(r.cloneContents());
  const start=earlier.reduce((n,e)=>n+plain(readRuns(e)).length,0)+plain(readRuns(before)).length,quote=plain(readRuns(selected));
  current={blockId:block.dataset.blockId!,textKey:key,...(key.includes('|cell:')?{cellId:key.slice(key.indexOf('|cell:')+6)}:{}),start,end:start+quote.length,quote};range=r.cloneRange();options.select(current.blockId,current,current.cellId?[current.cellId]:[]);
 };
 const serialize=(el:HTMLElement)=>{
  const doc=activeDocument,key=el.dataset.textKey;if(!doc||!key)return;
  const block=el.closest<HTMLElement>('[data-block-id]');if(!block)return;
  const all=[...doc.querySelectorAll<HTMLElement>('[data-text-key]')].filter(e=>e.dataset.textKey===key);
  const runs=el.closest('thead')?readRuns(el):all.flatMap(readRuns);
  if(el.closest('thead'))for(const other of all)if(other!==el)other.innerHTML=el.innerHTML;
  const cursor:Cursor={blockId:block.dataset.blockId!,textKey:key,cellId:key.includes('|cell:')?key.slice(key.indexOf('|cell:')+6):undefined,start:current?.start||0,end:current?.end||0,quote:current?.quote||''};
  options.text(cursor,runs);selection();
 };
 const decorate=()=>{
  const doc=activeDocument;if(!doc)return;
  doc.querySelectorAll('.ds-selected').forEach(el=>el.classList.remove('ds-selected'));doc.querySelectorAll('.ds-resize-grip').forEach(el=>el.remove());
  for(const el of doc.querySelectorAll<HTMLElement>('[data-block-id]'))if(el.dataset.blockId===options.selected()){
   el.classList.add('ds-selected');const block=options.layout().blocks.find((b:Row)=>b.id===options.selected());
   if(options.metadata().editable&&block&&unlocked(options.metadata(),block.id,'layout')){const grip=doc.createElement('button');grip.className='ds-resize-grip';grip.type='button';grip.setAttribute('aria-label','Resize element');grip.title='Drag to resize';Object.assign(grip.style,{position:'absolute',right:'-3px',bottom:'-3px',width:'10px',height:'10px',border:'1px solid #fff',background:'#2679c6',cursor:'nwse-resize',zIndex:'8',padding:'0'});el.append(grip);}
  }
 };
 const attach=()=>{
  detach();const doc=options.frame.current?.contentDocument;if(!doc)return;activeDocument=doc;
  const removals:(()=>void)[]=[];
  const on=(type:string,handler:(event:any)=>void)=>{doc.addEventListener(type,handler);removals.push(()=>doc.removeEventListener(type,handler));};
  on('selectionchange',selection);on('mouseup',selection);on('keyup',selection);
  on('input',(e:Event)=>{const target=(e.target as Element).closest<HTMLElement>('[data-text-key]');if(target)serialize(target);});
  on('focusout',()=>options.blur());
  on('paste',(e:ClipboardEvent)=>{const el=(e.target as Element).closest<HTMLElement>('[contenteditable=true]');if(!el)return;e.preventDefault();doc.execCommand('insertText',false,e.clipboardData?.getData('text/plain')||'');serialize(el);});
  on('click',(e:MouseEvent)=>{const el=(e.target as Element).closest<HTMLElement>('[data-block-id]');if(!el)return;const cell=(e.target as Element).closest<HTMLElement>('[data-cell-id]'),text=(e.target as Element).closest('[data-text-key]');
   const b=options.layout().blocks.find((b:Row)=>b.id===el.dataset.blockId);if(options.metadata().editable&&b&&unlocked(options.metadata(),b.id,'content')&&((e.target as Element).closest('.ds-checkbox')||b.type==='checklist'&&cell&&['☐','☑'].includes(cell.innerText.trim()))){options.toggle(b.id,cell?.dataset.cellId);return;}
   if(!text){current=null;options.select(el.dataset.blockId!,null,cell?.dataset.cellId?[cell.dataset.cellId]:[]);}else selection();decorate();
  });
  on('keydown',(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();void options.save().catch(error=>options.error(error.message));}});
  on('dragstart',(e:DragEvent)=>{const grip=(e.target as Element).closest<HTMLElement>('[data-grip]');if(!grip)return;const block=grip.dataset.grip!;if(!options.metadata().editable||!unlocked(options.metadata(),block,'layout')){e.preventDefault();return;}e.dataTransfer?.setData('application/x-studio-block',block);});
  on('dragover',(e:DragEvent)=>{if(e.dataTransfer?.types.some(t=>['application/x-studio-block','application/x-studio-insert'].includes(t)))e.preventDefault();});
  on('drop',(e:DragEvent)=>{const el=(e.target as Element).closest<HTMLElement>('[data-block-id]'),moving=e.dataTransfer?.getData('application/x-studio-block'),adding=e.dataTransfer?.getData('application/x-studio-insert');
   e.preventDefault();if(moving&&el)options.move(moving,el.dataset.blockId!);else if(adding)options.insert(adding,el?.dataset.blockId);else{const text=(e.target as Element).closest<HTMLElement>('[contenteditable=true]');if(text){doc.execCommand('insertText',false,e.dataTransfer?.getData('text/plain')||'');serialize(text);}}
  });
  on('pointerdown',(e:PointerEvent)=>{if(!(e.target as Element).classList.contains('ds-resize-grip'))return;const wrapper=(e.target as Element).closest<HTMLElement>('[data-block-id]');if(!wrapper)return;const block=options.layout().blocks.find((b:Row)=>b.id===wrapper.dataset.blockId),parent=wrapper.parentElement;if(!block||!parent)return;
   e.preventDefault();e.stopPropagation();const bounds=wrapper.getBoundingClientRect(),parentBounds=parent.getBoundingClientRect(),startX=e.clientX,startY=e.clientY,scale=bounds.width/(wrapper.offsetWidth||bounds.width);
   const update=(event:PointerEvent)=>{wrapper.style.width=Math.max(10,Math.min(100-block.style.x,(bounds.width+event.clientX-startX)/parentBounds.width*100))+'%';wrapper.style.minHeight=Math.max(5,(bounds.height+event.clientY-startY)/scale/3.779527559)+'mm';};
   const finish=(event:PointerEvent)=>{doc.removeEventListener('pointermove',update);doc.removeEventListener('pointerup',finish);options.resize(block.id,Math.round(Math.max(10,Math.min(100-block.style.x,(bounds.width+event.clientX-startX)/parentBounds.width*100))),Math.round(Math.max(5,Math.min(500,(bounds.height+event.clientY-startY)/scale/3.779527559))));};doc.addEventListener('pointermove',update);doc.addEventListener('pointerup',finish,{once:true});
  });
  detach=()=>{removals.forEach(fn=>fn());activeDocument=null;range=null;};decorate();
 };
 const format=(command:string,value?:string)=>{const doc=activeDocument;if(!doc||!range||!current)return;const selected=doc.getSelection();selected?.removeAllRanges();selected?.addRange(range);doc.execCommand(command,false,value);const el=[...doc.querySelectorAll<HTMLElement>('[data-text-key]')].find(e=>e.dataset.textKey===current?.textKey&&e.contains(doc.getSelection()?.anchorNode||null));if(el)serialize(el);};
 const focus=(blockId:string)=>{const doc=activeDocument;if(!doc)return;const wrapper=[...doc.querySelectorAll<HTMLElement>('[data-block-id]')].find(e=>e.dataset.blockId===blockId),text=wrapper?.querySelector<HTMLElement>('[contenteditable=true]');wrapper?.scrollIntoView({block:'nearest'});if(text){text.focus();const r=doc.createRange();r.selectNodeContents(text);r.collapse(false);doc.getSelection()?.removeAllRanges();doc.getSelection()?.addRange(r);}options.select(blockId,null);decorate();};
 return {attach,decorate,format,focus,selection,dispose:()=>detach(),cursor:()=>current};
}
