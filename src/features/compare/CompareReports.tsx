import {userStorage} from '../../shared/userStorage';
import {useEffect,useRef,useState} from 'react';
import {Download,FileText,X} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import type {ReportCover} from '../../shared/ReportExport';
import '../../shared/report-export.css';

type Format='html'|'pdf'|'docx'|'json';
type Selection={categories:string[];statuses:string[];includeKnowledge:boolean};
const categoryLabels:Record<string,string>={logic:'Logic',screen:'Screen',config:'Project view / configuration',hardware:'Hardware'};
const statusLabels:Record<string,string>={modified:'Modified / differences',added:'Added',removed:'Removed',unchanged:'Unchanged'};
const defaultSelection:Selection={categories:Object.keys(categoryLabels),statuses:['modified','added','removed'],includeKnowledge:true};
type Job={id:string;sessionId:string;status:string;stage:string;elapsedSeconds:number;cover:ReportCover;skipLayoutProperties:boolean;reports:Partial<Record<Format,{status:string;downloadUrl?:string;filename?:string;error?:string}>>};
const formats:Format[]=['html','pdf','docx','json'];
const label=(format:Format)=>format==='docx'?'Word':format.toUpperCase();
const pending=(job:Job)=>['queued','running'].includes(job.status);
const today=()=>{const date=new Date();return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;};
async function responseData(response:Response){
  if(response.status===404||response.status===405)throw new Error('Report preparation is unavailable. Restart the updated uSOPp server, then compare again.');
  const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Could not prepare this report.');return data;
}

export function CompareReports({sessionId,projectName,busy,skipLayout}:{sessionId?:string;projectName:string;busy:boolean;skipLayout:boolean}){
  const {user}=useAccount();const key=`usopp_matchview_cover_${user.id}`;
  const [cover,setCover]=useState<ReportCover>(()=>{try{const saved=JSON.parse(userStorage.getItem(key)||'null');if(saved&&typeof saved.description==='string')return {...saved,projectName:'',date:today()};}catch{}
    return {projectName:'',description:'',validatedBy:user.username,date:today(),validationDetails:'',approvedBy:''};});
  const [selectedFormats,setSelectedFormats]=useState<Format[]>(['html','pdf']);
  const [selection,setSelection]=useState<Selection>(defaultSelection),[draftSelection,setDraftSelection]=useState<Selection>(defaultSelection);
  const [draft,setDraft]=useState(cover),[draftFormats,setDraftFormats]=useState(selectedFormats);
  const [detailsOpen,setDetailsOpen]=useState(false),[reportsOpen,setReportsOpen]=useState(false),[error,setError]=useState(''),[starting,setStarting]=useState(false);
  const [jobs,setJobs]=useState<Job[]>([]),[selectedJob,setSelectedJob]=useState('');
  const detailsDialog=useRef<HTMLDialogElement>(null),reportsDialog=useRef<HTMLDialogElement>(null);
  const autoKey=useRef(''),notified=useRef(new Set<string>()),mounted=useRef(true),runSnapshot=useRef<{cover:ReportCover;formats:Format[];selection:Selection}|null>(null);
  const effectiveCover={...cover,projectName:cover.projectName||projectName||'Comparison'};
  const current=jobs.find(job=>job.id===selectedJob)||jobs[0];
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(detailsOpen)detailsDialog.current?.showModal();else detailsDialog.current?.close();},[detailsOpen]);
  useEffect(()=>{if(reportsOpen)reportsDialog.current?.showModal();else reportsDialog.current?.close();},[reportsOpen]);

  const prepare=async(sid:string,details:ReportCover,requested:Format[],filter:boolean,options:Selection=selection)=>{
    setStarting(true);setError('');
    try{
      const job:Job=await responseData(await fetch(`/api/local/compare/reports/start/${encodeURIComponent(sid)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cover:details,formats:requested,skipLayoutProperties:filter,...options})}));
      if(!mounted.current)return;
      setJobs(previous=>[job,...previous.filter(item=>item.id!==job.id)]);setSelectedJob(job.id);
      if(Object.values(job.reports).some(item=>item?.status==='ready')){setReportsOpen(true);notified.current.add(job.id);}
    }catch(reason){if(mounted.current)setError(reason instanceof Error?reason.message:'Could not start report preparation.');}
    finally{if(mounted.current)setStarting(false);}
  };
  useEffect(()=>{
    if(busy){if(!runSnapshot.current)runSnapshot.current={cover:effectiveCover,formats:selectedFormats,selection};return;}
    if(!sessionId)return;
    const next=`${sessionId}:${skipLayout}`;
    if(autoKey.current===next){runSnapshot.current=null;return;}
    autoKey.current=next;const snapshot=runSnapshot.current;runSnapshot.current=null;
    void prepare(sessionId,snapshot?.cover||effectiveCover,snapshot?.formats||selectedFormats,skipLayout,snapshot?.selection||selection);
  },[sessionId,busy,skipLayout]);
  useEffect(()=>{
    const running=jobs.filter(pending);if(!running.length)return;
    let active=true;const controller=new AbortController();
    const timer=setTimeout(()=>{void Promise.all(running.map(async job=>{
      try{
        const update:Job=await responseData(await fetch(`/api/local/compare/reports/status/${job.id}`,{signal:controller.signal}));
        if(!active)return undefined;
        if(!notified.current.has(job.id)&&(Object.values(update.reports).some(item=>item?.status==='ready')||!pending(update))){
          notified.current.add(job.id);setSelectedJob(job.id);setReportsOpen(true);
        }
        return update;
      }catch(reason){if(active)setError(reason instanceof Error?reason.message:'Could not check report preparation.');return undefined;}
    })).then(updates=>{if(active)setJobs(previous=>previous.map(job=>updates.find(update=>update?.id===job.id)||job));});},1500);
    return()=>{active=false;controller.abort();clearTimeout(timer);};
  },[jobs]);
  const edit=()=>{setDraft(effectiveCover);setDraftFormats(selectedFormats);setDraftSelection(selection);setDetailsOpen(true);};
  const update=(field:keyof ReportCover,value:string)=>setDraft(previous=>({...previous,[field]:value}));
  const choose=(format:Format,checked:boolean)=>setDraftFormats(previous=>checked?[...previous,format]:previous.filter(item=>item!==format));
  const chooseItem=(field:'categories'|'statuses',value:string,checked:boolean)=>setDraftSelection(previous=>({...previous,[field]:checked?[...previous[field],value]:previous[field].filter(item=>item!==value)}));
  const save=()=>{setCover(draft);setSelectedFormats(draftFormats);setSelection(draftSelection);userStorage.setItem(key,JSON.stringify(draft));setDetailsOpen(false);
    if(sessionId&&!busy){void prepare(sessionId,draft,draftFormats,skipLayout,draftSelection);setReportsOpen(true);}};

  return <>
    <button className="compareDarkBtn" onClick={edit}><FileText size={14}/> Project details</button>
    {sessionId&&<button className="compareDarkBtn" onClick={()=>setReportsOpen(true)} disabled={starting}>{starting?'Starting reports…':current&&pending(current)?`Preparing reports · ${Math.floor(current.elapsedSeconds)}s`:'Reports / download'}</button>}
    {error&&<span className="compareReportError" role="alert">{error}</span>}
    {detailsOpen&&<dialog ref={detailsDialog} className="reportExportDialog" onCancel={event=>{event.preventDefault();setDetailsOpen(false);}}>
      <form onSubmit={event=>{event.preventDefault();save();}}><header><div><span className="eyebrow">MATCHVIEW</span><h2>Project details</h2><p>Save before comparing. Reports prepare in the background.</p></div><button type="button" className="btn" aria-label="Close project details" onClick={()=>setDetailsOpen(false)}><X size={18}/></button></header>
      <div className="reportCoverFields">
        <label>Project name<input autoFocus required maxLength={200} value={draft.projectName} onChange={event=>update('projectName',event.target.value)}/></label>
        <label>Description<textarea rows={3} maxLength={2000} value={draft.description} onChange={event=>update('description',event.target.value)}/></label>
        <div className="reportCoverPair"><label>Validated by<input maxLength={200} value={draft.validatedBy} onChange={event=>update('validatedBy',event.target.value)}/></label><label>Date<input type="date" required value={draft.date} onChange={event=>update('date',event.target.value)}/></label></div>
        <label>Validation details<textarea rows={3} maxLength={4000} value={draft.validationDetails} onChange={event=>update('validationDetails',event.target.value)}/></label>
        <label>Approved by<input maxLength={200} value={draft.approvedBy} onChange={event=>update('approvedBy',event.target.value)}/><small>Leave blank until approved. Cover pages appear in HTML and PDF.</small></label>
        <fieldset className="compareReportFormats"><legend>Prepare report formats</legend>{formats.map(format=><label key={format}><input type="checkbox" checked={draftFormats.includes(format)} onChange={event=>choose(format,event.target.checked)}/>{label(format)}</label>)}</fieldset>
        <fieldset className="compareReportFormats"><legend>Report sections</legend><label><input type="checkbox" checked={draftSelection.categories.length===Object.keys(categoryLabels).length&&draftSelection.includeKnowledge} onChange={event=>setDraftSelection(previous=>({...previous,categories:event.target.checked?Object.keys(categoryLabels):[],includeKnowledge:event.target.checked}))}/>All sections</label>{Object.entries(categoryLabels).map(([value,text])=><label key={value}><input type="checkbox" checked={draftSelection.categories.includes(value)} onChange={event=>chooseItem('categories',value,event.target.checked)}/>{text}</label>)}<label><input type="checkbox" checked={draftSelection.includeKnowledge} onChange={event=>setDraftSelection(previous=>({...previous,includeKnowledge:event.target.checked}))}/>Project knowledge base</label></fieldset>
        <fieldset className="compareReportFormats"><legend>File status</legend><label><input type="checkbox" checked={draftSelection.statuses.length===Object.keys(statusLabels).length} onChange={event=>setDraftSelection(previous=>({...previous,statuses:event.target.checked?Object.keys(statusLabels):[]}))}/>All statuses</label>{Object.entries(statusLabels).map(([value,text])=><label key={value}><input type="checkbox" checked={draftSelection.statuses.includes(value)} onChange={event=>chooseItem('statuses',value,event.target.checked)}/>{text}</label>)}</fieldset>
        <small>Only selected sections and file statuses are exported. HTML and PDF include linked contents. Package.pkg files are excluded.</small>
      </div><footer><button type="button" className="btn" onClick={()=>setDetailsOpen(false)}>Cancel</button><button className="btn primary" disabled={!draftFormats.length||!draftSelection.statuses.length||(!draftSelection.categories.length&&!draftSelection.includeKnowledge)||starting}>{sessionId&&!busy?'Save and prepare another report':'Save details'}</button></footer>
      </form></dialog>}
    {reportsOpen&&<dialog ref={reportsDialog} className="reportExportDialog compareReportsDialog" onCancel={event=>{event.preventDefault();setReportsOpen(false);}}>
      <header><div><span className="eyebrow">MATCHVIEW REPORTS</span><h2>Report downloads</h2><p>You can close this window while reports prepare.</p></div><button className="btn" aria-label="Close report downloads" onClick={()=>setReportsOpen(false)}><X size={18}/></button></header>
      {jobs.length>1&&<label>Prepared versions<select value={selectedJob} onChange={event=>setSelectedJob(event.target.value)}>{jobs.map((job,index)=><option key={job.id} value={job.id}>{index+1}. {job.cover.projectName} · {job.cover.description.slice(0,50)||job.cover.date} · {job.skipLayoutProperties?'layout properties skipped':'all properties'}</option>)}</select></label>}
      {current&&<><p role="status">{current.stage} · {Math.floor(current.elapsedSeconds)} seconds</p><p>{current.cover.projectName} · Validated by {current.cover.validatedBy||'not provided'} · {current.cover.date}</p>{current.cover.description&&<p>{current.cover.description}</p>}
      <div className="compareReportDownloads">{Object.entries(current.reports).map(([format,item])=><div key={format}><strong>{label(format as Format)}</strong><span>{item?.status==='ready'?'Ready':item?.status==='error'?item.error:item?.status==='running'?'Preparing…':'Queued'}</span>{item?.status==='ready'&&<a className="btn primary" href={item.downloadUrl} download={item.filename}><Download size={15}/>Download</a>}</div>)}</div></>}
      {error&&<p className="reportExportError" role="alert">{error}</p>}
      <footer><button className="btn" onClick={()=>setReportsOpen(false)}>Close</button><button className="btn" onClick={()=>{setReportsOpen(false);edit();}}>Edit details / another report</button>{sessionId&&<button className="btn primary" disabled={starting} onClick={()=>void prepare(sessionId,effectiveCover,selectedFormats,skipLayout)}>Prepare reports</button>}</footer>
    </dialog>}
  </>;
}
