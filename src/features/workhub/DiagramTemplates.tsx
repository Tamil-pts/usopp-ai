import {useEffect,useState} from 'react';
import {hub,type HubRow as Row} from './projectApi';

export function DiagramThumbnail({content}:{content:Row}){
 const nodes:Row[]=content.nodes||[],edges:Row[]=content.edges||[],width=Math.max(400,...nodes.map(n=>n.position.x+260)),height=Math.max(180,...nodes.map(n=>n.position.y+140));
 return <svg viewBox={'-25 -25 '+(width+50)+' '+(height+50)} aria-hidden="true" className="wh-template-thumbnail">{edges.map(e=>{const a=nodes.find(n=>n.id===e.source),b=nodes.find(n=>n.id===e.target);return a&&b?<path key={e.id} d={`M${a.position.x+120} ${a.position.y+90} L${b.position.x+120} ${b.position.y}`} stroke="currentColor" fill="none" strokeWidth="5" opacity=".45"/>:null;})}{nodes.map(n=><g key={n.id}><rect x={n.position.x} y={n.position.y} width="240" height="90" rx={['start','end','topic'].includes(n.data.kind)?45:10} fill="var(--panel)" stroke="currentColor" strokeWidth="5"/><text x={n.position.x+120} y={n.position.y+53} textAnchor="middle" fill="currentColor" fontSize="24">{n.data.label}</text></g>)}</svg>;
}

export function DiagramTemplates({kind,value,onChange,disabled=false}:{kind:string;value:string;onChange:(id:string,content:Row)=>void;disabled?:boolean}){
 const [items,setItems]=useState<Row[]>([]),[error,setError]=useState('');
 useEffect(()=>{let live=true;void hub('/diagram-templates').then(v=>{if(live)setItems(v.items);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
 return <div className="wh-template-gallery" aria-label="Diagram starter templates"><button type="button" className="wh-template-card" aria-pressed={!value} disabled={disabled} onClick={()=>onChange('',{diagram_type:kind,nodes:[],edges:[],sources:[]})}><span className="wh-template-blank">+</span><strong>Blank canvas</strong><small>Build your own diagram.</small></button>{items.filter(t=>t.kind===kind).map(t=><button type="button" key={t.id} className="wh-template-card" aria-pressed={value===t.id} disabled={disabled} onClick={()=>onChange(t.id,t.content)}><DiagramThumbnail content={t.content}/><strong>{t.name}</strong><small>{t.description}</small></button>)}{error&&<p className="wh-error" role="alert">{error}</p>}</div>;
}
