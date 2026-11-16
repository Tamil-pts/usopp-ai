import {visualPalettes} from '../../../shared/visualTokens';
﻿import {useMemo,useState} from 'react';
import {Sparkles,ArrowRight,LayoutGrid} from 'lucide-react';
import type {Row} from '../intelligence/api';

const layouts=['Process','Cycle','Timeline','Mind map','Infographic','Comparison'] as const;
type Layout=typeof layouts[number];
const palettes=visualPalettes;
export function visualContent(text:string,layout:Layout,palette:keyof typeof palettes):Row{
 const parts=text.split(/\n+|(?<=[.!?])\s+|;\s*/).map(v=>v.replace(/^\s*(?:[-*•]|\d+[.)])\s*/,'').trim()).filter(Boolean);
 if(!parts.length)throw Error('Paste a paragraph or a list of steps.');
 if(parts.length>24||parts.some(v=>v.length>1800))throw Error('Use up to 24 points, each below 1,800 characters. Split longer content into pages.');
 const colors=palettes[palette],center=layout==='Mind map',radial=layout==='Cycle',nodes:Row[]=[],edges:Row[]=[];
 if(center)nodes.push({id:crypto.randomUUID(),type:'engineering',width:260,height:120,position:{x:430,y:320},data:{kind:'topic',label:'Main idea — edit title',appearance:{fill:colors[0],stroke:'#0f766e',bold:true}}});
 parts.forEach((label,i)=>{const angle=i/parts.length*Math.PI*2-Math.PI/2;const position=radial||center?{x:430+Math.cos(angle)*390,y:320+Math.sin(angle)*300}:layout==='Timeline'?{x:i%2?380:40,y:i*160}:layout==='Process'?{x:(i%3)*340,y:Math.floor(i/3)*210}:{x:(i%2)*370,y:Math.floor(i/2)*190};
 const id=crypto.randomUUID();nodes.push({id,type:'engineering',width:280,height:130,position,data:{kind:'process',label,appearance:{fill:colors[i%colors.length],stroke:'#0f766e',font_size:15,shadow:true}}});
 if(center)edges.push({id:crypto.randomUUID(),source:nodes[0].id,target:id,type:'smoothstep'});
 else if(i&&['Process','Timeline','Cycle'].includes(layout))edges.push({id:crypto.randomUUID(),source:nodes[i-1].id,target:id,type:'smoothstep',markerEnd:{type:'arrowclosed'}});
 });
 if(radial&&nodes.length>1)edges.push({id:crypto.randomUUID(),source:nodes.at(-1)!.id,target:nodes[0].id,type:'smoothstep',markerEnd:{type:'arrowclosed'}});
 return {nodes,edges,visual_assist:{source_text:text,layout,palette,method:'local sentence layout',version:1}};
}
export function VisualAssist({disabled,onApply,initial}:{initial?:Row;disabled:boolean;onApply:(content:Row)=>void}){
 const [open,setOpen]=useState(false),[text,setText]=useState(initial?.source_text||''),[layout,setLayout]=useState<Layout>(initial?.layout||'Process'),[palette,setPalette]=useState<keyof typeof palettes>(initial?.palette||'Ocean'),[error,setError]=useState('');
 const preview=useMemo(()=>{try{return visualContent(text,layout,palette);}catch{return null;}},[text,layout,palette]);
 return <section className="visual-assist"><button type="button" className="btn" aria-expanded={open} onClick={()=>setOpen(!open)}><Sparkles size={17}/>Chopper Visual Assist · Text to Visual</button>{open&&<div className="visual-assist-body"><div><h4>Turn your text into an editable visual</h4><p>Paste a paragraph or one point per line. Choose a layout, review it, then edit every shape and connection.</p><textarea aria-label="Text to visualize" rows={5} maxLength={20000} value={text} onChange={e=>setText(e.target.value)} placeholder="Capture requirements. Plan the work. Develop and validate. Review and release."/><small>Local layout generation keeps your original wording. Connections show text order; review engineering relationships before use.</small></div><div><div className="visual-layouts">{layouts.map(v=><button type="button" className="btn" key={v} aria-pressed={layout===v} onClick={()=>setLayout(v)}><LayoutGrid size={14}/>{v}</button>)}</div><label>Color palette <select value={palette} onChange={e=>setPalette(e.target.value as keyof typeof palettes)}>{Object.keys(palettes).map(v=><option key={v}>{v}</option>)}</select></label>{preview&&<div className="visual-preview" aria-label="Visual layout preview"><svg viewBox="-100 -100 1250 1000">{preview.edges.map((e:Row)=>{const a=preview.nodes.find((n:Row)=>n.id===e.source),b=preview.nodes.find((n:Row)=>n.id===e.target);return <line key={e.id} x1={a.position.x+140} y1={a.position.y+65} x2={b.position.x+140} y2={b.position.y+65} stroke="#94a3b8" strokeWidth="5"/>;})}{preview.nodes.map((n:Row)=><g key={n.id}><rect x={n.position.x} y={n.position.y} width="280" height="130" rx="20" fill={n.data.appearance.fill} stroke="#0f766e"/><text x={n.position.x+15} y={n.position.y+65} fontSize="21">{n.data.label.slice(0,21)}{n.data.label.length>21?'…':''}</text></g>)}</svg></div>}<button type="button" className="btn primary" disabled={disabled||!text.trim()} onClick={()=>{try{onApply(visualContent(text,layout,palette));setOpen(false);setError('');}catch(e){setError((e as Error).message);}}}><ArrowRight size={16}/>Use this visual</button>{error&&<p role="alert">{error}</p>}</div></div>}</section>;
}
