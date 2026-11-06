import {useState} from 'react';
import {normalize,dimensions,visible} from './model';
import {SymbolArt} from './Symbol';
import type {Row} from '../intelligence/api';
export function DrawingPreview({flow}:{flow:Row}){
 const content=normalize(flow),[page,setPage]=useState(content.workspace.pages[0].id),nodes:Row[]=content.nodes.filter((n:Row)=>visible(n,content.workspace,page)),byId=new Map(nodes.map(n=>[n.id,n]));
 const lx=Math.min(0,...nodes.map(n=>n.position.x))-30,ly=Math.min(0,...nodes.map(n=>n.position.y))-30,w=Math.max(500,...nodes.map(n=>n.position.x+dimensions(n).w))-lx+30,h=Math.max(260,...nodes.map(n=>n.position.y+dimensions(n).h))-ly+30;
 return <div>{content.workspace.pages.length>1&&<label>Drawing page<select value={page} onChange={e=>setPage(e.target.value)}>{content.workspace.pages.map((p:Row)=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}<svg className="frd-flow-preview" role="img" aria-label="Saved drawing preview" viewBox={`${lx} ${ly} ${w} ${h}`}>
 {content.edges.map((e:Row)=>{const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b)return null;const {w:aw,h:ah}=dimensions(a),{h:bh}=dimensions(b);return <g key={e.id}><path d={`M${a.position.x+aw} ${a.position.y+ah/2} L${b.position.x} ${b.position.y+bh/2}`} fill="none" stroke={e.style?.stroke||'#087f83'} strokeWidth={e.style?.strokeWidth||2}/></g>;})}
 {nodes.map(n=>{const {w,h}=dimensions(n),s=n.data.appearance||{},asset=n.data.symbol?.asset||{shape:n.data.kind==='decision'?'diamond':'rect'};return <g key={n.id} transform={`translate(${n.position.x},${n.position.y})`} opacity={s.opacity??1}><g transform={`translate(${w/2},${h/2}) rotate(${s.rotation||0}) scale(${s.flip_x?-1:1},${s.flip_y?-1:1}) translate(${-w/2},${-h/2})`}><svg width={w} height={h} viewBox="0 0 100 100" preserveAspectRatio="none"><SymbolArt asset={asset} fill={s.fill||n.data.color||'#e7f5f4'} stroke={s.stroke||'#087f83'} width={s.stroke_width||1.5}/></svg></g>{!n.data.hide_label&&<text x={w/2} y={h/2} fontFamily={s.font||'Arial'} fontSize={s.font_size||14} fill={s.text||'#17344b'} textAnchor="middle">{String(n.data.label||'').slice(0,70)}</text>}</g>;})}</svg></div>;
}
