import {lazy,Suspense,useEffect,useState} from 'react';
import {DocumentDraft} from './intelligence/DocumentDraft';
import type {HubRow as Row} from './projectApi';
import {flushQualityDraft} from './quality/bridge';
import './intelligence/intelligence.css';
const MeetingTools=lazy(()=>import('./intelligence/ProjectIntelligence'));

export default function NativeDocumentWorkspace({detail,documentId,users,userId,onChanged}:{detail:Row;documentId:string;users:Row[];userId:number;onChanged:()=>Promise<void>}){
 const [tools,setTools]=useState(false),[source,setSource]=useState<Row|null>(null),[error,setError]=useState(''),scope=detail.project.id;
 const openTools=(value:boolean)=>void flushQualityDraft().then(()=>setTools(value)).catch(e=>setError(e.message));
 useEffect(()=>{const open=(event:Event)=>{if((event as CustomEvent).detail?.scope===scope)openTools(true);};window.addEventListener('workhub-meeting-tools',open);return()=>window.removeEventListener('workhub-meeting-tools',open);},[scope]);
 return <div className="wh-native-document">{error&&<p className="wh-error" role="alert">{error}</p>}{tools?<><button className="btn" onClick={()=>openTools(false)}>Back to meeting document</button><Suspense fallback={<p>Opening meeting tools...</p>}><MeetingTools detail={detail} workspace="meetings" users={users} userId={userId} canManage={detail.can_manage} onChanged={onChanged} onOpen={()=>{}} onEdit={()=>{}} canEdit={()=>false} onSchedule={async()=>{}}/></Suspense></>:<DocumentDraft project={scope} documentId={documentId} users={users} userId={userId} defaultReviewer={detail.project.reviewer_id} startEditing onChanged={()=>void onChanged().catch(e=>setError(e.message))} onSource={setSource} onOpenFile={(_doc,rev)=>{if(rev.file_id)window.open('/api/workhub/files/'+rev.file_id+'/download','_blank','noopener');}} onEditFlow={()=>openTools(true)}/>}{source&&<div className="wh-backdrop"><section className="wh-dialog" role="dialog" aria-modal="true" aria-label="Document source"><header><h3>{source.filename||source.label||'Document source'}</h3><button className="btn" onClick={()=>setSource(null)}>Close source</button></header><p className="wh-preserve">{source.text||'Original source retained in the document record.'}</p>{source.file_id&&<a className="btn" href={'/api/workhub/files/'+source.file_id+'/download'}>Download source</a>}</section></div>}</div>;
}
