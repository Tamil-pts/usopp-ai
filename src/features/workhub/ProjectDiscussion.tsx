import {useState,useRef,type FormEvent} from 'react';
import {hub,HUB,bytes,when,uploadFiles,type HubRow} from './projectApi';
import {Paperclip,Clock,FolderOpen,Send,MessageSquare,X,FileText,Check} from 'lucide-react';
import './project-discussion.css';

type Props={
 project:HubRow;
 selected:HubRow;
 users:HubRow[];
 currentUserId:number;
 updates:HubRow[];
 events:HubRow[];
 onRefresh:()=>void;
};

const initials=(name:string)=>{
 return name.split(/\s+/).filter(Boolean).slice(0,2).map(p=>p[0]).join('').toUpperCase()||'?';
};

export function ProjectDiscussion({project,selected,users,currentUserId,updates,events,onRefresh}:Props){
 const [comment,setComment]=useState('');
 const [updateType,setUpdateType]=useState<'daily'|'project'>('project');
 const [subtask,setSubtask]=useState('');
 const [hours,setHours]=useState('');
 const [minutes,setMinutes]=useState('');
 const [showTime,setShowTime]=useState(false);
 const [markdownMode,setMarkdownMode]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [attachedFiles,setAttachedFiles]=useState<HubRow[]>([]);
 const fileInputRef=useRef<HTMLInputElement>(null);

 const currentUser=users.find(u=>u.id===currentUserId);

 async function handleAttach(e:React.ChangeEvent<HTMLInputElement>){
  const files=Array.from(e.target.files||[]);
  if(!files.length)return;
  e.target.value='';
  setBusy(true);
  try{
   const abort=new AbortController();
   const uploaded=await uploadFiles(project.id,files,()=>{},()=>{},abort.signal);
   setAttachedFiles(prev=>[...prev,...uploaded]);
  }catch(err){
   setError((err as Error).message);
  }finally{
   setBusy(false);
  }
 }

 async function submitComment(e:FormEvent){
  e.preventDefault();
  if(!comment.trim()&&!attachedFiles.length)return;
  setBusy(true);
  setError('');
  try{
   const h=Number(hours||0),m=Number(minutes||0);
   const totalMinutes=h*60+m;
   let bodyText=comment.trim();
   if(subtask.trim()){
    bodyText='**['+(updateType==='daily'?'Daily Update':'Project Update')+']** Sub-task: '+subtask.trim()+'\n\n'+bodyText;
   }else if(updateType==='daily'){
    bodyText='**[Daily Update]**\n\n'+bodyText;
   }

   await hub('/items/'+(selected.id||project.id)+'/updates',{
    body:bodyText,
    minutes:totalMinutes,
    work_date:new Date().toISOString().slice(0,10),
    file_ids:attachedFiles.map(f=>f.id),
    subtask_title:subtask.trim(),
    update_type:updateType,
    work_status:'in_progress',
    request_kind:'progress'
   });
   setComment('');
   setSubtask('');
   setHours('');
   setMinutes('');
   setShowTime(false);
   setAttachedFiles([]);
   onRefresh();
  }catch(err){
   setError((err as Error).message);
  }finally{
   setBusy(false);
  }
 }

 // Consolidate comments from updates and events
 const commentsList:any[]=[];
 for(const up of updates){
  commentsList.push({
   id:up.id,
   author_id:up.author_id,
   body:up.body,
   created_at:up.created_at||up.work_date,
   minutes:up.minutes,
   time_status:up.time_status,
   file_ids:up.file_ids||[],
   kind:up.body?.includes('[Daily Update]')?'daily':'project'
  });
 }
 for(const ev of events){
  if(ev.detail?.comment||ev.event==='comment'||ev.event?.includes('update')){
   const isAlready=commentsList.some(c=>c.id===ev.detail?.update_id);
   if(!isAlready&&ev.detail?.comment){
    commentsList.push({
     id:'ev-'+ev.id,
     author_id:ev.actor_id,
     author_name:ev.detail?.actor_name,
     body:ev.detail.comment||ev.detail.body,
     created_at:ev.created_at,
     minutes:ev.detail.minutes||0,
     time_status:'',
     file_ids:ev.detail.files||[],
     kind:ev.detail.update_type||'project'
    });
   }
  }
 }
 commentsList.sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime());

 function renderCommentBody(text:string){
  // Highlight @mentions in blue
  const parts=text.split(/(@[a-zA-Z0-9_.-]+)/g);
  return parts.map((part,i)=>{
   if(part.startsWith('@')){
    return <span key={i} className="discussionMention">{part}</span>;
   }
   return part;
  });
 }

 return (
  <section className="wh-discussion-container" aria-label="Project discussion">
   <div className="wh-discussion-header">
    <h3>Discussion</h3>
   </div>

   {/* Add Comment Box */}
   <div className="wh-comment-card">
    <div className="wh-comment-avatar-col">
     <div className="wh-user-avatar currentUserAvatar">
      {initials(currentUser?.username||'Admin')}
     </div>
    </div>
    <form className="wh-comment-form-col" onSubmit={submitComment}>
     <div className="wh-comment-input-wrap">
      <textarea
       className="wh-comment-textarea"
       rows={3}
       maxLength={8000}
       placeholder="Add a comment. Use # to link a work item, @ to mention a person, or ! to link a pull request."
       value={comment}
       onChange={e=>setComment(e.target.value)}
       disabled={busy}
      />
      <div className="wh-comment-toolbar">
       <button
        type="button"
        className="wh-text-link"
        onClick={()=>setMarkdownMode(v=>!v)}
       >
        {markdownMode?'preview comment':'switch to Markdown editor'}
       </button>
       <div className="wh-toolbar-actions">
        <button
         type="button"
         className={'wh-icon-btn '+(updateType==='daily'?'active':'')}
         onClick={()=>setUpdateType(t=>t==='daily'?'project':'daily')}
         title="Toggle Daily Update vs Project Update"
        >
         <Clock size={13}/> {updateType==='daily'?'Daily Update':'Project Update'}
        </button>
        <button
         type="button"
         className={'wh-icon-btn '+(showTime?'active':'')}
         onClick={()=>setShowTime(v=>!v)}
         title="Log time against this update"
        >
         <Clock size={13}/> Log time
        </button>
        <button
         type="button"
         className="wh-icon-btn"
         onClick={()=>fileInputRef.current?.click()}
         disabled={busy}
         title="Attach files"
        >
         <Paperclip size={13}/> Attach
        </button>
        <input type="file" multiple hidden ref={fileInputRef} onChange={handleAttach}/>
        <button
         type="submit"
         className="btn primary wh-submit-comment-btn"
         disabled={busy||(!comment.trim()&&!attachedFiles.length)}
        >
         <Send size={13}/> {busy?'Posting...':'Comment'}
        </button>
       </div>
      </div>
     </div>

     {/* Optional Sub-task & Time Log inputs */}
     {(showTime||updateType==='daily')&&(
      <div className="wh-comment-extra-inputs">
       <div className="wh-subtask-row">
        <label>
         <span>Sub-task (Optional):</span>
         <input
          type="text"
          className="textInput"
          placeholder="e.g. Sub-task #1: Verify alarm threshold bits"
          value={subtask}
          onChange={e=>setSubtask(e.target.value)}
          disabled={busy}
         />
        </label>
       </div>
       {showTime&&(
        <div className="wh-time-log-row">
         <label>
          <span>Hours:</span>
          <input
           type="number"
           min={0}
           max={24}
           className="textInput"
           placeholder="0"
           value={hours}
           onChange={e=>setHours(e.target.value)}
           disabled={busy}
          />
         </label>
         <label>
          <span>Minutes:</span>
          <input
           type="number"
           min={0}
           max={59}
           className="textInput"
           placeholder="0"
           value={minutes}
           onChange={e=>setMinutes(e.target.value)}
           disabled={busy}
          />
         </label>
        </div>
       )}
      </div>
     )}

     {/* Attached files chips */}
     {attachedFiles.length>0&&(
      <div className="wh-comment-attached-files">
       {attachedFiles.map(f=>(
        <span key={f.id} className="wh-attach-chip">
         <Paperclip size={12}/> {f.name} <small>({bytes(f.size)})</small>
         <button type="button" onClick={()=>setAttachedFiles(prev=>prev.filter(x=>x.id!==f.id))}><X size={12}/></button>
        </span>
       ))}
      </div>
     )}
     {error&&<p role="alert" className="wh-error" style={{marginTop:6}}>{error}</p>}
    </form>
   </div>

   {/* Comments list */}
   <div className="wh-comments-list">
    {commentsList.map(item=>{
     const author=users.find(u=>u.id===item.author_id);
     const authorName=item.author_name||author?.username||'Engineer';
     return (
      <article key={item.id} className="wh-discussion-entry">
       <div className="wh-comment-avatar-col">
        <div className="wh-user-avatar">
         {initials(authorName)}
        </div>
       </div>
       <div className="wh-discussion-content">
        <header className="wh-discussion-meta">
         <strong>{authorName}</strong>
         <span>commented {when(item.created_at)}</span>
         {item.kind==='daily'&&<span className="wh-kind-pill daily">Daily Update</span>}
         {item.minutes>0&&<span className="wh-kind-pill time">{(item.minutes/60).toFixed(2)} h</span>}
        </header>
        <div className="wh-discussion-body">
         <p className="wh-preserve">{renderCommentBody(item.body)}</p>
        </div>
        {item.file_ids?.length>0&&(
         <div className="wh-discussion-attachments">
          {item.file_ids.map((id:string)=>(
           <a key={id} href={HUB+'/files/'+id+'/download'} target="_blank" rel="noopener noreferrer">
            <Paperclip size={12}/> Attachment
           </a>
          ))}
         </div>
        )}
       </div>
      </article>
     );
    })}
    {!commentsList.length&&(
     <p className="wh-empty" style={{marginTop:16}}>No discussion comments yet. Add a comment or work update above.</p>
    )}
   </div>
  </section>
 );
}
