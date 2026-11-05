import {CompareModule} from './CompareModule';

import {useEffect,useState,lazy,Suspense,type ComponentProps,type ReactNode} from 'react';
import {userStorage} from '../../shared/userStorage';
const PLCPDFCompare=lazy(()=>import('./PLCPDFCompare'));
import {CircuitCompare} from './CircuitCompare';
import './circuit-compare.css';

export function ComparePage({type,projectLink,...props}:ComponentProps<typeof CompareModule>&{type:'plc'|'circuit';projectLink?:ReactNode}){
 const [mode,setMode]=useState(()=>userStorage.getItem('usopp_plc_matchview_mode')==='pdf'?'pdf':'project');
 const [pdfOpened,setPDFOpened]=useState(mode==='pdf');
 const choose=(next:string)=>{setMode(next);userStorage.setItem('usopp_plc_matchview_mode',next);if(next==='pdf')setPDFOpened(true);};
 useEffect(()=>{const open=()=>choose('pdf');window.addEventListener('usopp-open-plc-pdf',open);return()=>window.removeEventListener('usopp-open-plc-pdf',open);},[]);
 return <div className="matchviewTypes"><div hidden={type!=='plc'}><div className="matchviewTypeBar" role="group" aria-label="PLC MatchView input type"><button type="button" className={mode==='project'?'active':''} aria-pressed={mode==='project'} onClick={()=>choose('project')}>Project folder</button><button type="button" className={mode==='pdf'?'active':''} aria-pressed={mode==='pdf'} onClick={()=>choose('pdf')}>PDF files · Block / network</button></div><div hidden={mode!=='project'}><CompareModule {...props} projectLink={type==='plc'?projectLink:undefined}/></div>{pdfOpened&&<div hidden={mode!=='pdf'}><Suspense fallback={<p role="status">Opening PLC PDF comparison…</p>}><PLCPDFCompare/></Suspense></div>}</div><div hidden={type!=='circuit'}><CircuitCompare projectLink={type==='circuit'?projectLink:undefined}/></div></div>;
}
