import React from 'react';

export function ResizeHandle({height,onChange,label='both screen previews'}:{height:number;onChange:(value:number)=>void;label?:string}){
 const drag=React.useRef<{y:number;height:number}|null>(null);
 const change=(value:number)=>onChange(Math.max(180,Math.min(2200,value)));
 return <div className="compareResizeHandle" role="separator" aria-label={`Resize ${label}`} aria-orientation="horizontal" aria-valuemin={180} aria-valuemax={2200} aria-valuenow={height} tabIndex={0}
  onPointerDown={e=>{drag.current={y:e.clientY,height};e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault()}}
  onPointerMove={e=>{if(drag.current)change(drag.current.height+e.clientY-drag.current.y)}}
  onPointerUp={e=>{drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)}} onPointerCancel={()=>{drag.current=null}}
  onKeyDown={e=>{if(['ArrowUp','ArrowDown','Home','End'].includes(e.key)){e.preventDefault();change(e.key==='Home'?180:e.key==='End'?2200:height+(e.key==='ArrowDown'?40:-40))}}}>
  <span>↕ Drag to resize {label} · {height}px</span>
 </div>;
}
