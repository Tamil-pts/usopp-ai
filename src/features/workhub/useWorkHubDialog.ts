import {useEffect,useRef} from 'react';
export function useWorkHubDialog(onClose:()=>void,busy=false){
 const element=useRef<HTMLElement>(null),close=useRef(onClose),working=useRef(busy);close.current=onClose;working.current=busy;
 useEffect(()=>{const root=element.current,prior=document.activeElement as HTMLElement|null;if(!root)return;const focusable=()=>Array.from(root.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href]')).filter(e=>e.getClientRects().length>0);focusable()[0]?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();if(!working.current)close.current();}if(e.key==='Tab'){const nodes=focusable(),first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}};root.addEventListener('keydown',key);return()=>{root.removeEventListener('keydown',key);if(prior?.isConnected)prior.focus();};},[]);
 return element;
}
