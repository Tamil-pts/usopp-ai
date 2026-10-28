import {useEffect,useState} from 'react';
import {userStorage} from '../../shared/userStorage';
import {HUB} from './projectApi';
const key='usopp_workhub_resume';
export type WorkPosition={project:string;title:string;section:string;stage:string;view?:string;requirement?:string};
export function rememberWork(value:WorkPosition){userStorage.setItem(key,JSON.stringify(value));window.dispatchEvent(new Event('workhub-resume-changed'));}
export function lastWork():WorkPosition|null{try{return JSON.parse(userStorage.getItem(key)||'null');}catch{return null;}}
export function ContinueWork({onOpen}:{onOpen:(value:WorkPosition)=>void}){
 const [value,setValue]=useState(lastWork);
 useEffect(()=>{const update=()=>setValue(lastWork());window.addEventListener('workhub-resume-changed',update);return()=>window.removeEventListener('workhub-resume-changed',update);},[]);
 useEffect(()=>{if(!value?.project)return;const project=value.project,controller=new AbortController();void fetch(HUB+'/projects/'+encodeURIComponent(project),{credentials:'same-origin',cache:'no-store',signal:controller.signal}).then(response=>{if(!controller.signal.aborted&&[403,404].includes(response.status)&&lastWork()?.project===project){userStorage.removeItem(key);window.dispatchEvent(new Event('workhub-resume-changed'));}}).catch(()=>{});return()=>controller.abort();},[value?.project]);
 return value?<section className="card pf-continue"><div><h3>Continue where you left off</h3><p>{value.title} · {value.stage.toUpperCase()}{value.requirement?' · '+value.requirement:''}{value.view?' · '+value.view:''}</p></div><button className="btn primary" onClick={()=>onOpen(value)}>Reopen saved work</button></section>:null;
}
