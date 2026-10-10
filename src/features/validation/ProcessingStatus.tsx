import {AlertCircle,CheckCircle2,FileUp,ShieldCheck,Sparkles} from 'lucide-react';

export function ProcessingStatus({busy,message,error,uploadProgress}:{busy:string;message:string;error:string;uploadProgress?:{uploaded:number;total:number}|null}) {
  if(!busy&&!message&&!error)return null;
  const kind=error?'error':busy==='metadata'?'generation':busy==='validate'?'validation':busy==='upload'?'upload':'success';
  const Icon=error?AlertCircle:busy==='metadata'?Sparkles:busy==='validate'?ShieldCheck:busy==='upload'?FileUp:CheckCircle2;
  const title=error?'Action could not be completed':busy==='metadata'?'Generating metadata…':busy==='validate'?'Running validation…':busy==='upload'?'Reading metadata file…':'Completed';
  const transferring=!!busy&&!!uploadProgress&&uploadProgress.total>0&&uploadProgress.uploaded<uploadProgress.total;
  const detail=error||(!busy?message:transferring?`Transferring the selected project in reliable batches: ${uploadProgress.uploaded.toLocaleString()} of ${uploadProgress.total.toLocaleString()} files.`:busy==='metadata'?'Reading project logic and knowledge mappings to create the workbook.':busy==='validate'?'Checking configured packets, offsets and metadata.':'Preparing the selected workbook for viewing and validation.');
  return <div className={'card processingStatus '+kind} role={error?'alert':'status'} aria-live="polite">
    <Icon className="processingIcon" size={24}/><div className="processingCopy"><strong>{title}</strong><p>{detail}</p></div>
    {!!busy&&<div className="processingTrack" aria-hidden="true"><span/></div>}
  </div>;
}
