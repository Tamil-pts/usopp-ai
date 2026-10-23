import React from 'react';
import type {FrameProtocol} from '../utils/frameProfile';

export function RequestFrameSelect({value,onChange,disabled=false,className=''}:{value:FrameProtocol;onChange:(value:FrameProtocol)=>void;disabled?:boolean;className?:string}){
 return <label className={className}>Request frame
  <select aria-label="Request frame" value={value} disabled={disabled} onChange={event=>onChange(event.target.value as FrameProtocol)}>
   <option value="spinconnect">Server → B&amp;R (SpinConnect)</option>
   <option value="ybs">Server → YBS (Embedded C)</option>
  </select>
 </label>;
}
