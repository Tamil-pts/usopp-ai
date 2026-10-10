import {useRef} from 'react';
export function TreeWidthHandle({width,onChange}:{width:number;onChange:(width:number)=>void}) {
  const start=useRef<{x:number;width:number}|null>(null);
  const update=(value:number)=>onChange(Math.min(650,Math.max(200,value)));
  return <div className="compareTreeWidthHandle" role="separator" aria-label="Resize project tree" aria-orientation="vertical" aria-valuemin={200} aria-valuemax={650} aria-valuenow={width} tabIndex={0}
    onPointerDown={event=>{event.preventDefault();start.current={x:event.clientX,width};event.currentTarget.setPointerCapture(event.pointerId)}}
    onPointerMove={event=>{if(start.current)update(start.current.width+event.clientX-start.current.x)}}
    onPointerUp={event=>{start.current=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId)}}
    onPointerCancel={()=>{start.current=null}} onLostPointerCapture={()=>{start.current=null}}
    onKeyDown={event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();update(event.key==='Home'?200:event.key==='End'?650:width+(event.key==='ArrowRight'?20:-20))}}}/>
}
