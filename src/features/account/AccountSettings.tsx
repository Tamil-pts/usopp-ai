import {useRef,useState,type FormEvent,type ChangeEvent} from 'react';
import {accountRequest,useAccount} from './AuthProvider';
import {PasswordInput} from './PasswordInput';
import {UserAvatar} from './UserAvatar';
import {TeamDetails} from '../workhub/people/PeopleManagement';
export function AccountSettings(){
  const {user,refreshUser}=useAccount();
  const [email,setEmail]=useState(user.email||'');
  const saveEmail=async(event:FormEvent)=>{event.preventDefault();setBusy(true);setError('');setMessage('');try{await accountRequest('profile-email',{email});await refreshUser();setMessage('Email ID saved.');}catch(reason){setError((reason as Error).message);}finally{setBusy(false);}};
  const photoInput=useRef<HTMLInputElement>(null);
  const [current,setCurrent]=useState(''),[replacement,setReplacement]=useState(''),[confirm,setConfirm]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
  const photo=async(event:ChangeEvent<HTMLInputElement>)=>{
    const input=event.currentTarget,file=input.files?.[0];if(!file)return;
    setBusy(true);setError('');setMessage('');
    try{
      if(file.size>5*1024*1024)throw new Error('Choose a photo up to 5 MB.');
      const body=new FormData();body.append('file',file);
      const response=await fetch('/api/auth/profile-image',{method:'POST',body,credentials:'same-origin'}),result=await response.json();
      if(!response.ok)throw new Error(result.detail||'Photo upload failed.');
      await refreshUser();setMessage('Profile photo updated.');
    }catch(reason){setError(reason instanceof Error?reason.message:'Photo upload failed.')}finally{setBusy(false);input.value=''}
  };
  const removePhoto=async()=>{setBusy(true);setError('');setMessage('');try{await accountRequest('profile-image',undefined,'DELETE');await refreshUser();setMessage('Profile photo removed.')}catch(reason){setError(reason instanceof Error?reason.message:'Could not remove photo.')}finally{setBusy(false)}};
  const submit=async(event:FormEvent)=>{
    event.preventDefault();setError('');setMessage('');
    if(replacement!==confirm){setError('New passwords do not match.');return;}
    setBusy(true);
    try{const result=await accountRequest('password',{currentPassword:current,newPassword:replacement});setMessage(result.message);setCurrent('');setReplacement('');setConfirm('')}
    catch(reason:any){setError(reason.message)}finally{setBusy(false)}
  };
  if(user.isDemo)return <div className="card setting"><h3>My account</h3><p><b>{user.username}</b> · Demo user</p><p>This demo session signs out automatically after 30 minutes. Your uploads and results belong to this demo session. Create a personal account for a continuing workspace.</p></div>;
  return <div className="card setting"><h3>My profile</h3>
    <div className="profilePhoto"><UserAvatar user={user} size={88}/><div><b>{user.username}</b><p>{user.role==='admin'?'Admin':'User'} · {user.designation}<br/>{user.company}</p></div></div>
    <TeamDetails userId={user.id}/><div className="actions"><button className="btn" type="button" disabled={busy} onClick={()=>photoInput.current?.click()}>Upload profile photo</button><input ref={photoInput} type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={busy} onChange={event=>void photo(event)}/>{user.avatarUrl&&<button className="btn" type="button" disabled={busy} onClick={()=>void removePhoto()}>Remove photo</button>}</div>
    <p className="muted">PNG, JPEG or WebP, up to 5 MB. Your photo appears beside your account name.</p>
    {error&&<p role="alert" className="accountError">{error}</p>}{message&&<p role="status">{message}</p>}
    <form onSubmit={saveEmail} className="accountForm"><label>Email ID (optional)<input className="textInput" type="email" maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></label><button className="btn" disabled={busy}>Save email ID</button><small>Contact information. Sending notifications still uses your existing connection preferences.</small></form><form onSubmit={submit} className="accountForm"><h4>Change password</h4>
      <PasswordInput label="Current password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/>
      <PasswordInput label="New password" autoComplete="new-password" required minLength={8} maxLength={128} value={replacement} onChange={e=>setReplacement(e.target.value)}/>
      <PasswordInput label="Confirm new password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/>
      <button className="btn primary" disabled={busy}>{busy?'Changing…':'Change password'}</button>
    </form></div>;
}
