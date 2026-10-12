import {useState,type FormEvent} from 'react';
import {accountRequest,useAccount} from './AuthProvider';
import {PasswordInput} from './PasswordInput';
export function AccountSettings(){
  const {user}=useAccount();
  const [current,setCurrent]=useState(''),[replacement,setReplacement]=useState(''),[confirm,setConfirm]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
  const submit=async(event:FormEvent)=>{
    event.preventDefault();setError('');setMessage('');
    if(replacement!==confirm){setError('New passwords do not match.');return;}
    setBusy(true);
    try{const result=await accountRequest('password',{currentPassword:current,newPassword:replacement});setMessage(result.message);setCurrent('');setReplacement('');setConfirm('')}
    catch(reason:any){setError(reason.message)}finally{setBusy(false)}
  };
  if(user.isDemo)return <div className="card setting"><h3>My account</h3><p><b>{user.username}</b> · Demo user</p><p>This demo session signs out automatically after 30 minutes. Your uploads and results belong to this demo session. Create a personal account for a continuing workspace.</p></div>;
  return <div className="card setting"><h3>My account</h3><p><b>{user.username}</b> · {user.role==='admin'?'Administrator':'User'}<br/>{user.designation} · {user.company}</p>
    <form onSubmit={submit} className="accountForm">
      <PasswordInput label="Current password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/>
      <PasswordInput label="New password" autoComplete="new-password" required minLength={8} maxLength={128} value={replacement} onChange={e=>setReplacement(e.target.value)}/>
      <PasswordInput label="Confirm new password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/>
      {error&&<p role="alert" className="accountError">{error}</p>}{message&&<p role="status">{message}</p>}
      <button className="btn primary" disabled={busy}>{busy?'Changing…':'Change password'}</button>
    </form></div>;
}
