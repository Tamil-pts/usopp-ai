import {useEffect,useId,useRef,useState,type KeyboardEvent,type PointerEvent} from 'react';
import {GripHorizontal,RotateCcw} from 'lucide-react';
import {userStorage} from '../../shared/userStorage';
import './chat-response-size.css';

const KEY='usopp_chopper_response_height_v1',MIN=200,MAX=1200;
const limit=()=>Math.max(MIN,Math.min(MAX,Math.round(window.innerHeight*.85)));
const clamp=(height:number,max:number)=>Math.max(MIN,Math.min(max,Math.round(height)));
function readHeight(){
 const value=userStorage.getItem(KEY);if(!value)return null;
 const number=Number(value);return Number.isFinite(number)&&number>=MIN&&number<=MAX?Math.round(number):null;
}

export function useChatResponseSize(accountId:number){
 const [preferred,setPreferred]=useState<number|null>(readHeight),[maximum,setMaximum]=useState(limit),[measured,setMeasured]=useState(MIN),[resizing,setResizing]=useState(false);
 const pane=useRef<HTMLDivElement>(null),id=useId(),latest=useRef(preferred);
 const drag=useRef<{id:number;y:number;height:number;before:number|null;target:HTMLDivElement}|null>(null);
 const height=preferred===null?null:clamp(preferred,maximum);
 const set=(value:number|null)=>{latest.current=value;setPreferred(value);};
 const save=(value:number|null)=>{set(value);userStorage.setItem(KEY,value===null?'':String(value));};
 useEffect(()=>{const next=readHeight();latest.current=next;setPreferred(next);},[accountId]);
 useEffect(()=>{const resize=()=>setMaximum(limit());window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
 useEffect(()=>{const element=pane.current;if(!element)return;const observer=new ResizeObserver(()=>setMeasured(Math.round(element.getBoundingClientRect().height)));observer.observe(element);return()=>observer.disconnect();},[]);
 useEffect(()=>()=>{const current=drag.current;drag.current=null;if(current?.target.hasPointerCapture(current.id))current.target.releasePointerCapture(current.id);},[]);
 const finish=(cancel=false)=>{
  const current=drag.current;if(!current)return;drag.current=null;setResizing(false);
  if(cancel)set(current.before);else save(latest.current);
  if(current.target.hasPointerCapture(current.id))current.target.releasePointerCapture(current.id);
 };
 const pointerDown=(event:PointerEvent<HTMLDivElement>)=>{
  if(!event.isPrimary||event.button!==0||drag.current)return;
  event.preventDefault();event.currentTarget.focus();
  drag.current={id:event.pointerId,y:event.clientY,height:pane.current?.getBoundingClientRect().height||MIN,before:latest.current,target:event.currentTarget};
  event.currentTarget.setPointerCapture(event.pointerId);setResizing(true);
 };
 const pointerMove=(event:PointerEvent<HTMLDivElement>)=>{const current=drag.current;if(current?.id===event.pointerId)set(clamp(current.height+event.clientY-current.y,maximum));};
 const keyDown=(event:KeyboardEvent<HTMLDivElement>)=>{
  if(event.key==='Escape'&&drag.current){event.preventDefault();finish(true);return;}
  if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
  event.preventDefault();if(drag.current)finish();
  const current=height??measured,step=event.shiftKey?80:24;
  save(event.key==='Home'?MIN:event.key==='End'?maximum:clamp(current+(event.key==='ArrowUp'?-step:step),maximum));
 };
 return {pane,id,height,measured,maximum,resizing,reset:()=>save(null),
  handle:{onPointerDown:pointerDown,onPointerMove:pointerMove,
   onPointerUp:(event:PointerEvent<HTMLDivElement>)=>{if(drag.current?.id===event.pointerId)finish();},
   onPointerCancel:(event:PointerEvent<HTMLDivElement>)=>{if(drag.current?.id===event.pointerId)finish(true);},
   onLostPointerCapture:()=>finish(true),onKeyDown:keyDown}};
}

export function ChatResponseSize({size}:{size:ReturnType<typeof useChatResponseSize>}){
 return <div className={'chopperResponseSize'+(size.resizing?' isResizing':'')}>
  <span>Response height{size.height!==null&&<small> · {size.height} px</small>}</span>
  <button className="btn" type="button" disabled={size.height===null} aria-label="Reset chat response height" onClick={size.reset}><RotateCcw size={13}/>Reset</button>
  <div className="chopperResponseGrip" role="separator" tabIndex={0} aria-label="Resize chat response height" aria-orientation="horizontal" aria-controls={size.id} aria-valuemin={MIN} aria-valuemax={size.maximum} aria-valuenow={clamp(size.height??size.measured,size.maximum)} aria-valuetext={`${size.height??size.measured} pixels`} title="Drag up or down to resize. Use Up/Down arrows or Home/End when focused." {...size.handle}><GripHorizontal size={20}/><span>Drag to resize</span></div>
 </div>;
}
