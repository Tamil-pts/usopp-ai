import {useEffect,useRef,useState} from 'react';
import {Download,Locate,Minus,Plus} from 'lucide-react';
import {Item,Project,download,list,request,valueText} from './model';
import type {ViewProps} from './views';
import './ladder-simulation.css';

/** MatchView's source renderer is authoritative for symbol/pin/branch geometry. */
export function LadderSimulation({network,project,scope,select}: {network:Item;project:Project;scope:string;select:ViewProps['select']}) {
  const [drawing,setDrawing]=useState<Item|null>(null),[error,setError]=useState(''),[zoom,setZoom]=useState(.8),[selected,setSelected]=useState<Item|null>(null),[value,setValue]=useState<any>(undefined);
  const viewport=useRef<HTMLDivElement>(null);
  useEffect(()=>{const controller=new AbortController();setDrawing(null);setSelected(null);setError('');
    void fetch('/api/ladder/render/view',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({network:{diagram:network,index:network.network,comment:network.comment,commented:network.commented},side:'base'})}).then(async response=>{if(!response.ok)throw Error('Unable to render the source Ladder network.');return response.json();}).then(result=>{if(!controller.signal.aborted)setDrawing(result);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[network]);
  useEffect(()=>{if(!selected)return;const controller=new AbortController();
    const name=selected.name||selected.instance;if(!name||!/^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[\d+\])*$/.test(name)){setValue(undefined);return;}
    const address=scope+'::'+name;
    const load=()=>request(`/projects/${project.id}/interface-values`,{method:'POST',signal:controller.signal,body:JSON.stringify({names:[address]})}).then(result=>{if(!controller.signal.aborted)setValue(result.values?.[address]);}).catch(()=>setValue(undefined));
    void load();const timer=setInterval(()=>void load(),1200);return()=>{controller.abort();clearInterval(timer);};
  },[selected,scope,project.id]);
  const choose=(element:Element)=>{const id=element.closest('[data-cell-id]')?.getAttribute('data-cell-id');const cell=list(drawing?.model?.cells||network.cells).find(c=>c.id===id);if(cell){setSelected(cell);select('ladder cell',{...cell,scope});}};
  return <article className="source-ladder-network"><header><strong>Network {network.network}</strong><span>{network.comment||network.label}</span><span className="spacer"/><button aria-label="Zoom out Ladder" onClick={()=>setZoom(v=>Math.max(.15,v-.1))}><Minus size={13}/></button><output>{Math.round(zoom*100)}%</output><button aria-label="Zoom in Ladder" onClick={()=>setZoom(v=>Math.min(3,v+.1))}><Plus size={13}/></button><button disabled={!drawing} onClick={()=>setZoom(Math.max(.15,Math.min(3,((viewport.current?.clientWidth||800)-20)/drawing!.width)))}><Locate size={13}/> Fit</button><button disabled={!drawing} onClick={()=>download(`Network-${network.network}.svg`,drawing?.svg||'','image/svg+xml')}><Download size={13}/></button></header>
    {error&&<div className="notice error">{error}</div>}{!drawing&&!error&&<p>Drawing source network…</p>}
    {network.commented&&<p className="notice warning">Commented network: excluded from execution.</p>}
    <div className="source-ladder-viewport" ref={viewport} onClick={e=>choose(e.target as Element)}>{drawing&&<div style={{width:drawing.width*zoom}} dangerouslySetInnerHTML={{__html:drawing.svg}}/>}</div>
    {selected&&<footer><strong>{selected.name||selected.instance||selected.type}</strong><span>{scope} · R{selected.row+1} / C{selected.column+1}</span><span>Selected value: <b>{valueText(value)}</b></span><span>Inputs: {listNames(selected.inputs)} · Outputs: {listNames(selected.outputs)}</span></footer>}
    <small>MatchView geometry · Original source remains read only. A selected variable value does not establish rung continuity.</small>
  </article>;
}
const listNames=(value:any)=>Array.isArray(value)?value.join(', ')||'—':'—';
