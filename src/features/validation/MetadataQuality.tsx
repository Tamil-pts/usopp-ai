import {useEffect,useState} from 'react';

export type QualityIssue={sheet?:string;row?:number;groupCode?:number|string;parameter?:string;check:string;expected:unknown;actual:unknown;status:string};
export type QualityStage={id:string;status:string;checked:number;issues:QualityIssue[];detail:string;workbookStatus?:string;sourceCompared?:boolean};
export type OffsetQuality={sheet:string;row:number;status:string;offset:number|null;expectedOffsets:number[];sourceOffset:number|null;size:number|null;issues:QualityIssue[]};
export type QualityReport={ready:boolean;stages:QualityStage[];offsetRows:OffsetQuality[]};
export type QualityState={report:QualityReport|null;loading:boolean;error:string;dirty?:boolean};
export type QualityFocus={stage:string;request:number};

export function useMetadataQuality(input:{workbookPath:string;sheets:unknown[];source:string;referenceSessionId?:string;modelId:string;machineDepartment?:string}){
  const [state,setState]=useState<QualityState>({report:null,loading:false,error:''});
  const {workbookPath,sheets,source,referenceSessionId,modelId,machineDepartment}=input;
  useEffect(()=>{
    if(!workbookPath||!sheets.length){setState({report:null,loading:false,error:''});return}
    const controller=new AbortController();
    setState(previous=>({...previous,loading:true,error:''}));
    const timer=setTimeout(()=>{
      fetch('/api/metadata/view/quality',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
        body:JSON.stringify({workbookPath,sheets,source,referenceSessionId,modelId,machineDepartment})})
        .then(async response=>{const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Metadata quality checks failed.');return result as QualityReport})
        .then(report=>{if(!controller.signal.aborted)setState({report,loading:false,error:''})})
        .catch(error=>{if(!controller.signal.aborted)setState({report:null,loading:false,error:error.message})});
    },300);
    return()=>{clearTimeout(timer);controller.abort()};
  },[workbookPath,sheets,source,referenceSessionId,modelId,machineDepartment]);
  return state;
}

const steps=[['bytes','Byte check'],['sheet2','Sheet2'],['duplicates','Duplicate'],['dataModel','Data Model']] as const;
const statusLabel=(status:string)=>({PASS:'OK',FAIL:'Fix',REVIEW:'Review',PENDING:'Pending',NOT_APPLICABLE:'N/A'}[status]||'Pending');

export function MetadataRoadmap({state,onSelect}:{state?:QualityState;onSelect?:(stage:string)=>void}){
  const ready=Boolean(state?.report?.ready&&!state.loading&&!state.error&&!state.dirty);
  const ending=state?.loading?'Checking…':state?.error?'Check unavailable':state?.dirty?'Save changes':ready?'Ready to serve':'Review required';
  return <nav className="metadataRoadmap" aria-label="Metadata quality roadmap">
    {steps.map(([id,label])=>{const stage=state?.report?.stages.find(stage=>stage.id===id);const status=state?.loading?'PENDING':stage?.status||'PENDING';const findings=(stage?.issues||[]).slice(0,3).map(issue=>`${issue.sheet||issue.parameter||''}${issue.row?` row ${issue.row}`:''}: ${issue.check}; expected ${String(issue.expected??'—')}; actual ${String(issue.actual??'—')}`).join('\n');return <span className="metadataRoadmapStep" key={id}><button type="button" className={`metadataRoadmapItem ${status.toLowerCase()}`} onClick={()=>onSelect?.(id)} title={state?.error||[stage?.detail,findings].filter(Boolean).join('\n')||'Not checked yet'}><span>{label}</span><b>{state?.loading?'…':statusLabel(status)}{status==='FAIL'&&stage?.issues.length?` (${stage.issues.length})`:''}</b></button><span aria-hidden="true" className="metadataRoadmapArrow">→</span></span>})}
    <span className={`metadataRoadmapReady ${ready?'ready':''}`} role="status">{ending}</span>
  </nav>;
}

export function qualityDescription(row:OffsetQuality|undefined){
  if(!row)return '';
  const notes=row.issues.map(issue=>`${issue.check}: expected ${String(issue.expected??'—')}; actual ${String(issue.actual??'—')}`);
  if(!notes.length)notes.push(`Workbook byte offset ${row.offset}; expected ${row.expectedOffsets.join(' / ')||'unresolved'}; field size ${row.size??'unresolved'} bytes.`);
  if(row.sourceOffset!==null)notes.push(`PLC source offset: ${row.sourceOffset} bytes.`);
  return notes.join(' ');
}
