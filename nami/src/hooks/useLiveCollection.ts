import {useCallback,useEffect,useRef,useState} from 'react';
import type {GroupResponseData,MetadataItem,PLCConfig,SpinningMachineType} from '../types';
import {userStorage} from '../../../src/shared/userStorage';
import {attachDropdownsToMetadata,getPredefinedMachineMetadata} from '../data/machinePresets';
import {parseCSVMetadata,restoreSavedSheet2,validateMetadata} from '../utils/metadataParser';
import {metadataFingerprint} from '../utils/calculationDashboard';

export type LiveSample={capturedAt:number;metadataHash:string;groups:Record<number,GroupResponseData>;error?:string;simulated?:boolean};
export type TargetContext={plc:PLCConfig;metadata:MetadataItem[];sample?:LiveSample|null};
export type LiveOverview={accountId:number;revision:number;targets:{plc:PLCConfig;metadataRows:number;lastCapturedAt?:number;error?:string;collecting:boolean}[]};
export type HistoryData={samples:LiveSample[];snapshots:Record<string,TargetContext>;totalSamples:number;returnedSamples:number;sampled:boolean};
const sameTarget=(a:PLCConfig,b:PLCConfig)=>['id','ip','port','machineId','isSimulated','targetMode','endianness','machineType'].every(key=>a[key as keyof PLCConfig]===b[key as keyof PLCConfig]);
const matches=(context:TargetContext|undefined,plc:PLCConfig,metadata:MetadataItem[])=>context&&sameTarget(context.plc,plc)&&metadataFingerprint(context.metadata)===metadataFingerprint(metadata);
let factoryCarding:Promise<MetadataItem[]>|undefined;
export async function targetMetadata(plc:PLCConfig):Promise<MetadataItem[]>{
 const machine:SpinningMachineType=plc.machineType||'Carding';const saved=userStorage.getItem(`spinning_metadata_${machine}`);
 if(saved)return restoreSavedSheet2(validateMetadata(JSON.parse(saved)));
 if(machine!=='Carding')return getPredefinedMachineMetadata(machine);
 if(!factoryCarding)factoryCarding=fetch('/nami/default_metadata.csv').then(async response=>{if(!response.ok)throw new Error('Factory metadata could not be loaded.');return attachDropdownsToMetadata(parseCSVMetadata(await response.text()))}).catch(error=>{factoryCarding=undefined;throw error});
 return factoryCarding;
}
async function request<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch(url,{cache:'no-store',...options});const data=await response.json();
 if(!response.ok)throw new Error(data.detail||'Live data is unavailable.');return data;
}
export const getTargetHistory=(id:string,start:number,end:number,signal?:AbortSignal)=>request<HistoryData>(`/api/nami/live/targets/${encodeURIComponent(id)}/history?start=${start}&end=${end}&limit=300`,{signal});

export function useLiveCollection(plcs:PLCConfig[],selected:PLCConfig,metadata:MetadataItem[],enabled:boolean,onLoaded:(items:PLCConfig[])=>void,responses:Record<number,GroupResponseData>,responseContext:object){
 const [overview,setOverview]=useState<LiveOverview|null>(null),[contexts,setContexts]=useState<Record<string,TargetContext>>({}),[error,setError]=useState('');
 const revision=useRef<number|null>(null),loaded=useRef(false),onLoadedRef=useRef(onLoaded);onLoadedRef.current=onLoaded;
 const accountId=useRef<number|null>(null);
 const captures=useRef<Record<string,TargetContext>>({}),captureContext=useRef(responseContext);
 useEffect(()=>{
  if(captureContext.current!==responseContext){captureContext.current=responseContext;return}
  const capturedAt=Math.max(0,...Object.values(responses).map(row=>row.completedAt||0));if(!capturedAt||!metadata.length)return;
  const context:TargetContext={plc:selected,metadata,sample:{capturedAt,metadataHash:'manual-workspace',groups:responses}};
  captures.current[selected.id]=context;setContexts(previous=>({...previous,[selected.id]:context}));
 },[responses,responseContext,selected.id,metadata]);
 useEffect(()=>{if(!enabled)return;let cancelled=false;
  Promise.all(plcs.map(async plc=>[plc.id,{plc,metadata:await targetMetadata(plc)}] as const)).then(entries=>{if(!cancelled)setContexts(previous=>Object.fromEntries(entries.map(([id,context])=>[id,{...context,sample:matches(previous[id],context.plc,context.metadata)?previous[id].sample:null}])))}).catch(reason=>{if(!cancelled)setError(String(reason.message||reason))});
  return()=>{cancelled=true};
 },[plcs,enabled]);
 useEffect(()=>{if(metadata.length)setContexts(previous=>({...previous,[selected.id]:{plc:selected,metadata,sample:matches(previous[selected.id],selected,metadata)?previous[selected.id].sample:null}}))},[metadata,selected]);
 useEffect(()=>{if(!enabled)return;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
  const refresh=async()=>{try{
   const next=await request<LiveOverview>('/api/nami/live/targets',{signal:controller.signal});if(controller.signal.aborted)return;
   if(accountId.current!==null&&accountId.current!==next.accountId)throw new Error('The account changed. Reload DataInspect.');
   accountId.current=next.accountId;
   if(revision.current===null)revision.current=next.revision;setOverview(next);
   if(!loaded.current){loaded.current=true;onLoadedRef.current(next.targets.map(item=>item.plc))}
   await Promise.all(next.targets.filter(item=>item.plc.liveEnabled).map(async item=>{const context=await request<TargetContext>(`/api/nami/live/targets/${encodeURIComponent(item.plc.id)}/latest`,{signal:controller.signal});const local=captures.current[item.plc.id];const effective=matches(local,context.plc,context.metadata)&&(local.sample?.capturedAt||0)>(context.sample?.capturedAt||0)?local:context;if(!controller.signal.aborted)setContexts(previous=>({...previous,[item.plc.id]:effective}))}));
   if(!controller.signal.aborted)setError('');
  }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Live data is unavailable.')}
  finally{if(!controller.signal.aborted)timer=setTimeout(refresh,5000)}};
  void refresh();return()=>{controller.abort();clearTimeout(timer)};
 },[enabled]);
 const save=useCallback(async(items:PLCConfig[])=>{
  if(!enabled)return;
  if(revision.current===null)throw new Error('Live target settings are still loading. Try again in a moment.');
  const targets=await Promise.all(items.map(async plc=>({plc,metadata:await targetMetadata(plc)})));
  const next=await request<LiveOverview>('/api/nami/live/targets',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({accountId:accountId.current,revision:revision.current,targets})});
  revision.current=next.revision;setOverview(next);setContexts(Object.fromEntries(targets.map(context=>[context.plc.id,context])));setError('');
 },[enabled]);
 return {overview,contexts,error,save};
}
