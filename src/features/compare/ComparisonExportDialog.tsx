import {useEffect,useRef,type ReactNode} from 'react';
import {Download,FileCheck2,FolderGit2,GitCompareArrows,X} from 'lucide-react';
import './comparison-export-dialog.css';

export type ComparisonDetails={projectName:string;projectId?:string;department?:string;base?:string;developed?:string;description:string;objectiveScope?:string;reviewedBy?:string;approvedBy:string};

const exportStatusLabels={modified:'Modified',added:'Added',removed:'Removed',unchanged:'Unchanged',unresolved:'Needs review'};
export type ExportStatus=keyof typeof exportStatusLabels;

export function ComparisonExportStatuses({available,selected,onChange,counts}:{available:readonly ExportStatus[];selected:readonly ExportStatus[];onChange:(statuses:ExportStatus[])=>void;counts?:Record<ExportStatus,number>}){
 const differences=available.filter(status=>status!=='unchanged');
 const isSelected=(statuses:readonly ExportStatus[])=>statuses.length===selected.length&&statuses.every(status=>selected.includes(status));
 const count=(statuses:readonly ExportStatus[])=>counts?statuses.reduce((total,status)=>total+counts[status],0):undefined;
 const choices=[{label:'All',statuses:available},{label:'Differences',statuses:differences}];
 const selectedCount=count(selected);
 return <fieldset className="comparisonExportStatuses">
  <legend>File status</legend>
  <div className="comparisonStatusPresets">{choices.map(({label,statuses})=><label key={label}>
   <input type="checkbox" checked={isSelected(statuses)} onChange={event=>onChange(event.target.checked?[...statuses]:[])}/>
   <span>{label}</span>{counts&&<span className="comparisonStatusCount" aria-hidden="true">{count(statuses)}</span>}
  </label>)}</div>
  {available.map(status=><label key={status}>
   <input type="checkbox" checked={selected.includes(status)} onChange={event=>onChange(available.filter(value=>value===status?event.target.checked:selected.includes(value)))}/>
   <span>{exportStatusLabels[status]}</span>{counts&&<span className="comparisonStatusCount" aria-hidden="true">{counts[status]}</span>}
  </label>)}
  <small aria-live="polite">{!selected.length?'Select at least one status.':selectedCount!==undefined?`${selectedCount} ${selectedCount===1?'section':'sections'} selected`:'Choose any combination of statuses.'}</small>
 </fieldset>;
}
export function ComparisonCoverFields({value,onChange,disabled=false}:{value:ComparisonDetails;onChange:(key:keyof ComparisonDetails,value:string)=>void;disabled?:boolean}){
 const input=(key:keyof ComparisonDetails,label:string,long=false)=><label className={key==='projectName'?'comparisonFullRow':long?'comparisonWide':''} key={key}>{label}{long?<textarea rows={3} maxLength={2000} value={value[key]||''} onChange={e=>onChange(key,e.target.value)}/>:<input autoFocus={key==='projectName'} maxLength={200} value={value[key]||''} onChange={e=>onChange(key,e.target.value)}/>}</label>;
 return <fieldset className="comparisonCoverFields" disabled={disabled}><section><h3><FolderGit2 size={17}/>Project information</h3><div className="comparisonFieldGrid">{input('projectName','Project name')}{input('projectId','Project ID')}{input('department','Department')}{input('description','Description',true)}{input('objectiveScope','Objective / scope',true)}</div></section><section><h3><GitCompareArrows size={17}/>Compared sources</h3><div className="comparisonFieldGrid">{input('base','Base / reference')}{input('developed','Developed / compare')}</div></section><section><h3><FileCheck2 size={17}/>Review details</h3><div className="comparisonFieldGrid">{input('reviewedBy','Reviewed by')}{input('approvedBy','Approved by')}</div><small>Leave approval blank until approved. Entered names are printed on the report; they do not grant a WorkHub approval.</small></section></fieldset>;
}

export function ComparisonExportDialog({title,subtitle,children,options,onClose,onSubmit,submitLabel,busy=false,disabled=false,error='',hint,progressText=''}:{title:string;subtitle:string;children:ReactNode;options:ReactNode;onClose:()=>void;onSubmit:()=>void;submitLabel:string;busy?:boolean;disabled?:boolean;error?:string;hint:string;progressText?:string}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const node=dialog.current;node?.showModal();return()=>{if(node?.open)node.close()}},[]);
 return <dialog ref={dialog} className="comparisonExportDialog" aria-labelledby="comparisonExportTitle" onCancel={e=>{e.preventDefault();if(!busy)onClose();}} onClick={e=>{if(e.target===e.currentTarget&&!busy){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();}}}><form onSubmit={e=>{e.preventDefault();if(!busy&&!disabled)onSubmit()}} aria-busy={busy}><header><div className="comparisonExportIcon"><Download size={21}/></div><div><span>MATCHVIEW · REPORT EXPORT</span><h2 id="comparisonExportTitle">{title}</h2><p>{subtitle}</p></div><button className="btn" type="button" disabled={busy} onClick={onClose} aria-label="Close export options"><X size={18}/></button></header><fieldset className="comparisonExportBody" disabled={busy}><div className="comparisonExportMain">{children}</div><aside className="comparisonExportOptions"><h3>Export options</h3>{options}<p className="comparisonExportHint">{hint}</p></aside></fieldset>{error&&<p className="comparisonExportError" role="alert">{error}</p>}<footer><small role={busy?'status':undefined} aria-live="polite">{busy?(progressText||'Preparing your report...'):'Review the details and selected content before exporting.'}</small><button type="button" className="btn" disabled={busy} onClick={onClose}>Cancel</button><button type="submit" className="btn primary" disabled={busy||disabled}><Download size={16}/>{busy?'Preparing…':submitLabel}</button></footer></form></dialog>;
}
