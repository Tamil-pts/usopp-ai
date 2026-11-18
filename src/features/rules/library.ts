import {useCallback,useEffect,useState} from 'react';
import type {Status} from '../../shared/types';
import {uiStatus} from '../../shared/resultEvidence';

export const DEPARTMENTS=['All','Blow Room','Carding','Breaker','Finisher','Comber','Lapformer','Speedframe','Ringframe','RAP','Auto Winder'];
export const CATEGORIES=['PLC logic + HMI','Logic / declaration','Declaration','Logic','Logic with condition','Group code wise parameter check','Logic traceability in various subroutines','Library check','HMI screen + datapoint mapped','HMI text groups','HMI touch pad','HMI alarm declaration','PLC configuration'];
export const FEEDBACK_LABELS=['Correct','Incorrect','Partially correct','Ignore','Create rule from this'];
export function categoryFor(rule:any){
 if(rule?.category)return rule.category;
 const kind=String(rule?.kind||'');
 if(kind==='lot_name_packet_hmi')return 'Cross-domain traceability';
 if(kind.includes('hmi'))return 'HMI screen / datapoint';
 if(kind.includes('packet')||kind.includes('group'))return 'Packet / Group Code';
 return 'Structured Text logic';
}
export function badgeStatus(value:any):Status{
 return uiStatus(value);
}
export async function apiJson(url:string,body?:any,method?:string){
 const requestMethod=method||(body===undefined?'GET':'POST');
 const response=await fetch(url,{method:requestMethod,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
 const data=await response.json();if(!response.ok)throw new Error(data.detail||'Request failed.');return data;
}
export function useRuleLibrary(revision=0){
 const [rules,setRules]=useState<any[]>([]);const [error,setError]=useState('');
 const reload=useCallback(async()=>{
  try{
   const data=await apiJson('/api/rules/library');setRules(data.rules||[]);setError('');
  }catch(e:any){setError(e.message)}
 },[]);
 useEffect(()=>{void reload()},[reload,revision]);
 return {rules,error,reload};
}
