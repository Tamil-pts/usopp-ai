import {useEffect,useMemo,useRef,useState} from 'react';
import {bounds,move,pin,snap,value,type Circuit,type Item,type Part,type Point} from './nativeModel';
type Props={id:string;doc:Circuit;library:Part[];tool:string;selection:string[];onSelect:(ids:string[])=>void;onElements:(elements:Item[],before?:Item[])=>void;onAdd:(kind:string,p:Point)=>void;command:{kind:string;nonce:number};onZoom:(z:number)=>void;result:any;sample:number;playing:boolean;focus:string};

export function CircuitCanvas({id,doc,library,tool,selection,onSelect,onElements,onAdd,command,onZoom,result,sample,playing,focus}:Props){
 const host=useRef<HTMLDivElement>(null),svg=useRef<SVGSVGElement>(null),drag=useRef<any>(null),changed=useRef(false);
 const [size,setSize]=useState({w:900,h:600}),[view,setView]=useState({x:60,y:60,z:1}),[wire,setWire]=useState<{points:Point[];from?:any}|null>(null),[cursor,setCursor]=useState<Point>([0,0]);
 const current=useRef(view);current.current=view;
 const boxes=useMemo(()=>new Map(doc.elements.map(e=>[e.id,bounds(e)])),[doc.elements]);
 const fit=()=>{const b=[...boxes.values()];if(!b.length){setView({x:40,y:40,z:1});return;}const x=Math.min(...b.map(b=>b[0])),y=Math.min(...b.map(b=>b[1])),r=Math.max(...b.map(b=>b[2])),bottom=Math.max(...b.map(b=>b[3]));const z=Math.max(.02,Math.min(2,(size.w-70)/Math.max(100,r-x),(size.h-70)/Math.max(100,bottom-y)));setView({z,x:(size.w-(r-x)*z)/2-x*z,y:(size.h-(bottom-y)*z)/2-y*z});};
 const zoom=(factor:number,x=size.w/2,y=size.h/2)=>setView(v=>{const z=Math.max(.02,Math.min(8,v.z*factor));return {z,x:x-(x-v.x)*z/v.z,y:y-(y-v.y)*z/v.z};});
 useEffect(()=>{const node=host.current;if(!node)return;const observer=new ResizeObserver(([e])=>setSize({w:e.contentRect.width,h:e.contentRect.height}));observer.observe(node);return()=>observer.disconnect();},[]);
 useEffect(()=>{fit();},[id,size.w,size.h]);
 useEffect(()=>{onZoom(Math.round(view.z*100));},[view.z]);
 useEffect(()=>{if(command.kind==='fit')fit();if(command.kind==='in')zoom(1.25);if(command.kind==='out')zoom(.8);},[command.nonce]);
 useEffect(()=>{setWire(null)},[tool,id]);
 useEffect(()=>{if(!focus)return;const b=boxes.get(focus.split('|')[0]);if(!b)return;setView(v=>({...v,z:1.5,x:size.w/2-(b[0]+b[2])*.75,y:size.h/2-(b[1]+b[3])*.75}));},[focus]);
 useEffect(()=>{const node=host.current;if(!node)return;const wheel=(e:WheelEvent)=>{e.preventDefault();const b=node.getBoundingClientRect();zoom(Math.exp(-e.deltaY*.0015),e.clientX-b.left,e.clientY-b.top);};node.addEventListener('wheel',wheel,{passive:false});return()=>node.removeEventListener('wheel',wheel);},[]);
 useEffect(()=>{if(playing)svg.current?.unpauseAnimations();else svg.current?.pauseAnimations();},[playing,result]);
 const world=(clientX:number,clientY:number):Point=>{const b=host.current!.getBoundingClientRect(),v=current.current;return [snap((clientX-b.left-v.x)/v.z),snap((clientY-b.top-v.y)/v.z)];};
 const finishWire=(p:Point,to?:any)=>{if(!wire){setWire({points:[p],from:to});return;}const last=wire.points[wire.points.length-1],pts=[...wire.points];if(last[0]!==p[0]&&last[1]!==p[1])pts.push([p[0],last[1]]);pts.push(p);const e:Item={id:crypto.randomUUID(),kind:'wire',x:0,y:0,points:pts,from:wire.from,to,reviewed:true};onElements([...doc.elements,e]);setWire(null);onSelect([e.id]);};
 const left=-view.x/view.z,top=-view.y/view.z,right=left+size.w/view.z,bottom=top+size.h/view.z;
 const rendered=doc.elements.filter(e=>{const b=boxes.get(e.id)!;return b[2]>=left&&b[0]<=right&&b[3]>=top&&b[1]<=bottom;});
 return <div ref={host} className={'ve-stage native-stage tool-'+tool} tabIndex={0} role="region" aria-label="Native circuit editor" onKeyDown={e=>{if(e.key==='Escape'){setWire(null);onSelect([]);}if(e.key==='0')fit();if(['+','='].includes(e.key))zoom(1.25);if(e.key==='-')zoom(.8);if(e.key.toLowerCase()==='a'&&(e.ctrlKey||e.metaKey)){e.preventDefault();onSelect(doc.elements.map(e=>e.id));}}}>
  <svg ref={svg} width="100%" height="100%" viewBox={`0 0 ${size.w} ${size.h}`} aria-label="Editable circuit wires and symbols" onPointerDown={e=>{if(e.button!==0&&e.button!==1)return;const p=world(e.clientX,e.clientY),target=e.target as Element,port=target.closest('[data-port]'),hit=target.closest('[data-element]')?.getAttribute('data-element');changed.current=false;
   if(tool==='wire'&&e.button===0){if(port){const identity=port.getAttribute('data-part')!,name=port.getAttribute('data-port')!,element=doc.elements.find(e=>e.id===identity)!;finishWire(pin(element,name,library),{id:identity,port:name});}else if(wire){setWire({...wire,points:[...wire.points,p]});}else setWire({points:[p]});return;}
   if(tool!=='select'&&tool!=='pan'&&e.button===0){onAdd(tool,p);return;}
   const pan=tool==='pan'||!hit||e.button===1,ids=hit?(e.shiftKey?[...new Set([...selection,hit])]:selection.includes(hit)?selection:[hit]):[];
   if(!pan)onSelect(ids);else if(!hit)onSelect([]);
   drag.current={px:e.clientX,py:e.clientY,view:current.current,elements:doc.elements,ids,pan};e.currentTarget.setPointerCapture(e.pointerId);
  }} onPointerMove={e=>{const p=world(e.clientX,e.clientY);setCursor(p);const d=drag.current;if(!d)return;const dx=e.clientX-d.px,dy=e.clientY-d.py;if(Math.hypot(dx,dy)<3)return;changed.current=true;if(d.pan)setView({...d.view,x:d.view.x+dx,y:d.view.y+dy});else onElements(move(d.elements,d.ids,snap(dx/d.view.z),snap(dy/d.view.z),library),d.elements);}} onPointerUp={e=>{const d=drag.current;if(d&&!d.pan&&changed.current)onElements(move(d.elements,d.ids,snap((e.clientX-d.px)/d.view.z),snap((e.clientY-d.py)/d.view.z),library));drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{drag.current=null;}} onDoubleClick={e=>{if(tool==='wire'&&wire)finishWire(world(e.clientX,e.clientY));}}>
   <defs><pattern id="native-grid" width={Math.max(10,20*view.z)} height={Math.max(10,20*view.z)} x={view.x} y={view.y} patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="currentColor"/></pattern></defs><rect width="100%" height="100%" fill="url(#native-grid)" className="ve-grid"/>
   <g transform={`translate(${view.x} ${view.y}) scale(${view.z})`}>
    {rendered.map(e=>{const selected=selection.includes(e.id),measurement=result?.measurements?.[e.id],v=measurement?.voltage?.[sample],i=measurement?.current?.[sample],part=library.find(p=>p.kind===e.kind);const cls=(selected?' selected':'')+(!e.reviewed&&e.kind!=='text'&&e.kind!=='drawing'?' unreviewed':'')+(i!==undefined&&Math.abs(i)>1e-8?' energized':'');
     if(e.kind==='wire'){const d='M'+e.points.map((p:Point)=>p.join(',')).join(' L'),flow=i<0?[...e.points].reverse():e.points,path='M'+flow.map((p:Point)=>p.join(',')).join(' L');return <g key={e.id} data-element={e.id} data-kind="wire" className={'native-wire'+cls}><title>{e.label||e.id}{v!==undefined?' · '+value(v,'V'):''}{i!==undefined?' · '+value(i,'A'):''}</title><path d={d} fill="none" className="native-hit" vectorEffect="non-scaling-stroke"/><path d={d} fill="none" vectorEffect="non-scaling-stroke"/>{i!==undefined&&Math.abs(i)>1e-8&&<circle r={2.5/view.z} className="native-current-dot"><animateMotion path={path} dur="1.2s" repeatCount="indefinite"/></circle>}{selected&&e.points.map((p:Point,j:number)=><circle key={j} cx={p[0]} cy={p[1]} r={3/view.z} className="native-wire-point"/>)}{selected&&v!==undefined&&<text x={e.points[0][0]+5} y={e.points[0][1]-10} className="native-voltage" fontSize={12/view.z}>{value(v,'V')}</text>}</g>;}
     if(e.kind==='text')return <text key={e.id} data-element={e.id} data-kind="text" className={'native-label'+cls} x={e.x} y={e.y} fontSize={e.fontSize||12}>{e.text}</text>;
     return <g key={e.id} data-element={e.id} data-kind={e.kind} className={'native-part'+cls} transform={`translate(${e.x} ${e.y})`}><title>{e.label||part?.title||'Unclassified vector'}{v!==undefined?' · '+value(v,'V'):''}</title><g transform={`rotate(${e.rotation||0}) scale(${e.scale||1})`}>
      {part&&<rect className="native-part-hit" x={-43} y={-28} width={86} height={56}/>}
      {(part?.paths||e.paths||['M-20 -20L20 20M-20 20L20 -20']).map((d:string,j:number)=><path key={j} d={e.kind==='switch'&&e.params?.closed&&j===0?'M-40 0H40':d} fill="none" vectorEffect="non-scaling-stroke"/>)}
      {selected&&<rect className="native-selection" x={-50} y={-50} width={Math.max(100,e.width||0)} height={Math.max(100,e.height||0)} vectorEffect="non-scaling-stroke"/>}</g>
      {e.label&&<text className="native-part-name" textAnchor="middle" y={-30*(e.scale||1)} fontSize={12/view.z}>{e.label}</text>}
      {part&&<text className="native-part-value" textAnchor="middle" y={45*(e.scale||1)} fontSize={10/view.z}>{e.params?.value!==undefined?value(e.params.value,part.fields.find((f:any)=>f.key==='value')?.unit||''):e.kind==='switch'?(e.params.closed?'Closed':'Open'):''}</text>}
      {measurement&&<text className="native-measurement" textAnchor="middle" y={62*(e.scale||1)} fontSize={11/view.z}>{value(v,'V')} · {value(i,'A')}</text>}
      {part?.ports.map(p=>{const [x,y]=pin({...e,x:0,y:0},p.id,library);return <circle key={p.id} data-part={e.id} data-port={p.id} cx={x} cy={y} r={(tool==='wire'?5:2.4)/view.z} className="native-port"><title>{e.label||part.title} · {p.id}</title></circle>;})}
     </g>;
    })}
    {wire&&<polyline className="native-wire-preview" points={[...wire.points,cursor].map(p=>p.join(',')).join(' ')} fill="none" vectorEffect="non-scaling-stroke"/>}
   </g>
  </svg><div className="ve-canvas-help">{tool==='wire'?'Click a pin, add bends, then click the destination pin. Double-click to end a free wire.':tool==='pan'?'Drag to pan. Wheel to zoom.':tool==='select'?'Select and drag circuit objects. Shift to select more. Wheel to zoom.':'Click to place '+(library.find(p=>p.kind===tool)?.title||tool)} · Esc cancels</div>
 </div>;
}
