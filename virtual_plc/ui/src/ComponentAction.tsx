import React from 'react';
import {AlertTriangle} from 'lucide-react';

export function ComponentAction({name,reason,onClick}:{name:string;reason?:string;onClick:()=>void}){
  return reason?<button type="button" className="component-action-required" title={reason} aria-label={`Action required for ${name}`} onClick={event=>{event.stopPropagation();onClick();}}><AlertTriangle size={15}/><span className="sr-only">Review connections</span></button>:null;
}
