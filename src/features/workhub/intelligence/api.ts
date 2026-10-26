import {hub,HUB,type HubRow} from '../projectApi';
export type Row=HubRow;
export const api=(project:string,path:string,body?:unknown,method?:string,signal?:AbortSignal)=>hub('/projects/'+project+'/intelligence'+path,body,method,signal);
export const url=(project:string,path:string)=>HUB+'/projects/'+project+'/intelligence'+path;
export const rows=(value:unknown):Row[]=>Array.isArray(value)?value:[];
export const label=(value:unknown,missing='Not confirmed'):string=>value==null||value===''?missing:typeof value==='string'?value:JSON.stringify(value);
export const stamp=(value:number|null|undefined)=>value==null?'Not provided':`${Math.floor(value/3600)?Math.floor(value/3600)+':':''}${String(Math.floor(value/60)%60).padStart(2,'0')}:${String(Math.floor(value)%60).padStart(2,'0')}`;
export const KIND:Record<string,string>={mom:'MOM',frd:'FRD',flowchart:'Flowchart',plan:'Timeline proposal',source:'Document',note:'Note'};
export function saveBlob(blob:Blob,name:string){const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),2000);}
export async function download(project:string,path:string,name:string){const response=await fetch(url(project,path),{credentials:'same-origin'});if(!response.ok){const value=await response.json().catch(()=>({}));throw Error(value.detail||'The document could not be exported.');}saveBlob(await response.blob(),name);}
