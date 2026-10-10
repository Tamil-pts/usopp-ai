import {useEffect,useState,type FormEvent} from 'react';
import {accountRequest,useAccount,type AccountUser} from './AuthProvider';
import {PasswordInput} from './PasswordInput';
import './user-management.css';

type ManagedUser=AccountUser&{active:boolean;createdAt:number};
const empty={username:'',password:'',designation:'',company:'',active:true};
export function UserManagement() {
 const {user}=useAccount();const [users,setUsers]=useState<ManagedUser[]>([]),[editing,setEditing]=useState<number|null>(null);
 const [form,setForm]=useState(empty),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const [capacity,setCapacity]=useState<{maxActiveUsers:number;activeUsers:number;availableSlots:number}|null>(null);
 const reload=()=>accountRequest('users').then(data=>{setUsers(data.users);setCapacity(data.capacity||null)});
 const adminCount=users.filter(account=>account.active&&account.role==='admin').length;
 useEffect(()=>{if(user.role==='admin')void reload().catch(e=>setError(e.message));},[user.role]);
 if(user.role!=='admin')return null;
 const edit=(account:ManagedUser)=>{setEditing(account.id);setForm({...account,password:''});setMessage('');setError('');};
 const clear=()=>{setEditing(null);setForm(empty);};
 const save=async(event:FormEvent)=>{
  event.preventDefault();setBusy(true);setError('');setMessage('');
  try{await accountRequest(editing===null?'users':`users/${editing}`,form);await reload();setMessage(editing===null?'User account created.':'User account updated. A reset password or disabled account signs out its existing sessions.');clear();}
  catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 return <section className="card userManagement" aria-labelledby="user-management-title"><div className="widgetHead"><h2 id="user-management-title">User management</h2><button className="btn" disabled={busy} onClick={()=>{clear();setMessage('')}}>Create user</button></div>
  <p>Create accounts, update company and designation, reset passwords, or enable and disable user access.</p>
  {capacity&&<p role="status"><b>{Math.max(0,capacity.activeUsers-adminCount)} / {Math.max(0,capacity.maxActiveUsers-adminCount)} enabled regular users</b>, plus {adminCount} Admin account. {capacity.availableSlots} available user slots. Disabled accounts retain their test history. The server limit can be increased later.</p>}
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  <div className="userManagementGrid"><div className="tableWrap"><table><thead><tr><th>Username</th><th>Designation</th><th>Company</th><th>Access</th><th>Created</th><th/></tr></thead><tbody>{users.map(account=><tr key={account.id}><td>{account.username}</td><td>{account.designation}</td><td>{account.company}</td><td>{account.role==='admin'?'Admin':account.active?'Enabled':'Disabled'}</td><td>{new Date(account.createdAt*1000).toLocaleString()}</td><td>{account.role!=='admin'&&<button className="btn" disabled={busy} onClick={()=>edit(account)}>Manage {account.username}</button>}</td></tr>)}</tbody></table></div>
   <form onSubmit={save}><h3>{editing===null?'Create user account':'Edit user account'}</h3><label>Username<input className="textInput" required minLength={3} maxLength={40} value={form.username} disabled={busy} onChange={e=>setForm({...form,username:e.target.value})}/></label>
    <PasswordInput label={editing===null?'Initial password':'Reset password (leave blank to keep)'} value={form.password} required={editing===null} minLength={8} maxLength={128} disabled={busy} autoComplete="new-password" onChange={e=>setForm({...form,password:e.target.value})}/>
    <label>Designation<input className="textInput" required value={form.designation} maxLength={120} disabled={busy} onChange={e=>setForm({...form,designation:e.target.value})}/></label><label>Company name<input className="textInput" required maxLength={120} value={form.company} disabled={busy} onChange={e=>setForm({...form,company:e.target.value})}/></label>
    {editing!==null&&<label><input type="checkbox" checked={form.active} disabled={busy} onChange={e=>setForm({...form,active:e.target.checked})}/>Account enabled</label>}
    <div className="actions"><button className="btn primary" disabled={busy||(editing===null&&capacity?.availableSlots===0)}>{busy?'Saving...':editing===null?'Create account':'Save account'}</button>{editing!==null&&<button type="button" className="btn" disabled={busy} onClick={clear}>Cancel edit</button>}</div>
   </form></div></section>;
}
