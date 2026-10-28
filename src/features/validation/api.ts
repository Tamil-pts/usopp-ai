import type {ProjectInput} from '../../shared/projectInput';
import {toolProjectHeaders} from '../../shared/toolProject';
import {projectSourceFiles} from '../../shared/projectInput';

export type BoolMetadataMode='BOOL'|'USINT';

type ValidationRequest = ProjectInput & {
  localProjectPath: string;
  localMetadataPath: string;
  metadata: File | null;
  machineDepartment?:string;
  boolMetadataMode:BoolMetadataMode;
  onUploadProgress?:(uploaded:number,total:number)=>void;
};
type MetadataRequest = ProjectInput & {localProjectPath: string;machineDepartment?:string;boolMetadataMode:BoolMetadataMode;onUploadProgress?:(uploaded:number,total:number)=>void};

async function responseData(response: Response, action: string) {
  const text = await response.text();
  let data:any = {};
  try { data = JSON.parse(text); } catch { /* Preserve the API status as the useful error. */ }
  if (!response.ok) throw new Error(data.detail || `${action} failed (HTTP ${response.status})`);
  return data;
}

const uploadedMetadata = new WeakMap<File, Promise<any>>();
const stagedProjects = new WeakMap<File[], Promise<any>>();
export function prepareMetadata(file:File) {
  let pending=uploadedMetadata.get(file);
  if(!pending){const form=new FormData();form.append('metadata',file);pending=fetch('/api/metadata/upload',{method:'POST',body:form}).then(r=>responseData(r,'Metadata upload')).catch(e=>{uploadedMetadata.delete(file);throw e});uploadedMetadata.set(file,pending)}
  return pending;
}

function projectUploadBatches(files:File[]) {
  const batches:File[][]=[];
  let batch:File[]=[];
  let bytes=0;
  for(const file of files){
    if(batch.length&&(batch.length>=100||bytes+file.size>24*1024*1024)){batches.push(batch);batch=[];bytes=0}
    batch.push(file);bytes+=file.size;
  }
  if(batch.length)batches.push(batch);
  return batches;
}

export async function stageBrowserProject(input:ProjectInput,onProgress?:(uploaded:number,total:number)=>void) {
  const files=projectSourceFiles(input.projectFiles);
  let pending=stagedProjects.get(input.projectFiles);
  if(!pending){
    pending=(async()=>{
      const total=files.length;
      onProgress?.(0,total);
      let uploaded=0;
      try{
        const start=await fetch('/api/project-upload/start',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({project_name:input.projectName,total_files:total}),
        }).then(r=>responseData(r,'Project upload'));
        for(const batch of projectUploadBatches(files)){
          const form=new FormData();form.append('session_id',start.sessionId);
          batch.forEach(file=>form.append('project_files',file,file.webkitRelativePath||file.name));
          const result=await fetch('/api/project-upload/chunk',{method:'POST',body:form}).then(r=>responseData(r,'Project upload'));
          uploaded=Number(result.receivedFiles||uploaded+batch.length);onProgress?.(uploaded,total);
        }
        return await fetch('/api/project-upload/finish',{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:start.sessionId}),
        }).then(r=>responseData(r,'Project upload'));
      }catch(error:any){
        const networkFailure=error instanceof TypeError||/failed to fetch|networkerror|load failed/i.test(String(error?.message||''));
        throw new Error(networkFailure
          ?`Browser transfer stopped after ${uploaded.toLocaleString()} of ${total.toLocaleString()} files. Keep uSOPp open and retry, or select the project with Browse This PC.`
          :error?.message||'Project upload failed.');
      }
    })().catch(error=>{stagedProjects.delete(input.projectFiles);throw error});
    stagedProjects.set(input.projectFiles,pending);
  }
  const result=await pending;
  onProgress?.(files.length,files.length);
  return result;
}

export async function validateProject(input: ValidationRequest) {
  const metadataPath=input.metadata?(await prepareMetadata(input.metadata)).path:input.localMetadataPath;
  const projectPath=input.localProjectPath||(
    input.projectFiles.length?(await stageBrowserProject(input,input.onUploadProgress)).projectPath:''
  );
  if (projectPath) {
    const response = await fetch('/api/local/validate', {
      method:'POST', headers:{'Content-Type':'application/json',...toolProjectHeaders('bytemap')},
      body:JSON.stringify({project_path:projectPath,project_name:input.projectName,metadata_path:metadataPath,machine_department:input.machineDepartment||'All',bool_metadata_mode:input.boolMetadataMode})
    });
    return responseData(response, 'Validation');
  }
  throw new Error('Select a project folder first.');
}

export async function generateProjectMetadata(input: MetadataRequest) {
  const projectPath=input.localProjectPath||(
    input.projectFiles.length?(await stageBrowserProject(input,input.onUploadProgress)).projectPath:''
  );
  if (projectPath) {
    const response = await fetch('/api/local/generate-metadata', {
      method:'POST', headers:{'Content-Type':'application/json',...toolProjectHeaders('bytemap')},
      body:JSON.stringify({project_path:projectPath,project_name:input.projectName,machine_department:input.machineDepartment||'All',bool_metadata_mode:input.boolMetadataMode})
    });
    return responseData(response, 'Metadata generation');
  }
  throw new Error('Select a project folder first.');
}
