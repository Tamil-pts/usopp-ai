import {hub,HUB,type HubRow as Row} from '../projectApi';
export const studioBase=(project:string,document:string)=>'/projects/'+project+'/studio/documents/'+document;
export const studio=(project:string,document:string,path='',body?:unknown,method?:string)=>hub(studioBase(project,document)+path,body,method);
export async function preview(project:string,document:string,payload:Row,signal:AbortSignal){
 const r=await fetch(HUB+studioBase(project,document)+'/preview',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify(payload),signal});
 if(!r.ok){const e=await r.json().catch(()=>({detail:'The document preview could not be prepared.'}));throw Error(e.detail||'Could not prepare the page layout.');}
 return r.text();
}
