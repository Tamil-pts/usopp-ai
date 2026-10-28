import {useState} from 'react';
import {ProjectGantt} from './ProjectGantt';
import type {HubRow} from './projectApi';
export function MyWorkTimeline({items,users,userId,onOpen,onEdit,canEdit,onSchedule}:{items:HubRow[];users:HubRow[];userId:number;onOpen:(r:HubRow)=>void;onEdit:(r:HubRow)=>void;canEdit:(r:HubRow)=>boolean;onSchedule:(r:HubRow,v:HubRow)=>Promise<void>}){
 const [filter,setFilter]=useState('all');
 const mine=items.filter(r=>[r.owner_id,r.current_user_id].includes(userId)||JSON.parse(r.supporting_ids||'[]').includes(userId));
 const state=(r:HubRow)=>r.stage==='released'||r.type==='task'&&['development_completed','quality','release_approval','ready_release'].includes(r.stage)?'completed':r.stage==='todo'?'assigned':'progress';
 return <section className="wh-my-work"><div className="wh-work-summary">{[['all','All my work'],['assigned','Assigned'],['progress','In progress'],['completed','Completed']].map(([id,label])=><button key={id} className={'card '+(filter===id?'selected':'')} onClick={()=>setFilter(id)}><span>{label}</span><strong>{mine.filter(r=>id==='all'||state(r)===id).length}</strong></button>)}</div><ProjectGantt title="My work timeline" description="Assigned, in progress and completed work, using the recorded project dates." items={mine.filter(r=>filter==='all'||state(r)===filter)} users={users} onOpen={onOpen} onEdit={onEdit} canEdit={canEdit} onSchedule={onSchedule}/></section>;
}
