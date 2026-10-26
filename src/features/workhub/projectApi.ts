import {userStorage} from '../../shared/userStorage';
export type HubRow=Record<string,any>;
export const HUB='/api/workhub';
export async function hub(path:string,body?:unknown,method?:string,signal?:AbortSignal):Promise<any>{
  const response=await fetch(HUB+path,{method:method||(body===undefined?'GET':'POST'),credentials:'same-origin',cache:'no-store',signal,
    ...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const value=await response.json().catch(()=>({detail:'The WorkHub service did not return a readable response.'}));
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'WorkHub could not complete the request.');
  return value;
}
export const bytes=(value:number)=>value>=1024**3?(value/1024**3).toFixed(2)+' GB':value>=1024**2?(value/1024**2).toFixed(1)+' MB':value>=1024?Math.round(value/1024)+' KB':value+' bytes';
export const when=(value:string)=>value?new Date(value).toLocaleString():'Not recorded';
export const dayLabel=(value:string)=>value?new Date(value+'T12:00:00').toLocaleDateString():'Unscheduled';
export async function uploadFiles(project:string,files:File[],onProgress:(value:HubRow)=>void,onFile:(value:HubRow)=>void,signal:AbortSignal){
  const completed:HubRow[]=[];const total=files.reduce((sum,file)=>sum+file.size,0);let previous=0;
  for(const file of files){
    if(signal.aborted)throw new DOMException('Upload paused','AbortError');
    const relative=file.webkitRelativePath?file.webkitRelativePath.split('/').slice(1).join('/'):file.name;
    const key='usop-workhub-upload:'+project+':'+relative+':'+file.size+':'+file.lastModified;
    let upload:HubRow|null=null;const saved=userStorage.getItem(key);
    if(saved){
      try{
        upload=await hub('/uploads/'+saved,undefined,undefined,signal);
        // A pause can occur after server commit but before its reply reaches us.
        if(upload!.status==='completed'){
          const record=await hub('/uploads/'+saved+'/finish',{},undefined,signal);
          userStorage.removeItem(key);completed.push(record);onFile(record);previous+=file.size;continue;
        }
        if(upload!.status!=='uploading')upload=null;
      }catch(error){if(signal.aborted)throw error;upload=null;}
    }
    if(!upload){upload=await hub('/projects/'+project+'/uploads',{name:relative,size:file.size},undefined,signal);userStorage.setItem(key,upload!.id);}
    let offset=Number(upload!.received||0);const chunk=Number(upload!.chunkBytes||8*1024*1024);
    while(offset<file.size){
      if(signal.aborted)throw new DOMException('Upload paused','AbortError');
      onProgress({name:relative,loaded:previous+offset,total,phase:'Uploading'});
      const response=await fetch(HUB+'/uploads/'+upload!.id+'?offset='+offset,{method:'PUT',body:file.slice(offset,offset+chunk),signal,headers:{'Content-Type':'application/octet-stream'}});
      const result=await response.json();if(!response.ok)throw new Error(result.detail||'Upload interrupted. Resume using the same files.');offset=result.received;
    }
    onProgress({name:relative,loaded:previous+offset,total,phase:'Verifying and saving'});
    const record=await hub('/uploads/'+upload!.id+'/finish',{},undefined,signal);
    userStorage.removeItem(key);completed.push(record);onFile(record);previous+=file.size;
  }
  onProgress({name:'Files saved',loaded:total,total,phase:'Complete'});return completed;
}
