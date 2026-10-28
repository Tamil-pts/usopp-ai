import type {HubRow as Row} from '../projectApi';
export type Run={text:string;bold?:boolean;italic?:boolean;underline?:boolean;color?:string;font_size?:number;field?:string};
export type Cursor={blockId:string;textKey:string;cellId?:string;start:number;end:number;quote:string};
export const id=()=>crypto.randomUUID().replaceAll('-','');
export const copy=<T,>(v:T):T=>structuredClone(v);
export const plain=(runs:Run[]=[])=>runs.map(r=>r.text||'').join('');
export const defaultStyle=()=>({align:'left',color:'#243b53',background:'transparent',border_color:'#ccd7e2',border_width:0,border_style:'solid',padding:2,width:100,height:0,x:0,space_before:2,space_after:3,font:'Arial',font_size:11,line_height:1.45,bold:false,italic:false,underline:false,visible:true,keep_together:false,inherit_font:true,inherit_color:true,inherit_spacing:true});
export const fields=[['project_name','Project name'],['project_number','Project number'],['customer','Customer / Client'],['machine','Machine / System'],['document_number','Document number'],['document_title','Document title'],['revision','Revision'],['status','Document status'],['prepared_by','Prepared by'],['reviewed_by','Reviewed by'],['approved_by','Approved by'],['approval_date','Approval date'],['company','Company'],['department','Department'],['date','Prepared date'],['page','Page number'],['pages','Total pages'],['section_title','Section title']];
export const fonts=['Arial','Calibri','Times New Roman','Georgia','Verdana','Courier New','Noto Sans Tamil'];
export function table(rows=3,columns=3,checklist=false){
 const headings=checklist?['Item','Pass','Fail','Not Applicable','Remarks']:Array.from({length:columns},(_,i)=>'Column '+(i+1));
 const cells=[];
 for(let row=0;row<rows;row++)for(let col=0;col<columns;col++)cells.push({id:id(),row,col,rowspan:1,colspan:1,runs:[{text:row===0?headings[col]:checklist&&col>0&&col<4?'☐':''}],style:{...defaultStyle(),font_size:10,inherit_font:false,space_before:0,space_after:0,bold:row===0}});
 return {rows,columns,header_rows:1,widths:Array(columns).fill(100/columns),cells,highlight:checklist,border_color:'#c7d4e2',border_width:0.4,header_background:'#edf3f9'};
}
export function newBlock(type:string,metadata?:Row):Row{
 const b:Row={id:id(),type,style:defaultStyle(),data:{runs:[{text:''}]}};
 if(type==='heading'||type==='cover'){b.data.level=type==='cover'?1:2;b.style={...b.style,font_size:type==='cover'?25:16,bold:true,inherit_font:false,color:'#235789',inherit_color:false};}
 if(type==='panel'){b.data.title='Information';b.style={...b.style,background:'#f0f6fc',border_width:0.3,padding:4};}
 if(type==='table')b.data=table();
 if(type==='checklist')b.data=table(4,5,true);
 if(type==='image')b.data={file_id:'',caption:'',alt:'',source:'file'};
 if(type==='signature')b.data={label:'Signature',name:'',role:'',date:'',file_id:'',runs:[]};
 if(type==='approval')b.data={label:'Recorded review and approval',name:'',role:'',date:'',file_id:'',runs:[]};
 if(type==='checkbox')b.data.checked=false;
 if(type==='chart')b.data={title:'Chart',kind:'bar',labels:[],values:[]};
 if(type==='flowchart'){const a=id(),z=id();b.data={nodes:[{id:a,label:'Start',kind:'start',x:50,y:20},{id:z,label:'End',kind:'end',x:50,y:160}],edges:[{source:a,target:z,label:''}]};}
 if(type==='line'){b.data={};b.style.border_width=0.4;b.style.space_after=4;}
 if(type==='field')b.data={field:'project_name'};
 if(type==='page_break'||type==='metadata'||type==='native_flowchart')b.data={};
 if(type==='section_break')b.data={title:'New section',page:copy(metadata?.layout.page||{}),header:copy(metadata?.layout.header||{}),footer:copy(metadata?.layout.footer||{})};
 return b;
}
export function sliceRuns(runs:Run[],from:number,to=Infinity):Run[]{let position=0;const result:Run[]=[];for(const r of runs){const a=Math.max(0,from-position),b=Math.min(r.text.length,to-position);if(b>a)result.push({...r,text:r.text.slice(a,b)});position+=r.text.length;}return result;}
export function setNativeText(content:Row,binding:string,text:string){
 if(binding.startsWith('section:')){const [,key,field]=binding.split(':');const section=(content.sections||[]).find((s:Row,i:number)=>String(s.id??i)===key);if(section)section[field]=text;}
 else content[binding]=text;
}
export function syncNativeText(content:Row,layout:Row,binding:string){setNativeText(content,binding,layout.blocks.filter((b:Row)=>b.type==='native_text'&&b.data.binding===binding).map((b:Row)=>plain(b.data.runs)).join(''));}
export function updateText(content:Row,layout:Row,cursor:Cursor,runs:Run[]){
 const b=layout.blocks.find((x:Row)=>x.id===cursor.blockId);if(!b)return;
 if(cursor.cellId&&b.type==='native_table'){
  const rows=content[b.data.binding]||[],columns=cursor.cellId.split(':'),field=columns.pop()!,rowKey=columns.join(':');
  if(['actual_result','result'].includes(field))return;
  const i=rows.findIndex((r:Row|string,index:number)=>String(typeof r==='string'?index:r.id??index)===rowKey);if(i<0)return;
  const text=plain(runs);
  if(b.data.binding==='participants')rows[i]=text;
  else rows[i][field]=field.endsWith('_ids')?text.split(',').map(v=>v.trim()).filter(Boolean):text;
 }else if(cursor.cellId&&['table','checklist'].includes(b.type)){const c=b.data.cells.find((c:Row)=>c.id===cursor.cellId);if(c)c.runs=runs;}
 else if('runs' in b.data){b.data.runs=runs;if(b.type==='native_text')syncNativeText(content,layout,b.data.binding);}
}
export function insert(content:Row,layout:Row,block:Row,cursor:Cursor|null){
 const index=layout.blocks.findIndex((b:Row)=>b.id===cursor?.blockId),current=layout.blocks[index];
 if(current&&cursor&&!cursor.cellId&&['paragraph','heading','cover','panel','native_text'].includes(current.type)){
  const all=current.data.runs||[];const end=plain(all).length;const before=sliceRuns(all,0,cursor.start),after=sliceRuns(all,cursor.end);
  const pieces:Row[]=[];if(cursor.start>0)pieces.push({...current,data:{...current.data,runs:before}});
  pieces.push(block);
  if(cursor.end<end){const tail=copy(current);tail.id=pieces.some(b=>b.id===current.id)?id():current.id;tail.data.runs=after;if(['heading','cover'].includes(tail.type)){tail.type='paragraph';tail.style=defaultStyle();}pieces.push(tail);}
  if(!pieces.some(b=>b.id===current.id)&&current.type==='native_text'){const tail=copy(current);tail.data.runs=[];pieces.push(tail);}
  layout.blocks.splice(index,1,...pieces);
  if(current.type==='native_text')syncNativeText(content,layout,current.data.binding);
 }else layout.blocks.splice(index<0?layout.blocks.length:index+1,0,block);
}
export function duplicate(block:Row){const next=copy(block);next.id=id();if(['table','checklist'].includes(next.type))for(const c of next.data.cells)c.id=id();if(next.type==='native_text'){next.type='paragraph';delete next.data.binding;delete next.data.source_hash;}return next;}
export function resizeTable(data:Row,rows:number,columns:number){
 rows=Math.max(1,Math.min(100,rows));columns=Math.max(1,Math.min(12,columns));
 const old=copy(data);data.rows=rows;data.columns=columns;data.header_rows=Math.min(data.header_rows,rows);data.widths=Array(columns).fill(100/columns);data.cells=[];
 for(let y=0;y<rows;y++)for(let x=0;x<columns;x++){
  const previous=old.cells.find((c:Row)=>c.row===y&&c.col===x);data.cells.push(previous?{...previous,rowspan:1,colspan:1}:{id:id(),row:y,col:x,rowspan:1,colspan:1,runs:[{text:''}],style:defaultStyle()});
 }
}
export function addTableRow(data:Row){const row=data.rows++;for(let x=0;x<data.columns;x++)data.cells.push({id:id(),row,col:x,rowspan:1,colspan:1,runs:[{text:''}],style:{...defaultStyle(),font_size:10,inherit_font:false}});}
export function mergeCells(data:Row,ids:string[]){
 const selected=data.cells.filter((c:Row)=>ids.includes(c.id));if(selected.length<2)throw Error('Select at least two adjacent cells with Shift-click.');
 const top=Math.min(...selected.map((c:Row)=>c.row)),left=Math.min(...selected.map((c:Row)=>c.col)),bottom=Math.max(...selected.map((c:Row)=>c.row+c.rowspan-1)),right=Math.max(...selected.map((c:Row)=>c.col+c.colspan-1));
 if(top<data.header_rows&&bottom>=data.header_rows)throw Error('Keep header merges within the header rows.');
 const covered=data.cells.filter((c:Row)=>c.row>=top&&c.col>=left&&c.row+c.rowspan-1<=bottom&&c.col+c.colspan-1<=right);
 if(covered.length!==selected.length||covered.reduce((n:number,c:Row)=>n+c.rowspan*c.colspan,0)!==(bottom-top+1)*(right-left+1))throw Error('Select a complete rectangular group of cells.');
 const first=copy(selected.sort((a:Row,b:Row)=>a.row-b.row||a.col-b.col)[0]);first.row=top;first.col=left;first.rowspan=bottom-top+1;first.colspan=right-left+1;first.runs=selected.flatMap((c:Row,i:number)=>[...(i?[{text:'\n'}]:[]),...c.runs]);
 data.cells=data.cells.filter((c:Row)=>!ids.includes(c.id));data.cells.push(first);
}
export function splitCell(data:Row,cellId:string){
 const c=data.cells.find((c:Row)=>c.id===cellId);if(!c)return;
 for(let y=c.row;y<c.row+c.rowspan;y++)for(let x=c.col;x<c.col+c.colspan;x++)if(y!==c.row||x!==c.col)data.cells.push({id:id(),row:y,col:x,rowspan:1,colspan:1,runs:[{text:''}],style:copy(c.style)});
 c.rowspan=1;c.colspan=1;
}
export function nativeRow(content:Row,binding:string,reserved:string[]=[]){
 const rows=content[binding]||(content[binding]=[]);
 if(binding==='participants'){rows.push('');return;}
 const n=Math.max(0,...[...rows,...reserved.map(id=>({id}))].map((r:Row)=>Number(String(r.id||'').match(/\d+$/)?.[0]||0)))+1;
 const row:Row={id:(binding==='requirements'?'FR-':binding==='cases'?'TC-':binding==='changes'?'CN-':'ITEM-')+String(n).padStart(3,'0'),source_ids:[]};
 if(binding==='requirements')Object.assign(row,{title:'',description:'',trigger:'',expected_behavior:'',acceptance_criteria:'',subsystem:'',mandatory:true,change:'new'});
 else if(binding==='cases')Object.assign(row,{objective:'',procedure:'',expected_result:'',acceptance_criteria:'',requirement_ids:[],mandatory:true});
 else if(binding==='changes')Object.assign(row,{summary:'',existing_behavior:'',expected_behavior:'',verification:'',requirement_ids:[]});
 else if(binding==='sections')Object.assign(row,{heading:'Section',text:''});
 else Object.assign(row,{text:'',topic:'',responsible:'',target_date:'',status:'Open',question:''});
 rows.push(row);
}
export function readRuns(element:Node):Run[]{
 const result:Run[]=[];
 const walk=(node:Node,style:Partial<Run>={})=>{
  if(node.nodeType===Node.TEXT_NODE){if(node.textContent)result.push({...style,text:node.textContent});return;}
  if(!(node instanceof element.ownerDocument!.defaultView!.HTMLElement))return;
  const e=node as HTMLElement;if(e.dataset.placeholder)return;
  if(e.dataset.field){result.push({...style,field:e.dataset.field,text:e.textContent||''});return;}
  if(e.tagName==='BR'){result.push({...style,text:'\n'});return;}
  const next:Partial<Run>={...style};if(['B','STRONG'].includes(e.tagName)||e.style.fontWeight==='bold'||Number(e.style.fontWeight)>=600)next.bold=true;
  if(['I','EM'].includes(e.tagName)||e.style.fontStyle==='italic')next.italic=true;if(e.tagName==='U'||e.style.textDecoration.includes('underline'))next.underline=true;
  if(e.style.color){const rgb=e.style.color.match(/\d+/g);next.color=rgb&&rgb.length>=3?'#'+rgb.slice(0,3).map(v=>Number(v).toString(16).padStart(2,'0')).join(''):e.style.color;}
  if(e.style.fontSize){const n=parseFloat(e.style.fontSize);if(Number.isFinite(n))next.font_size=e.style.fontSize.endsWith('px')?n*.75:n;}
  const children=[...e.childNodes];children.forEach((child,i)=>{if(i&&child.nodeType===Node.ELEMENT_NODE&&['DIV','P'].includes((child as Element).tagName))result.push({...next,text:'\n'});walk(child,next);});
 };
 [...element.childNodes].forEach(n=>walk(n));return result.length?result:[{text:''}];
}
export function unlocked(metadata:Row,elementId:string,kind='content'){return !metadata.locks.some((l:Row)=>l.kind===kind&&[elementId,'document'].includes(l.element_id));}
export function pruneAttachments(content:Row,layout:Row){
 if(!content.field_files)return;
 const allowed=new Set(['summary','purpose','scope','acceptance_summary','na_reason','meeting_subject','meeting_date','meeting_mode','location','agenda','follow_up']);
 for(const [prefix,binding,columns] of [['requirement','requirements',['title','description','trigger','expected_behavior','subsystem','acceptance_criteria']],['case','cases',['objective','procedure','expected_result','acceptance_criteria','actual','observations']],['change','changes',['summary','existing_behavior','expected_behavior','plc_references','impact','before_evidence','after_evidence','verification']],['section','sections',['text']]] as [string,string,string[]][])for(const row of content[binding]||[])for(const col of columns)allowed.add(prefix+'/'+row.id+'/'+col);
 for(const b of layout.blocks){const base='element/'+b.id;allowed.add(base);for(const cell of b.data.cells||[])allowed.add(base+'/cell/'+cell.id);if(b.type==='metadata')for(let y=0;y<7;y++)for(let x=0;x<2;x++)allowed.add(base+'/cell/meta-'+y+'-'+x);if(b.type==='native_table')for(const [index,row] of (content[b.data.binding]||[]).entries())for(const field of typeof row==='string'?['text']:Object.keys(row))allowed.add(base+'/cell/'+(row.id??index)+':'+field);}
 content.field_files=Object.fromEntries(Object.entries(content.field_files).filter(([key,value])=>allowed.has(key)&&Array.isArray(value)&&value.length));
}
