import {useEffect,useRef,useState} from 'react';
import {ArrowRight,FileText,LoaderCircle,X} from 'lucide-react';
import type {HubRow} from './projectApi';

const tools=[
  {stage:'frd',section:'meetings',title:'FRD',description:'Functional requirements, linked flowchart and source references.'},
  {stage:'test',section:'documents',title:'Test Report',description:'Prepare and review engineering test documentation.'},
  {stage:'corrections',section:'documents',title:'Correction Notes',description:'Record requested corrections and their resolution.'},
  {stage:'fat',section:'quality',title:'FAT',description:'Factory acceptance procedure and recorded test results.'},
  {stage:'quality',section:'quality',title:'Quality Approval',description:'Review delivery quality using the existing approval process.'},
  {stage:'closure',section:'quality',title:'Project Closure',description:'Prepare the controlled project closure record.'},
];

export function ProjectDocumentTools({projects,initialProject,onOpen,onReports,onClose}:{projects:HubRow[];initialProject?:string;onOpen:(project:string,section:string,stage:string)=>Promise<void>;onReports:()=>void;onClose:()=>void}){
  const [project,setProject]=useState(initialProject||projects.find(p=>p.stage!=='released')?.id||projects[0]?.id||''),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const ref=useRef<HTMLDivElement>(null),closeRef=useRef(onClose);closeRef.current=onClose;
  useEffect(()=>{const previous=document.activeElement as HTMLElement;ref.current?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape')closeRef.current();if(e.key==='Tab'){const nodes=ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),select');if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};window.addEventListener('keydown',key);return()=>{window.removeEventListener('keydown',key);previous?.focus();};},[]);
  const open=async(section:string,stage:string)=>{setBusy(stage);setError('');try{await onOpen(project,section,stage);onClose();}catch(e){setError((e as Error).message);}finally{setBusy('');}};
  return <div className="wh-backdrop"><div className="wh-dialog wide" role="dialog" aria-modal="true" aria-label="Create FRD / Reports" tabIndex={-1} ref={ref}>
    <header><h2><FileText size={20}/>Create FRD / Reports</h2><button className="btn" aria-label="Close document tools" onClick={onClose}><X size={18}/></button></header>
    <div className="wh-form"><p>Choose a project, then open its document workspace. Use <b>Generate draft</b> there to prepare the document from the available project sources.</p>
      <label>Project for documents<select className="textInput" value={project} disabled={!!busy||!projects.length} onChange={e=>setProject(e.target.value)}>{!projects.length&&<option value="">Create a project first</option>}{projects.map(p=><option key={p.id} value={p.id}>{p.title}{p.stage==='released'?' (closed)':''}</option>)}</select></label>
      {error&&<p className="wh-error" role="alert">{error}</p>}
      <div className="wh-form-grid">{tools.map(t=><button className="btn wh-document-tool" key={t.stage} disabled={!project||!!busy} onClick={()=>void open(t.section,t.stage)}><span><strong>{t.title}</strong><small>{t.description}</small></span>{busy===t.stage?<LoaderCircle size={17} className="spin"/>:<ArrowRight size={17}/>}</button>)}</div>
      <footer><button className="btn" disabled={!!busy} onClick={onReports}>Portfolio reports</button><button className="btn" onClick={onClose}>Close</button></footer>
    </div>
  </div></div>;
}
