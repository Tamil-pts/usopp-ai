import {hub,type HubRow} from '../projectApi';
export type Row=HubRow;
export const ROOT='/api/workhub/growth';
export const api=(path:string,body?:unknown,method?:string,signal?:AbortSignal)=>hub('/growth'+path,body,method,signal);
export const list=(value:unknown):Row[]=>Array.isArray(value)?value:[];
export const person=(users:Row[],id:number)=>users.find(user=>user.id===id)?.username||'Account unavailable';
export const status=(value:string)=>String(value||'draft').replaceAll('_',' ');
export const date=(value:string)=>value?new Date(value).toLocaleDateString():'Not recorded';
export async function attach(kind:string,key:string,file:File){const form=new FormData();form.append('file',file);const response=await fetch(ROOT+'/files/'+kind+'/'+key,{method:'POST',body:form,credentials:'same-origin'});const value=await response.json();if(!response.ok)throw Error(value.detail||'Attachment upload failed.');return value;}
