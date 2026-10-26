import {useId} from 'react';
const DEFAULTS=['B&R PLC','Siemens PLC','Other PLC','Electrical / CAD','Documentation','General'];
export function WorkTypeField({value,kinds=[],change}:{value:string;kinds?:string[];change:(value:string)=>void}){
  const id=useId();return <label>Work type<input className="textInput" list={id} required maxLength={50} value={value} placeholder="Select or enter a work type" onChange={event=>change(event.target.value)}/><datalist id={id}>{Array.from(new Set([...DEFAULTS,...kinds])).map(kind=><option value={kind} key={kind}/>)}</datalist><small>Choose an existing type or enter your own.</small></label>;
}
