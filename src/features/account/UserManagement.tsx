import {useEffect,useState,type FormEvent} from 'react';
import {accountRequest,useAccount,type AccountUser} from './AuthProvider';
import {UserAvatar} from './UserAvatar';
import {PasswordInput} from './PasswordInput';
import './user-management.css';
import PeopleManagement,{TeamDetails} from '../workhub/people/PeopleManagement';

type ManagedUser=AccountUser&{active:boolean;approved?:boolean;createdAt:number};
const empty={username:'',password:'',designation:'',company:'',email:'',active:true,role:'user' as 'admin'|'user'};
export function UserManagement() {
 const {user}=useAccount();const [users,setUsers]=useState<ManagedUser[]>([]),[editing,setEditing]=useState<number|null>(null);
 const [form,setForm]=useState(empty),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const [accountStats,setAccountStats]=useState<{activeUsers:number}|null>(null);
 const reload=()=>accountRequest('users').then(data=>{setUsers(data.users);setAccountStats(data.capacity||null)});
 const adminCount=users.filter(account=>account.active&&account.role==='admin').length;
 const pendingUsers=users.filter(account=>account.role==='user'&&!account.approved);
 const enableRequest=async(account:ManagedUser)=>{
  setBusy(true);setError('');setMessage('');
  try{await accountRequest(`users/${account.id}`,{...account,active:true});await reload();setMessage(`Account for ${account.username} is enabled. They can now sign in.`)}
  catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 const deleteAccount=async(account:ManagedUser)=>{
  if(!window.confirm(`Permanently delete ${account.username}? Their sign-in, saved user settings, test history and owned workspaces will be deleted. This cannot be undone.`))return;
  setBusy(true);setError('');setMessage('');
  try{await accountRequest(`users/${account.id}`,undefined,'DELETE');if(editing===account.id)clear();await reload();setMessage(`Account ${account.username} and its user data were deleted.`)}
  catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 useEffect(()=>{if(user.role==='admin')void reload().catch(e=>setError(e.message));},[user.role]);
 if(user.role!=='admin')return null;
 const primary=editing!==null&&users.find(account=>account.id===editing)?.username.toLowerCase()==='admin';
 const edit=(account:ManagedUser)=>{setEditing(account.id);setForm({...account,email:account.email||'',password:''});setMessage('');setError('');};
 const clear=()=>{setEditing(null);setForm(empty);};
 const save=async(event:FormEvent)=>{
  event.preventDefault();setBusy(true);setError('');setMessage('');
  try{await accountRequest(editing===null?'users':`users/${editing}`,form);await reload();setMessage(editing===null?'User account created.':'User account updated. Role changes, password resets and disabled access sign out the affected account.');clear();}
  catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 return <section className="card userManagement" aria-labelledby="user-management-title"><div className="widgetHead"><h2 id="user-management-title">Users &amp; Roles</h2><div className="actions"><button className="btn" disabled={busy} onClick={()=>void reload().catch(e=>setError(e.message))}>Refresh requests</button><button className="btn" disabled={busy} onClick={()=>{clear();setMessage('')}}>Create user</button></div></div>
  <p>Review account requests and enable access. Assign Admin or User roles, update user details, reset passwords, and enable or disable access. Every enabled account can open all workspace features. Only Admin can manage users.</p>
  {pendingUsers.length>0&&<div className="accountRequests" role="status"><b>{pendingUsers.length} account request{pendingUsers.length===1?'':'s'} waiting</b><p>Review each request and enable access when approved.</p></div>}
  {accountStats&&<p role="status"><b>{accountStats.activeUsers} enabled accounts</b> ({adminCount} Admin). Accounts are not limited by a fixed user cap. Disabled accounts retain their test history.</p>}
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  <details className="people-catalog"><summary>Manage departments, professional roles and teams</summary><PeopleManagement/></details><div className="userManagementGrid"><div className="tableWrap"><table><thead><tr><th>Username</th><th>Email ID</th><th>Designation</th><th>Team Details</th><th>Company</th><th>Role</th><th>Access</th><th>Created</th><th>Actions</th></tr></thead><tbody>{[...users].sort((a,b)=>Number(!a.approved)-Number(!b.approved)||a.username.localeCompare(b.username)).map(account=><tr key={account.id}><td><div className="managedUserName"><UserAvatar user={account} size={30}/>{account.username}</div></td><td>{account.email||'?'}</td><td>{account.designation}</td><td><TeamDetails userId={account.id} compact/></td><td>{account.company}</td><td>{account.role==='admin'?'Admin':'User'}</td><td>{!account.approved?'Request pending':account.active?'Enabled':'Disabled'}</td><td>{new Date(account.createdAt*1000).toLocaleString()}</td><td>{account.id!==user.id?<div className="actions">{account.role==='user'&&!account.approved&&<button className="btn primary" disabled={busy} onClick={()=>void enableRequest(account)}>Enable {account.username}</button>}<button className="btn" disabled={busy} onClick={()=>edit(account)}>Manage</button><button className="btn danger" disabled={busy||account.role==='admin'} onClick={()=>void deleteAccount(account)}>Delete</button></div>:<span>Your account</span>}</td></tr>)}</tbody></table></div>
   <form onSubmit={save}><h3>{editing===null?'Create user account':'Edit user account'}</h3><label>Username<input className="textInput" required minLength={3} maxLength={40} value={form.username} disabled={busy||primary} onChange={e=>setForm({...form,username:e.target.value})}/></label>
    <label>Role<select className="textInput" value={form.role} disabled={busy||primary} onChange={event=>setForm({...form,role:event.target.value as 'admin'|'user'})}><option value="user">User</option><option value="admin">Admin</option></select></label>
    <p className="muted">User: all workspace features and personal results. Admin: workspace features, user management and shared settings.</p>
    <PasswordInput label={editing===null?'Initial password':'Reset password (leave blank to keep)'} value={form.password} required={editing===null} minLength={8} maxLength={128} disabled={busy} autoComplete="new-password" onChange={e=>setForm({...form,password:e.target.value})}/>
    <label>Email ID (optional)<input className="textInput" type="email" maxLength={254} value={form.email} disabled={busy} onChange={e=>setForm({...form,email:e.target.value})}/></label><label>Designation<input className="textInput" required value={form.designation} maxLength={120} disabled={busy} onChange={e=>setForm({...form,designation:e.target.value})}/></label><label>Company name<input className="textInput" required maxLength={120} value={form.company} disabled={busy} onChange={e=>setForm({...form,company:e.target.value})}/></label>
    {editing!==null&&<TeamDetails userId={editing}/>}
    {editing!==null&&<label><input type="checkbox" checked={form.active} disabled={busy||primary} onChange={e=>setForm({...form,active:e.target.checked})}/>Account enabled</label>}
    <div className="actions"><button className="btn primary" disabled={busy}>{busy?'Saving...':editing===null?'Create account':'Save account'}</button>{editing!==null&&<button type="button" className="btn" disabled={busy} onClick={clear}>Cancel edit</button>}</div>
   </form></div></section>;
}
