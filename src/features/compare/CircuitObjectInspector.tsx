import {useEffect,useState} from 'react';

export type DrawingObjectOverlay={bbox?:number[];paths?:number[][][];label:string};
type Item={id?:string;kind?:string;text?:string;reference?:string;bbox?:number[];points?:number[][];path?:number[][];point?:number[];degree?:number;from?:string;to?:string;lineIds?:string[];status?:string;shape?:string;uncertain?:boolean};
type Graph={drawingKind?:string;labels:Item[];components:Item[];terminals:Item[];symbols:Item[];lines:Item[];vertices:Item[];connections:Item[];geometricPaths:Item[];crossings:Item[];terminalAssociations:unknown[];coverage:Record<string,number|boolean|string>;limitations:string[]};
const kinds=[['components','Component references'],['terminals','Terminal / pin labels'],['labels','All text labels'],['symbols','Symbol shapes'],['lines','Drawn line segments'],['vertices','Path nodes'],['connections','Connection candidates / printed mappings'],['geometricPaths','Geometric paths (not electrical nets)'],['crossings','Unjoined crossings']] as const;
const text=(value:Item)=>value.reference||value.text||(value.from?`${value.from} → ${value.to}`:value.shape)||`${value.id||'Crossing'}${value.degree!==undefined?` · ${value.degree} joined segments`:''}`;
const identity=(value:string)=>value.normalize('NFKC').replace(/\s+/g,'').toLowerCase();
function overlay(item:Item):DrawingObjectOverlay{
 const paths=item.path?[item.path]:item.points?[item.points]:undefined;
 return {label:text(item),bbox:item.bbox||(!paths&&item.point?[item.point[0]-.003,item.point[1]-.003,item.point[0]+.003,item.point[1]+.003]:undefined),paths};
}

export function CircuitObjectInspector({session,pair,enabled,onInspect}:{session:string;pair:{id:string;base:number|null;developed:number|null};enabled:boolean;onInspect:(value:[DrawingObjectOverlay|null,DrawingObjectOverlay|null])=>void}){
 const [open,setOpen]=useState(false),[graphs,setGraphs]=useState<[Graph|null,Graph|null]>([null,null]);
 const [kind,setKind]=useState<typeof kinds[number][0]>('components'),[search,setSearch]=useState(''),[limit,setLimit]=useState(50),[error,setError]=useState(''),[loading,setLoading]=useState(false),[selected,setSelected]=useState<{side:number;item:Item}|null>(null);
 useEffect(()=>{
  setGraphs([null,null]);setSelected(null);onInspect([null,null]);setError('');
  if(!open||!enabled)return;
  const abort=new AbortController();setLoading(true);
  Promise.all((['base','developed'] as const).map(async side=>{
   if(!pair[side])return null;
   const r=await fetch(`/api/circuit-compare/${session}/graph/${side}/${pair[side]}`,{signal:abort.signal});
   const data=await r.json();if(!r.ok)throw new Error(data.detail||'Object graph could not be loaded.');return data as Graph;
  })).then(values=>{if(!abort.signal.aborted)setGraphs(values as [Graph|null,Graph|null])}).catch(e=>{if(!abort.signal.aborted)setError(e.message)}).finally(()=>{if(!abort.signal.aborted)setLoading(false)});
  return()=>abort.abort();
 },[open,enabled,pair.id,session,onInspect]);
 useEffect(()=>{setLimit(50)},[kind,search]);
 const inspect=(side:number,item:Item)=>{
  setSelected({side,item});const values:[DrawingObjectOverlay|null,DrawingObjectOverlay|null]=[null,null];values[side]=overlay(item);
  // Only unique label/reference identities are linked across versions. W1/N1
  // identifiers are page-local and must never be treated as matching objects.
  const stable=item.reference||item.text;
  if(stable){const matches=((graphs[1-side]?.[kind]||[]) as Item[]).filter(p=>identity(p.reference||p.text||'')===identity(stable));if(matches.length===1)values[1-side]=overlay(matches[0])}
  onInspect(values);
 };
 return <details className="circuitObjects" open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>Drawing objects &amp; connection paths <span>Labels · components · terminals · nodes</span></summary>
  {!enabled?<p>Recompare the original drawings to build the updated object graph.</p>:<>
   <p>Objects come from the PDF text and vectors. Endpoint/dot joins are traced; plain crossings stay unjoined. Terminal associations are candidates for engineer verification.</p>
   {loading&&<p role="status">Reading page objects…</p>}{error&&<p role="alert">{error}</p>}
   <div className="circuitObjectFilters"><label>Object type<select aria-label="Drawing object type" value={kind} onChange={e=>setKind(e.target.value as typeof kind)}>{kinds.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><label>Find object<input aria-label="Find drawing object" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Reference, label or node ID"/></label><button className="btn" onClick={()=>{setSelected(null);onInspect([null,null])}}>Clear object highlight</button></div>
   <div className="circuitObjectSides">{graphs.map((graph,side)=><section key={side}><h3>{side===0?'Base':'Developed'} · Page {side===0?pair.base||'—':pair.developed||'—'}</h3>{graph?<>
    <p className="circuitObjectCoverage">{graph.coverage.textLabels} labels · {graph.coverage.componentReferences} component refs · {graph.coverage.terminalReferences} terminal refs · {graph.coverage.drawnLines} lines · {graph.coverage.candidateConnections} candidate paths</p>
    <p className="circuitObjectCaution">{graph.drawingKind}. {graph.terminals.length-graph.terminalAssociations.length} terminal labels have no unique wire association. {graph.coverage.unjoinedCrossings} crossings remain unjoined. Cable/symbol outlines are inspected as geometry, not electrical nets.{graph.coverage.graphPartial&&' Path analysis is partial.'}</p>
    <div className="circuitObjectList">{((graph[kind]||[]) as Item[]).filter(item=>identity(`${text(item)} ${item.id||''}`).includes(identity(search))).slice(0,limit).map((item,i)=><button key={item.id||i} className={selected?.side===side&&selected.item===item?'selected':''} onClick={()=>inspect(side,item)}><b>{text(item)}</b><small>{item.id||'Crossing'}{item.lineIds?.length?` · ${item.lineIds.length} source line segments`:''} {item.status||item.kind||kind}{item.uncertain?' · verify extraction':''}</small></button>)}</div>
    {!((graph[kind]||[]) as Item[]).length&&<p className="circuitObjectCaution">{kind==='connections'?'No explicit mappings or unambiguous electrical connection candidates were established. Geometric paths are listed separately.':'No objects of this type were extracted on this page.'}</p>}
    {((graph[kind]||[]) as Item[]).length>limit&&<button className="btn" onClick={()=>setLimit(n=>n+100)}>Show more objects</button>}
   </>:<p>No page on this side.</p>}</section>)}</div>
   {selected&&<div className="circuitObjectSelection"><b>Selected: {text(selected.item)}</b><p>{selected.item.status||'Source object selected. Its location is outlined in cyan on the drawing.'}</p>{selected.item.lineIds&&<p>Source paths: {selected.item.lineIds.join(', ')}</p>}<small>Selecting a path does not approve an electrical connection or establish machine behavior.</small></div>}
  </>}
 </details>;
}
