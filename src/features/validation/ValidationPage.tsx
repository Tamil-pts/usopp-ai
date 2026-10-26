import {PacketGroupTable} from './PacketGroupTable';
import {useEffect,useState} from 'react';
import {LocalFolderTree,LocalFileTree} from '../../shared/LocalFileBrowser';
import {Badge} from '../../shared/ui';
import type {MetaCol} from '../../shared/types';
import type {ValidationWorkspace} from './useValidationWorkspace';
import {normalizeResult} from './normalizeResult';
import {TablePage} from './ValidationViews';
import {WorkbookViewer} from './WorkbookViewer';
import {ProjectSummary} from './ProjectSummary';
import {ProcessingStatus} from './ProcessingStatus';
import {LoaderCircle,ShieldCheck,Sparkles} from 'lucide-react';
import {WriteSTGenerator} from './WriteSTGenerator';
import {ProcessingTimePopup} from '../../shared/ProcessingTimePopup';
import './validation.css';
import {ValidationSourceEditor,type SourceSelection} from './ValidationSourceEditor';
import {DEPARTMENTS} from '../rules/library';

const tabs=[['packets','Configured packets'],['offset','ByteMap'],['metadata','MetaWorks'],['dropdown','Dropdowns'],['write-st','Write ST'],['generated','MetaWorks · Generated'],['uploaded','MetaWorks · Uploaded']] as const;
export function ValidationPage({workspace:w,metaCols,departments=DEPARTMENTS}:{workspace:ValidationWorkspace;metaCols:MetaCol[];departments?:string[]}) {
  const [tab,setTab]=useState<string>('packets');
  const [browser,setBrowser]=useState<'project'|'metadata'|null>(null);
  const [group,setGroup]=useState('');
  const data=w.result?normalizeResult(w.result):null;
  const [draftProject,setDraftProject]=useState(w.localProjectPath);
  const [draftMetadata,setDraftMetadata]=useState(w.localMetadataPath);
  const [pathError,setPathError]=useState('');
  const [sourceSelection,setSourceSelection]=useState<SourceSelection|null>(null);
  useEffect(()=>setDraftProject(w.localProjectPath),[w.localProjectPath]);
  useEffect(()=>setDraftMetadata(w.localMetadataPath),[w.localMetadataPath]);
  useEffect(()=>{if(w.generated)setTab('generated');else if(w.result)setTab('packets')},[w.generated,w.result]);
  const usePath=async(kind:'folder'|'file',path:string)=>{
    setPathError('');
    try{const r=await fetch('/api/local/path/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,path,extensions:kind==='file'?['.xlsx','.xls']:[]})});const j=await r.json();if(!r.ok)throw new Error(j.detail);if(kind==='folder'){w.selectProject(j.path,j.name);setDraftProject(j.path)}else{w.selectMetadata(j.path,j.name);setDraftMetadata(j.path)}}catch(e:any){setPathError(e.message)}
  };
  const ready=!!w.localProjectPath||!!w.projectFiles.length;
  const transferring=!!w.uploadProgress&&w.uploadProgress.uploaded<w.uploadProgress.total;
  return <>
    <ProcessingTimePopup active={!!w.busy} label={transferring?'Project upload':w.busy==='metadata'?'Metadata generation':w.busy==='validate'?'Project validation':'File preparation'} progress={transferring&&w.uploadProgress?100*w.uploadProgress.uploaded/w.uploadProgress.total:undefined} defaultEstimate={w.busy==='metadata'?55:w.busy==='validate'?75:25}/>
    <div className="pageHead"><div><div className="eyebrow">ENGINEERING WORKSPACE</div><h1>ByteMap</h1><p>Validate SpinConnect packets, offsets and metadata against the selected B&R project. Review workbook edits before using them.</p></div>{w.result?.downloadExcelUrl&&<a className="btn" href={w.result.downloadExcelUrl}>Download validation report</a>}</div>
    {(w.result?.testId||w.generated?.testId)&&<p className="mono">Test ID: {w.generated?.testId||w.result?.testId}</p>}
    <div className="validationTopBar">
      <ProcessingStatus busy={w.busy} message={w.message} error={w.error||pathError} uploadProgress={w.uploadProgress}/>
      <div className="card projectActions"><span>{w.busy==='metadata'?'Generating metadata…':w.busy==='validate'?'Validation in progress…':ready?'Project ready':'Select a project to begin'}</span><label className="machineDepartmentSelect">Machine / department<select className="textInput" value={w.machineDepartment} disabled={!!w.busy} onChange={e=>w.setMachineDepartment(e.target.value)}>{departments.map(d=><option key={d}>{d}</option>)}</select></label><div className="actions"><button className="btn" disabled={!!w.busy} onClick={()=>{w.clearProject();setDraftProject('')}}>Clear project</button><button className={'btn generationButton '+(w.busy==='metadata'?'isProcessing':'')} aria-busy={w.busy==='metadata'} disabled={!ready||!!w.busy} onClick={()=>{setPathError('');void w.generateMetadata()}}>{w.busy==='metadata'?<LoaderCircle size={17} className="spin"/>:<Sparkles size={17}/>} {w.busy==='metadata'?'Generating…':'Generate metadata'}</button><button className={'btn validationButton '+(w.busy==='validate'?'isProcessing':'')} aria-busy={w.busy==='validate'} disabled={!ready||!!w.busy} onClick={()=>{setPathError('');void w.runValidation()}}>{w.busy==='validate'?<LoaderCircle size={17} className="spin"/>:<ShieldCheck size={17}/>} {w.busy==='validate'?'Validating…':'Run validation'}</button></div></div>
    </div>
    <LocalFolderTree open={browser==='project'} selectedPath={w.localProjectPath} onClose={()=>setBrowser(null)} onSelect={(p,n)=>{setPathError('');w.selectProject(p,n);setDraftProject(p)}}/>
    <LocalFileTree open={browser==='metadata'} selectedPath={w.localMetadataPath} onClose={()=>setBrowser(null)} onSelect={(p,n)=>{setPathError('');w.selectMetadata(p,n);setDraftMetadata(p)}}/>
    <ProjectSummary workspace={w} onViewMetadata={()=>setTab('uploaded')}
      projectControls={<div className="validationInputControls">
        <label className="pathLabel">Project path<input className="textInput" disabled={!!w.busy} value={draftProject} onChange={e=>setDraftProject(e.target.value)} placeholder="Project folder or .apj path"/></label>
        <div className="actions"><button className="btn primary" disabled={!!w.busy} onClick={()=>usePath('folder',draftProject)}>Use path</button><button className="btn" disabled={!!w.busy} onClick={()=>setBrowser('project')}>Browse This PC</button></div>
        <label className="validationUpload">Upload folder<input aria-label="Upload project folder" disabled={!!w.busy} type="file" multiple {...({webkitdirectory:'',directory:''} as any)} onChange={e=>{const files=Array.from(e.target.files||[]);if(files.length){w.selectProject('',files[0].webkitRelativePath.split('/')[0],files);setDraftProject('')}}}/></label>
        <details><summary>Project name</summary><input className="textInput" aria-label="Project name" value={w.projectName} disabled={!!w.busy} onChange={e=>w.setProjectName(e.target.value)}/></details>
      </div>}
      metadataControls={<div className="validationInputControls">
        <label className="pathLabel">Metadata path<input className="textInput" disabled={!!w.busy} value={draftMetadata} onChange={e=>setDraftMetadata(e.target.value)} placeholder="Reference workbook .xlsx or .xls"/></label>
        <div className="actions"><button className="btn primary" disabled={!!w.busy} onClick={()=>usePath('file',draftMetadata)}>Use path</button><button className="btn" disabled={!!w.busy} onClick={()=>setBrowser('metadata')}>Browse This PC</button><button className="btn" disabled={!!w.busy} onClick={()=>{w.selectMetadata('','');setDraftMetadata('')}}>Clear metadata</button></div>
        <label className="validationUpload">Upload workbook<input aria-label="Upload metadata workbook" disabled={!!w.busy} type="file" accept=".xlsx,.xls" onChange={e=>{const file=e.target.files?.[0];if(file)void w.uploadMetadata(file);e.target.value=''}}/></label>
      </div>}/>
    {w.sourceChanged&&<div className="validationStale" role="status">Source files were edited. These results and datatype declarations describe the previous source. Run validation again.</div>}
    <div className="featureTabs" role="tablist">{tabs.map(([id,label])=><button role="tab" aria-selected={tab===id} className={'chip '+(tab===id?'active':'')} key={id} onClick={()=>setTab(id)}>{label}</button>)}</div>
    <div hidden={tab!=='write-st'}><WriteSTGenerator workspace={w}/></div>
    {sourceSelection&&w.result?.sessionId&&<ValidationSourceEditor sessionId={w.result.sessionId} selection={sourceSelection} datatypes={w.result.datatypeIndex||[]} onClose={()=>setSourceSelection(null)} onSaved={w.markSourceChanged}/>}
    {['packets','offset','metadata','dropdown'].includes(tab)&&!w.result&&<div className="card emptyState"><h3>No validation results yet</h3><p>Select the project and run validation using the controls above.</p></div>}
    {tab==='packets'&&w.result&&<PacketGroupTable groups={w.result.groups||[]} issues={w.result.issues||[]} onOffsets={code=>{setGroup(code);setTab('offset')}} onSource={(path,line)=>setSourceSelection({path,line,mode:'source'})}/>}
    {tab==='offset'&&w.result&&<><div className="actions"><label>Group code <select className="textInput" value={group} onChange={e=>setGroup(e.target.value)}><option value="">All groups</option>{(w.result.groups||[]).map((g:any)=><option key={g.groupCode} value={String(g.groupCode)}>GC{g.groupCode}</option>)}</select></label></div><TablePage title="ByteMap" desc="PLC field sizes and buffer offsets, including memcpy and direct byte assignments. Metadata offsets exclude the 5-byte header." type="offset" onSource={(row,mode)=>setSourceSelection({path:row.sourceFile,line:row.lineNumber,tag:row.parameter,mode})} rows={(data?.offsetRows||[]).filter((r:any)=>!group||r.gc===`GC${group}`)}/></>}
    {tab==='metadata'&&w.result&&<TablePage title="MetaWorks" desc="Compare PLC and reference metadata; approved mappings are stored in the knowledge base." type="metadata" rows={data?.metadataRows||[]} metaCols={metaCols} projectName={w.result.projectName}/>}
    {tab==='dropdown'&&w.result&&<TablePage title="Dropdown validation" desc="HMI values and metadata mappings by group and tag code." type="dropdown" rows={data?.dropdownRows||[]}/>}
    {tab==='generated'&&w.generated?.alarmSourceSummary&&<p>Alarm catalog: {w.generated.alarmSourceSummary.MAPPED||0} caption rows mapped to transmitted bits in Sheet2.</p>}
    <div hidden={tab!=='generated'}>{!!w.generated?.alarmWarnings?.length&&<details className="card" open><summary>GC 30 alarm source findings ({w.generated.alarmWarnings.length})</summary><p>Sheet2 follows the bytes copied by the PLC. Review these findings when alarm captions are missing.</p>{w.generated.alarmWarnings.map((issue:any,index:number)=><div key={index}><b>{issue.validation_type}</b><p>Expected: {issue.expected}. Actual: {issue.actual}.</p><p>{issue.suggested_fix}</p><p className="mono">{issue.source_file}:{issue.line_number}</p></div>)}</details>}<WorkbookViewer source="generated" path={w.generated?.workbookPath} sessionId={w.generated?.sessionId} projectName={w.generated?.projectName||w.projectName} onUse={w.selectMetadata}/></div>
    <div hidden={tab!=='uploaded'}><WorkbookViewer source="uploaded" path={w.localMetadataPath} projectName={w.projectName} onUse={w.selectMetadata}/></div>
  </>;
}
