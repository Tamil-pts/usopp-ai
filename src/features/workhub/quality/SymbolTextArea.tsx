import {useRef,useState,type TextareaHTMLAttributes} from 'react';
import './symbol-text.css';

const symbols=[['≥','Greater than or equal'],['≤','Less than or equal'],['≠','Not equal'],['±','Plus or minus'],['°','Degree'],['Ω','Ohm'],['µ','Micro'],['Δ','Delta'],['×','Multiply'],['÷','Divide'],['²','Squared'],['³','Cubed'],['→','Right arrow'],['←','Left arrow'],['↑','Up arrow'],['↓','Down arrow'],['✓','Check'],['•','Bullet']];
export function SymbolTextArea({value,onValueChange,...props}:Omit<TextareaHTMLAttributes<HTMLTextAreaElement>,'value'|'onChange'>&{value:string;onValueChange:(value:string)=>void}){
 const ref=useRef<HTMLTextAreaElement>(null),range=useRef([0,0]),[open,setOpen]=useState(false);
 const label=props['aria-label']||'text';
 const insert=(symbol:string)=>{const [start,end]=range.current,next=value.slice(0,start)+symbol+value.slice(end);if(props.maxLength&&next.length>props.maxLength)return;onValueChange(next);setOpen(false);requestAnimationFrame(()=>{ref.current?.focus();ref.current?.setSelectionRange(start+symbol.length,start+symbol.length);range.current=[start+symbol.length,start+symbol.length];});};
 return <div className="wh-symbol-text"><textarea {...props} ref={ref} value={value} onChange={e=>onValueChange(e.target.value)} onSelect={e=>{range.current=[e.currentTarget.selectionStart,e.currentTarget.selectionEnd];}}/><button type="button" className="wh-symbol-toggle" aria-label={'Insert symbol in '+label} aria-expanded={open} disabled={props.disabled||props.readOnly} onMouseDown={e=>e.preventDefault()} onClick={()=>setOpen(v=>!v)}>Ω <span>Symbol</span></button>{open&&<div className="wh-symbol-palette" role="group" aria-label={'Symbols for '+label}>{symbols.map(([symbol,name])=><button key={symbol} type="button" title={name} aria-label={name+' '+symbol} onClick={()=>insert(symbol)}>{symbol}</button>)}<button type="button" className="wh-symbol-close" onClick={()=>setOpen(false)}>Close</button></div>}</div>;
}
