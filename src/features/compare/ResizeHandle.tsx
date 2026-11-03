import React from 'react';

export function ResizeHandle({height,onChange,label='both screen previews',minHeight=180,maxHeight=2200}:{height:number;onChange:(value:number)=>void;label?:string;minHeight?:number;maxHeight?:number}){
 const drag=React.useRef<{y:number;height:number}|null>(null);
 const change=(value:number)=>onChange(Math.max(minHeight,Math.min(maxHeight,value)));
 return <div className="compareResizeHandle" role="separator" aria-label={`Resize ${label}`} aria-orientation="horizontal" aria-valuemin={minHeight} aria-valuemax={maxHeight} aria-valuenow={height} tabIndex={0}
  onPointerDown={e=>{if(!e.isPrimary||e.button!==0)return;drag.current={y:e.clientY,height};e.currentTarget.focus();e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault()}}
  onPointerMove={e=>{if(drag.current)change(drag.current.height+e.clientY-drag.current.y)}}
  onPointerUp={e=>{drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)}} onPointerCancel={()=>{drag.current=null}} onLostPointerCapture={()=>{drag.current=null}}
  onKeyDown={e=>{if(['ArrowUp','ArrowDown','Home','End'].includes(e.key)){e.preventDefault();change(e.key==='Home'?minHeight:e.key==='End'?maxHeight:height+(e.key==='ArrowDown'?40:-40))}}}>
  <span>↕ Drag to resize {label} · {height}px</span>
 </div>;
}
