import {useId,useState,type InputHTMLAttributes} from 'react';
import {Eye,EyeOff} from 'lucide-react';

type Props=Omit<InputHTMLAttributes<HTMLInputElement>,'type'|'id'> & {label:string};
export function PasswordInput({label,...inputProps}:Props){
  const id=useId();
  const [visible,setVisible]=useState(false);
  return <div className="passwordField">
    <label htmlFor={id}>{label}</label>
    <div className="passwordControl">
      <input {...inputProps} id={id} className="textInput" type={visible?'text':'password'}/>
      <button type="button" className="passwordToggle" aria-label={`${visible?'Hide':'Show'} ${label.toLowerCase()}`} aria-controls={id} aria-pressed={visible} disabled={inputProps.disabled} onClick={()=>setVisible(!visible)}>
        {visible?<EyeOff size={18}/>:<Eye size={18}/>}<span>{visible?'Hide':'Show'}</span>
      </button>
    </div>
  </div>;
}
