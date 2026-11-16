import {useEffect,useRef,useState,type KeyboardEvent,type ReactNode} from 'react';
import {ChevronDown,LogOut,Moon,ShieldAlert,Sun,UserRound} from 'lucide-react';
import {UserAvatar} from '../features/account/UserAvatar';
import {ThemePicker} from './ThemePicker';
import type {AppTheme} from './themes';
import {NotificationBell} from '../features/workhub/NotificationBell';
import {TeamInbox} from '../features/team-chat/TeamInbox';
import {BuildVersionBadge,type AppHealth} from './BuildStatus';
import type {AccountUser} from '../features/account/AuthProvider';
import petrusLogo from '../petrus_logo.png';
import './workspace-topbar.css';

type Props={user:AccountUser;page:string;theme:AppTheme;health:AppHealth|null;assistant?:ReactNode;onTheme:(theme:AppTheme)=>void;onProfile:()=>void;onLogout:()=>Promise<void>;onNotification:(project:string,item:string)=>void};
export function WorkspaceTopBar({user,page,theme,health,assistant,onTheme,onProfile,onLogout,onNotification}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const account=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null);
 useEffect(()=>{if(!open)return;const outside=(e:PointerEvent)=>{if(!account.current?.contains(e.target as Node))setOpen(false);};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);},[open]);
 const close=()=>{setOpen(false);trigger.current?.focus();};
 const keys=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();close();return;}if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;e.preventDefault();const items=Array.from(account.current?.querySelectorAll<HTMLButtonElement>('[role=menuitem]:not(:disabled)')||[]),i=items.indexOf(document.activeElement as HTMLButtonElement);items[e.key==='Home'?0:e.key==='End'?items.length-1:(i+(e.key==='ArrowUp'?-1:1)+items.length)%items.length]?.focus();};
 return <header className={'top workspaceTopBar'+(assistant?' hasAssistant':'')}>
  <div className="workspaceCrumb" aria-label={'Current workspace: '+page}><b>uSOPp.ai</b><span aria-hidden="true">/</span><span className="workspacePageName">{page}</span></div>
  {assistant&&<div className="workspaceTopAssistant">{assistant}</div>}
  <div className="workspaceTopActions">
   <BuildVersionBadge health={health} compact/>
   <ThemePicker theme={theme} onChange={onTheme}/>
   <NotificationBell onOpen={onNotification}/>
   <TeamInbox/>
   <div className="workspaceAccount" ref={account} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setOpen(false);}}>
    <button ref={trigger} className="workspaceAccountTrigger" aria-label={'Account menu for '+user.username} aria-haspopup="menu" aria-expanded={open} aria-controls="workspace-account-menu" onClick={()=>setOpen(v=>!v)} onKeyDown={e=>{if(e.key==='ArrowDown'){e.preventDefault();setOpen(true);setTimeout(()=>account.current?.querySelector<HTMLButtonElement>('[role=menuitem]')?.focus(),0);}}}><UserAvatar user={user}/><span>{user.username}<small>{user.role==='admin'?'Administrator':'Team member'}</small></span><ChevronDown size={14}/></button>
    {open&&<div id="workspace-account-menu" className="workspaceAccountMenu" role="menu" aria-label="Your account" onKeyDown={keys}><div className="workspaceAccountIdentity"><strong>{user.username}</strong><small>{user.designation} · {user.company}</small></div><button role="menuitem" onClick={()=>{setOpen(false);onProfile();}}><UserRound size={16}/>My profile & password</button>{user.passwordChangeRequired&&<button role="menuitem" className="workspacePasswordAction" onClick={()=>{setOpen(false);onProfile();}}><ShieldAlert size={16}/>Change initial password</button>}<button role="menuitem" disabled={busy} onClick={()=>{setBusy(true);setError('');void onLogout().catch(e=>setError((e as Error).message)).finally(()=>setBusy(false));}}><LogOut size={16}/>{busy?'Signing out…':'Sign out'}</button>{error&&<p role="alert">{error}</p>}<div className="workspaceBuildDetails"><BuildVersionBadge health={health}/></div></div>}
   </div>
   <img className="workspacePartnerLogo" src={petrusLogo} alt="Petrus"/>
  </div>
 </header>;
}
