import {userStorage} from '../../shared/userStorage';
import {activateUserStorage,hydrateUserStorage,flushUserStorage} from '../../shared/userStorage';
import {StorageNotice} from '../../shared/StorageNotice';
import {createContext,useContext,useEffect,useRef,useState,type ReactNode,type FormEvent,type MouseEvent} from 'react';
import {ArrowRight,ArrowUpRight,Check,RefreshCw} from 'lucide-react';
import usoppLogo from '../../usopp_logo.png';
import petrusLogo from '../../petrus_logo.png';
import engineeringHero from './assets/engineering-factory-hero-v1.webp';
import {PasswordInput} from './PasswordInput';
import type {WorkspaceModule} from '../../shared/workspaceModules';
import '../../styles.css';
import './account.css';
import {LandingHighlights} from './LandingHighlights';
export type AccountUser={id:number;username:string;designation:string;company:string;role:'admin'|'user';email?:string;avatarUrl?:string|null;approved?:boolean;isDemo?:boolean;passwordChangeRequired?:boolean;sessionExpiresAt?:number;workspaceModules?:WorkspaceModule[]};
const Context=createContext<{user:AccountUser;logout:()=>Promise<void>;refreshUser:()=>Promise<void>}|null>(null);
export function useAccount(){const value=useContext(Context);if(!value)throw new Error('Account is not signed in');return value;}
class AccountServiceError extends Error {}
export async function accountRequest(path:string,data?:unknown,method?:'POST'|'DELETE'){
  let response:Response;
  try{response=await fetch('/api/auth/'+path,{credentials:'same-origin',cache:'no-store',...(data||method?{method:method||'POST',...(data?{headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{})}:{})})}
  catch{throw new AccountServiceError('Cannot reach the uSOPp.ai server. Start the application, then check the connection again.')}
  if(response.status===404||response.status===405)throw new AccountServiceError('The running server needs an update. Stop and restart uSOPp.ai, then check the connection again.');
  let result:any;
  try{result=await response.json()}catch{throw new AccountServiceError('The accounts service is unavailable. Start the updated uSOPp.ai server, then check the connection again.')}
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Account request failed.');
  if(['session','login'].includes(path)&&(!result||!('user' in result)))throw new AccountServiceError('The running server does not support accounts. Restart the updated uSOPp.ai application.');
  return result;
}
const originalFetch=window.fetch.bind(window);
window.fetch=async(...args:Parameters<typeof fetch>)=>{
  const response=await originalFetch(...args);
  const input=args[0];
  const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,window.location.href);
  if(url.origin===window.location.origin&&url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/api/auth/')&&response.status===401)window.dispatchEvent(new Event('usopp-session-expired'));
  return response;
};
export function AuthProvider({children}:{children:ReactNode}){
  const [user,setUserState]=useState<AccountUser|null>(null),[loading,setLoading]=useState(true),[register,setRegister]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const accountGeneration=useRef(0);
  const setUser=async(value:AccountUser|null)=>{const generation=++accountGeneration.current;if(value){activateUserStorage(value);setUserState(value);void hydrateUserStorage(value).catch(()=>{});return;}activateUserStorage(null);if(generation===accountGeneration.current)setUserState(null)};
  const [serviceReady,setServiceReady]=useState(false);
  const [form,setForm]=useState({username:'',password:'',confirm:'',designation:'',company:'',email:''});
  const usernameInput=useRef<HTMLInputElement>(null);
  const expireSession=(notice:string)=>{void setUser(null);setRegister(false);setError(notice);setForm(value=>({...value,password:'',confirm:''}))};
  useEffect(()=>{
    document.documentElement.dataset.theme=userStorage.getItem('usopp_theme')==='dark'?'dark':'light';
    let active=true;
    accountRequest('session').then(async result=>{if(active){await setUser(result.user);setServiceReady(true)}}).catch(reason=>{if(active){setError(reason.message);setServiceReady(false)}}).finally(()=>{if(active)setLoading(false)});
    const expired=()=>expireSession('Your session expired. Sign in again.');
    window.addEventListener('usopp-session-expired',expired);
    return()=>{active=false;window.removeEventListener('usopp-session-expired',expired)};
  },[]);
  useEffect(()=>{
    if(!user?.isDemo||!user.sessionExpiresAt)return;
    const deadline=user.sessionExpiresAt*1000;
    const check=()=>{if(Date.now()>=deadline)expireSession('Your 30-minute demo session ended. Choose Explore demo to start a new session.')};
    const timer=setTimeout(check,Math.max(0,deadline-Date.now()));
    window.addEventListener('focus',check);
    document.addEventListener('visibilitychange',check);
    return()=>{clearTimeout(timer);window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check)};
  },[user?.isDemo,user?.sessionExpiresAt]);
  const submit=async(event:FormEvent)=>{
    event.preventDefault();setError('');
    if(!serviceReady)return;
    if(register&&form.password!==form.confirm){setError('Passwords do not match.');return;}
    setBusy(true);
    try{
      const result=await accountRequest(register?'register':'login',form);
      setForm({username:'',password:'',confirm:'',designation:'',company:'',email:''});
      if(register){setNotice(result.message||'Your account request was sent to Admin for approval.');setRegister(false);return;}
      setNotice('');await setUser(result.user);
    }
    catch(reason:any){setError(reason.message);if(reason instanceof AccountServiceError)setServiceReady(false)}finally{setBusy(false)}
  };
  const retryConnection=async()=>{
    setBusy(true);setError('');
    try{const result=await accountRequest('session');await setUser(result.user);setServiceReady(true)}
    catch(reason:any){setError(reason.message);setServiceReady(false)}finally{setBusy(false)}
  };
  const refreshUser=async()=>{const result=await accountRequest('session');if(!result.user){expireSession('Your session expired. Sign in again.');return}setUserState(current=>current?.id===result.user.id?result.user:current)};
  useEffect(()=>{if(!user||user.isDemo)return;let active=true;const refresh=()=>{if(active&&document.visibilityState==='visible')void refreshUser().catch(()=>{})};const id=setInterval(refresh,15000);window.addEventListener('focus',refresh);return()=>{active=false;clearInterval(id);window.removeEventListener('focus',refresh)}},[user?.id,user?.isDemo]);
  const logout=async()=>{await flushUserStorage();await accountRequest('logout',{});await setUser(null);setRegister(false)};
  const enterWorkspace=(event:MouseEvent<HTMLAnchorElement>)=>{
    event.preventDefault();document.getElementById('accountCard')?.scrollIntoView({block:'center'});
    if(register){setRegister(false);setForm(value=>({...value,password:'',confirm:''}));if(serviceReady)setError('')}
    usernameInput.current?.focus({preventScroll:true});
  };
  const exploreDemo=()=>{
    setRegister(false);setNotice('');if(serviceReady)setError('');
    setForm({username:'demo',password:'demo',confirm:'',designation:'',company:'',email:''});
    usernameInput.current?.focus({preventScroll:true});
  };
  if(loading)return <div className="accountScreen"><div className="accountOpening" role="status"><img src={usoppLogo} alt="uSOPp.ai" width={68}/><p>Opening your engineering workspace…</p></div></div>;
  if(user)return <Context.Provider key={user.id} value={{user,logout,refreshUser}}>{children}<StorageNotice/></Context.Provider>;
  return <div className="accountScreen">
    <header className="accountLandingHeader"><a className="accountBrand" href="#accountLanding" aria-label="uSOPp.ai home"><img src={usoppLogo} alt=""/><div><b>uSOPp.ai</b><span>ENGINEERING WORKSPACE</span></div></a><nav aria-label="Welcome page"><a href="#accountWorkHub">WorkHub</a><a className="landingToolsLink" href="#accountFeatures">Engineering tools</a><a href="#accountCard" onClick={exploreDemo}>Explore demo</a><a href="#accountCard" onClick={enterWorkspace}>Sign in <ArrowUpRight size={16}/></a></nav><img className="accountPetrus" src={petrusLogo} alt="Petrus"/></header>
    <main id="accountLanding"><div className={`accountPortal${register?' accountRegister':''}`}>
    <img className="accountHeroImage" src={engineeringHero} alt="" fetchPriority="high"/>

    <aside className="accountOverview" aria-label="About uSOPp.ai">
      <div className="accountIntroduction"><span className="accountEyebrow"><i/>BUILT FOR EVERY ENGINEERING TEAM</span><h2>One Workspace.<br/><em>Smarter Engineering.<br/>Better Delivery.</em></h2><p>Bring engineering teams, projects, design reviews, validation, AI assistance, and technical knowledge together in one connected platform.</p><p className="accountValueLine">Simplify workflows, reduce manual effort, improve quality, and empower teams to work smarter—from initial requirements to final delivery.</p></div>
      <div className="accountHeroActions"><a className="btn primary" href="#accountCard" onClick={enterWorkspace}>Explore Workspace <ArrowUpRight size={19}/></a><a className="btn" href="#accountFeatures">Discover Capabilities <ArrowRight size={19}/></a></div>
      <div className="accountTrust"><span><Check size={17}/>Built around your projects</span><span><Check size={17}/>Engineer stays in control</span></div>
      <div className="accountOverviewFooter">PROJECTS. PEOPLE. ENGINEERING EVIDENCE.</div>
    </aside>
    <section id="accountCard" className="accountCard" aria-labelledby="accountHeading">
    <div className="accountFormHeader"><span className="accountEyebrow">{register?'REQUEST ACCESS':'WELCOME BACK'}</span><h1 id="accountHeading">{register?'Request an account':'Sign in to uSOPp.ai'}</h1><p>{register?'Send your details to Admin. Your account will be ready after it is enabled.':'Sign in to continue your projects and engineering checks.'}</p></div>
    {notice&&<p className="accountSuccess" role="status">{notice}</p>}
    {!serviceReady&&<div className="accountConnection" role="alert"><b>Server connection needs attention</b><p>{error}</p><button type="button" className="btn" disabled={busy} onClick={()=>void retryConnection()}><RefreshCw size={16}/>{busy?'Checking…':'Check connection'}</button></div>}
    <form onSubmit={submit} className="accountForm">
      <label>Username<input ref={usernameInput} className="textInput" required maxLength={40} minLength={register?3:1} autoComplete="username" value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/></label>
      <PasswordInput key={register?'new-password':'current-password'} label="Password" required minLength={register?12:1} maxLength={128} autoComplete={register?'new-password':'current-password'} value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/>
      {register&&<><p className="accountPasswordHint">Use at least 12 characters.</p><PasswordInput label="Confirm password" required maxLength={128} autoComplete="new-password" value={form.confirm} onChange={e=>setForm({...form,confirm:e.target.value})}/>
        <div className="accountProfileFields"><label>Designation<input className="textInput" required maxLength={120} autoComplete="organization-title" value={form.designation} onChange={e=>setForm({...form,designation:e.target.value})}/></label>
        <label>Email ID (optional)<input className="textInput" type="email" maxLength={254} value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></label><label>Company name<input className="textInput" required maxLength={120} autoComplete="organization" value={form.company} onChange={e=>setForm({...form,company:e.target.value})}/></label></div></>}
      {error&&serviceReady&&<p role="alert" className="accountError">{error}</p>}
      {!register&&form.username.toLowerCase()==='demo'&&<p className="accountDemoNotice" role="status">Demo credentials are filled in. Click Sign in to begin your 30-minute session.</p>}
      <button className="btn primary accountSubmit" disabled={busy||!serviceReady}>{busy?'Please wait…':register?'Send account request':'Sign in'}{!busy&&<ArrowRight size={18}/>}</button>
    </form>
    <div className="accountSwitch"><p>{register?'Already have an account?':'Need access to the workspace?'}</p><button className="btn" disabled={busy} onClick={()=>{setRegister(!register);setNotice('');if(serviceReady)setError('');setForm({...form,password:'',confirm:''})}}>{register?'Back to sign in':'New user? Request an account'}</button></div>
    <p className="accountFooter">Shared tools. Traceable engineering.</p>
  </section></div>
    <LandingHighlights/>
    </main><footer className="accountLandingFooter"><span>uSOPp.ai · Engineering workspace</span><span>Shared tools. Traceable engineering.</span></footer></div>;
}
