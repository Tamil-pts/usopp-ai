import type {MetadataItem} from '../../../nami/src/types';
import {parseCSVMetadata,parseExcelMetadata,requireSheet2References,MetadataValidationError} from '../../../nami/src/utils/metadataParser';

export type DatasetSource={id:string;name:string;sha256:string;sheets:{name:string;rows:number;columns:number}[];header_rows?:Record<string,number>};
export interface ChatAttachment {
 id:string;name:string;kind:'metadata'|'log'|'document'|'unsupported'|'project'|'report'|'dataset';text:string;notice?:string;metadata?:MetadataItem[];projectPath?:string;projectName?:string;dataset?:DatasetSource;
 reportId?:string;report?:{id:string;kind:string;label:string;records:number;machines:number;dateFrom?:string;dateTo?:string;complete:boolean};
}
export const looksLikeLog=(text:string)=>/\b(?:writeBuffer|buffer):\s*\[[^\]]*\]\s*for groupCode\s+\d+/i.test(text);
export async function readChatAttachment(file:File):Promise<ChatAttachment> {
 const item:ChatAttachment={id:crypto.getRandomValues(new Uint32Array(2)).join('-'),name:file.name,kind:'document',text:''};
 if(/\.zip$/i.test(file.name)) {
  if(file.size>200*1024*1024)throw new Error('Choose a project ZIP smaller than 200 MB.');
  const body=new FormData();body.append('file',file);
  const response=await fetch('/api/assist/project-attachment',{method:'POST',body});
  if(response.status===404||response.status===405)throw new Error('The running server needs the project attachment update. Stop and restart the updated uSOPp application.');
  const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||'Project upload failed.');
  return {...item,kind:'project',projectPath:data.projectPath,projectName:data.projectName,notice:`${data.uploadedFiles} project files uploaded. Ask about this project in chat.`};
 }
 if(/\.(apj|pgp)$/i.test(file.name))throw new Error(`${file.name} identifies the project but does not include its source. Use the attachment button > Project folder, or attach a ZIP of the complete project.`);
 if(file.size>20*1024*1024)throw new Error(`${file.name}: choose a file smaller than 20 MB.`);
 let mappingNotice='';
 if(/\.(xlsx|xls|csv)$/i.test(file.name)) {
  try {
   const metadata=/\.csv$/i.test(file.name)?requireSheet2References(parseCSVMetadata(await file.text())):parseExcelMetadata(await file.arrayBuffer());
   if(metadata.length){
    const body=new FormData();body.append('file',file);
    const response=await fetch('/api/assist/datasets/uploads',{method:'POST',body});const data=await response.json();
    if(!response.ok)throw new Error(data.detail||'Could not prepare the workbook for analysis.');
    return {...item,kind:'metadata',metadata,dataset:data,notice:`${metadata.length} metadata parameters`};
   }
  }catch(error){if(error instanceof MetadataValidationError&&error.issues.some(issue=>issue.startsWith('Missing Sheet2 reference:')))throw error;mappingNotice=`Not usable as PLC metadata: ${error instanceof Error?error.message:'invalid workbook'}.`;}
 }
 // Text is decoded on the backend as well, so UTF-16 source files keep their characters.
 const body=new FormData();body.append('file',file);
 const response=await fetch('/api/assist/attachment',{method:'POST',body});
 if(response.status===404||response.status===405)throw new Error('The running server needs the attachment update. Stop and restart the updated uSOPp application.');
 const data=await response.json().catch(()=>({}));
 if(!response.ok)throw new Error(data.detail||`Cannot read ${file.name}. Restart uSOPp after updating it.`);
 if(data.report?.id)return {...item,kind:'report',text:String(data.text||''),notice:data.notice,reportId:data.report.id,report:data.report,dataset:data.dataset};
 if(data.dataset)return {...item,kind:'dataset',text:String(data.text||''),notice:data.notice,dataset:data.dataset};
 const text=String(data.text||'');
 return {...item,text,kind:looksLikeLog(text)?'log':data.readable?'document':'unsupported',notice:[mappingNotice,data.notice].filter(Boolean).join(' ')};
}

export async function copyChatText(text:string):Promise<boolean> {
 try {
  if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);
  else {
   const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);
   try {area.select();if(!document.execCommand('copy'))return false;}finally{area.remove();}
  }
  return true;
 }catch{return false;}
}
