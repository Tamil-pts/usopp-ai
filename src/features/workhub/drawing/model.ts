import {visualFonts} from '../../../shared/visualTokens';
import {artwork} from './artwork';
import catalogue from '../../../../knowledge/master/drawing_libraries.json';
import type {Row} from '../intelligence/api';

export const libraries=[artwork,...catalogue.groups] as Row[];
export const fonts=visualFonts;
export const themes={Teal:{fill:'#e7f5f4',stroke:'#087f83',text:'#17344b'},Blue:{fill:'#eaf2ff',stroke:'#2864c5',text:'#19385b'},Amber:{fill:'#fff4ce',stroke:'#ac7300',text:'#493700'},Mono:{fill:'#ffffff',stroke:'#263445',text:'#17202a'}};
export const paper={A4:[794,1123],A3:[1123,1587],A2:[1587,2245]};
export function normalize(content:Row):Row{
 const workspace={schema_version:2,pages:[{id:'page-1',name:'Page 1',paper:'infinite',orientation:'portrait',background:'#ffffff'}],layers:[{id:'default',name:'Drawing',visible:true,locked:false}],grid:true,snap:true,snap_objects:true,rulers:false,units:'px',...content.workspace};
 return {...structuredClone(content),workspace,nodes:(content.nodes||[]).map((n:Row)=>({id:n.id,type:'engineering',width:n.width||240,height:n.height||100,position:{x:n.position?.x||0,y:n.position?.y||0},data:{...n.data,page_id:n.data?.page_id||workspace.pages[0].id,layer_id:n.data?.layer_id||'default'}})),edges:(content.edges||[]).map((e:Row)=>({id:e.id,source:e.source,target:e.target,sourceHandle:e.sourceHandle,targetHandle:e.targetHandle,type:['straight','default','smoothstep','routed'].includes(e.type)?e.type:'smoothstep',label:e.label||'',data:e.data?.waypoints?{waypoints:e.data.waypoints}:undefined,markerEnd:'markerEnd' in e?(e.markerEnd?{type:'arrowclosed'}:null):content.diagram_type==='mindmap'?null:{type:'arrowclosed'},style:{stroke:/^#[a-f0-9]{6}$/i.test(e.style?.stroke)?e.style.stroke:'#087f83',strokeWidth:Math.max(0,Math.min(12,Number(e.style?.strokeWidth)||2)),strokeDasharray:['8 5','2 4'].includes(e.style?.strokeDasharray)?e.style.strokeDasharray:''}}))};
}
export function validateImport(content:Row){
 if(!Array.isArray(content.nodes)||!Array.isArray(content.edges)||content.nodes.length>500||content.edges.length>1500)throw Error('Choose a uSOPp.ai drawing with up to 500 objects and 1,500 connections.');
 const ids=new Set<string>();
 for(const n of content.nodes){if(!/^[A-Za-z0-9_-]{1,80}$/.test(n.id)||ids.has(n.id)||typeof n.data?.label!=='string'||n.data.label.length>2000)throw Error('Drawing objects need unique IDs and bounded text labels.');ids.add(n.id);
  if(!['x','y'].every(k=>Number.isFinite(n.position?.[k])&&Math.abs(n.position[k])<=100000))throw Error('Invalid drawing position.');
  const s=n.data.appearance||{};
  for(const k of ['fill','stroke','text','gradient'])if(s[k]&&!/^#[a-f0-9]{6}$/i.test(s[k]))throw Error('Use hexadecimal style colors. External resources are unsupported.');
  if(s.font&&!fonts.includes(s.font))throw Error('Unsupported font.');
  if(n.data.symbol)safeLibrary({schema_version:1,libraries:[{...n.data.symbol,id:n.data.symbol.library_id,name:'Imported drawing',symbols:[{id:n.data.symbol.id,name:n.data.label,asset:n.data.symbol.asset}]}]});
 }
 for(const e of content.edges)if(!ids.has(e.source)||!ids.has(e.target)||e.label!=null&&typeof e.label!=='string')throw Error('A drawing connector refers to an absent object or invalid label.');
 if(content.workspace){const ws=content.workspace;if(ws.schema_version!==2||!Array.isArray(ws.pages)||!ws.pages.length||ws.pages.length>20||!Array.isArray(ws.layers)||!ws.layers.length||ws.layers.length>30)throw Error('Unsupported drawing pages or layers.');for(const p of ws.pages)if(p.background&&!/^#[a-f0-9]{6}$/i.test(p.background))throw Error('Use hexadecimal page colors.');}
}
export const dimensions=(node:Row)=>({w:Number(node.width||240),h:Number(node.height||100)});
export const editable=(node:Row,ws:Row)=>!node.data.locked&&!ws.layers.find((l:Row)=>l.id===node.data.layer_id)?.locked;
export function visible(node:Row,ws:Row,page:string){return node.data.page_id===page&&ws.layers.find((l:Row)=>l.id===node.data.layer_id)?.visible!==false;}
export function align(nodes:Row[],ids:Set<string>,mode:string){
 const picked=nodes.filter(n=>ids.has(n.id));if(picked.length<2)return nodes;
 const minX=Math.min(...picked.map(n=>n.position.x)),minY=Math.min(...picked.map(n=>n.position.y)),maxX=Math.max(...picked.map(n=>n.position.x+dimensions(n).w)),maxY=Math.max(...picked.map(n=>n.position.y+dimensions(n).h));
 const ordered=[...picked].sort((a,b)=>mode==='distribute-y'?a.position.y-b.position.y:a.position.x-b.position.x),horizontal=mode==='distribute-x';
 const gap=((horizontal?maxX-minX:maxY-minY)-picked.reduce((sum,n)=>sum+(horizontal?dimensions(n).w:dimensions(n).h),0))/(picked.length-1);
 let cursor=horizontal?minX:minY;const points=new Map<string,Row>();
 for(const n of ordered){const {w,h}=dimensions(n);const p={...n.position};
  if(mode==='left')p.x=minX;if(mode==='right')p.x=maxX-w;if(mode==='top')p.y=minY;if(mode==='bottom')p.y=maxY-h;
  if(mode==='center-x')p.x=(minX+maxX-w)/2;if(mode==='center-y')p.y=(minY+maxY-h)/2;
  if(mode.startsWith('distribute')){p[horizontal?'x':'y']=cursor;cursor+=(horizontal?w:h)+gap;}points.set(n.id,p);
 }
 return nodes.map(n=>points.has(n.id)?{...n,position:points.get(n.id)}:n);
}
export function cloned(nodes:Row[],edges:Row[],ids:Set<string>){
 const selected=nodes.filter(n=>ids.has(n.id)),mapping=new Map(selected.map(n=>[n.id,crypto.randomUUID()]));
 const groupMap=new Map(selected.filter(n=>n.data.group_id).map(n=>[n.data.group_id,crypto.randomUUID()]));
 return {nodes:selected.map(n=>({...structuredClone(n),id:mapping.get(n.id),selected:true,position:{x:n.position.x+30,y:n.position.y+30},data:{...n.data,locked:false,...(n.data.group_id?{group_id:groupMap.get(n.data.group_id)}:{})}})),edges:edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>({...structuredClone(e),id:crypto.randomUUID(),source:mapping.get(e.source),target:mapping.get(e.target)}))};
}
export function safeLibrary(value:Row):Row[]{
 if(value.schema_version!==1||!Array.isArray(value.libraries)||!value.libraries.length||value.libraries.length>30)throw Error('Import a version 1 library manifest with 1–30 libraries.');
 for(const l of value.libraries){
  if(!l.id||!l.name||!l.source||!l.license||!l.version||!Array.isArray(l.symbols)||l.symbols.length>150)throw Error('Each library needs an ID, name, source, licence, version and up to 150 symbols.');
  for(const s of l.symbols){if(!s.id||!s.name||!['rect','roundrect','ellipse','diamond','io','document','subprocess','path'].includes(s.asset?.shape))throw Error('Use supported geometric SVG symbols.');
   if(s.asset.path&&(!/^[MmLlHhVvCcSsQqTtAaZz0-9., +\-eE]+$/.test(s.asset.path)||s.asset.path.length>12000))throw Error('Invalid bounded SVG path. Scripts, external images and embedded HTML are unsupported.');
  }
 }
 return value.libraries;
}
export function symbolData(library:Row,symbol:Row){return {kind:'process',label:symbol.name,symbol:{id:symbol.id,library_id:library.id,version:library.version,source:library.source,license:library.license,asset:structuredClone(symbol.asset),ports:structuredClone(symbol.ports||[])}};}
export function connectionIssues(nodes:Row[],edges:Row[]){
 const byId=new Map(nodes.map(n=>[n.id,n]));const messages:string[]=[];
 for(const e of edges){const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b){messages.push('Missing node on connection '+e.id);continue;}
  if(a.data.page_id!==b.data.page_id)messages.push('Cross-page connection requires explicit reference: '+e.id);
  const ap=a.data.symbol?.ports?.find((p:Row)=>p.id===e.sourceHandle),bp=b.data.symbol?.ports?.find((p:Row)=>p.id===e.targetHandle);
  if(ap?.domain&&bp?.domain&&ap.domain!==bp.domain)messages.push('Port domain mismatch: '+e.id);
 }
 return messages;
}
