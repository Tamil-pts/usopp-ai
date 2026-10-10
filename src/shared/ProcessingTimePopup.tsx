import React from 'react';
import {Clock3} from 'lucide-react';

const formatDuration=(seconds:number)=>{
  const safe=Math.max(0,Math.round(seconds));
  const minutes=Math.floor(safe/60);
  return `${String(minutes).padStart(2,'0')}:${String(safe%60).padStart(2,'0')}`;
};

export function ProcessingTimePopup({active,label,progress,defaultEstimate=60}:{active:boolean;label:string;progress?:number;defaultEstimate?:number}){
  const [elapsed,setElapsed]=React.useState(0);
  React.useEffect(()=>{
    if(!active){setElapsed(0);return;}
    const started=Date.now();
    setElapsed(0);
    const timer=window.setInterval(()=>setElapsed((Date.now()-started)/1000),500);
    return()=>window.clearInterval(timer);
  },[active,label]);
  if(!active)return null;
  const percent=Math.max(0,Math.min(100,Number(progress||0)));
  const estimatedTotal=percent>=2&&elapsed>=2?Math.max(elapsed,elapsed*100/percent):defaultEstimate;
  const remaining=Math.max(0,estimatedTotal-elapsed);
  return <aside className="processingTimePopup" role="status" aria-live="off">
    <Clock3 size={15}/><div><b>{label}</b><span>Elapsed {formatDuration(elapsed)}</span><span>{remaining>0?`Estimated remaining ${formatDuration(remaining)}`:'Still processing; initial estimate exceeded'}</span></div>
  </aside>;
}
