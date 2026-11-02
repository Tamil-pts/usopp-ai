import {useEffect,useState,type ReactNode} from 'react';
import {ArrowRight,ArrowLeft,UserRound,Palette,Users,FilePenLine,Files,Workflow,Bell,BrainCircuit,Cpu,Table2,Database,Search,Settings2} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {userStorage} from '../../shared/userStorage';
import './settings-workspace.css';

const categories=[
 {id:'profile',group:'Personal',label:'My account',description:'Profile photo, contact details and password.',keywords:'email security password picture',Icon:UserRound,tone:'blue'},
 {id:'appearance',group:'Personal',label:'Appearance',description:'Choose your theme and accent colors.',keywords:'dark light color colour theme',Icon:Palette,tone:'purple'},
 {id:'users',group:'WorkHub',label:'User management',description:'Approve account requests, manage access and organize your team.',keywords:'admin users roles departments teams people permission',Icon:Users,tone:'mint',admin:true},
 {id:'document-studio',group:'WorkHub',label:'Document Studio',description:'Create and customize reusable document templates.',keywords:'template editor layout design MOM FRD FAT validation report closure',Icon:FilePenLine,tone:'purple',noDemo:true},
 {id:'documents',group:'WorkHub',label:'Document setup',description:'Company branding, document numbers and report formats.',keywords:'numbering logo revision PDF header footer format',Icon:Files,tone:'blue',admin:true},
 {id:'workflow',group:'WorkHub',label:'Workflows & approvals',description:'Project workflows, required documents and review controls.',keywords:'project template assignment approval milestone quality',Icon:Workflow,tone:'amber',admin:true},
 {id:'connections',group:'WorkHub',label:'Notifications & sharing',description:'Manage email, Teams and notification preferences.',keywords:'connections alerts teams email notifications sharing',Icon:Bell,tone:'mint'},
 {id:'assistant',group:'Engineering',label:'AI & Chopper',description:'Local models, inference and assistant preferences.',keywords:'AI model provider context Qwen CPU GPU token chopper',Icon:BrainCircuit,tone:'purple'},
 {id:'plc',group:'Engineering',label:'PLC & metadata',description:'Machine definitions, metadata workbook and BOOL representation.',keywords:'bool USINT metadata workbook machine department',Icon:Cpu,tone:'mint'},
 {id:'tables',group:'Engineering',label:'Tables & columns',description:'Choose visible columns, their order and table widths.',keywords:'HMI min max value source table column width layout',Icon:Table2,tone:'blue'},
 {id:'data',group:'Engineering',label:'Data & diagnostics',description:'Temporary files, knowledge transfer and application logs.',keywords:'cache storage temporary logs diagnostics export backup safety knowledge',Icon:Database,tone:'amber'},
];
export function SettingsShell({panels}:{panels:Record<string,ReactNode>}){
 const {user}=useAccount(),allowed=categories.filter(c=>(!c.admin||user.role==='admin')&&(!c.noDemo||!user.isDemo)),ids=allowed.map(c=>c.id);
 const initial=()=>{const hash=/^#settings\/([a-z-]+)$/.exec(location.hash)?.[1],saved=hash||userStorage.getItem('usopp_settings_section')||'overview';return ids.includes(saved)?saved:'overview';};
 const [section,setSection]=useState(initial),[visited,setVisited]=useState(()=>new Set([initial()])),[query,setQuery]=useState('');
 const choose=(id:string)=>{if(id!=='overview'&&!ids.includes(id))return;setSection(id);setQuery('');setVisited(v=>new Set([...v,id]));userStorage.setItem('usopp_settings_section',id);history.replaceState(null,'','#settings/'+id);};
 useEffect(()=>{const open=(event:Event)=>choose((event as CustomEvent).detail||'overview'),hash=()=>{const id=/^#settings\/([a-z-]+)$/.exec(location.hash)?.[1];if(id)choose(id);};window.addEventListener('usopp-open-settings-section',open);window.addEventListener('hashchange',hash);return()=>{window.removeEventListener('usopp-open-settings-section',open);window.removeEventListener('hashchange',hash);};},[ids.join('|')]);
 useEffect(()=>{if(section!=='overview'&&!ids.includes(section))choose('overview');},[user.role,user.isDemo]);
 const matches=allowed.filter(c=>[c.label,c.description,c.keywords].join(' ').toLowerCase().includes(query.trim().toLowerCase()));
 const current=allowed.find(c=>c.id===section);
 return <section className="settingsWorkspace" aria-label="Settings workspace"><header className="settingsHeading"><div><span>YOUR WORKSPACE, YOUR WAY</span><h1>Settings</h1><p>Find what you need, make a change, and get back to your work.</p></div><span className="settingsAccountBadge"><UserRound size={15}/>{user.username}{user.role==='admin'&&<small>Admin</small>}</span></header>
  <div className="settingsLayout"><aside className="settingsSidebar"><label className="settingsSearch"><Search size={16}/><input aria-label="Find a setting" placeholder="Find a setting..." value={query} maxLength={100} onChange={e=>setQuery(e.target.value)}/>{query&&<button type="button" aria-label="Clear settings search" onClick={()=>setQuery('')}>Clear</button>}</label><nav aria-label="Settings categories"><button className={section==='overview'&&!query?'active':''} aria-current={section==='overview'&&!query?'page':undefined} onClick={()=>choose('overview')}><Settings2 size={17}/><span>All settings</span></button>{['Personal','WorkHub','Engineering'].filter(group=>matches.some(c=>c.group===group)).map(group=><div key={group}><h2>{group}</h2>{matches.filter(c=>c.group===group).map(c=><button key={c.id} className={section===c.id&&!query?'active':''} aria-current={section===c.id&&!query?'page':undefined} onClick={()=>choose(c.id)}><c.Icon size={17}/><span>{c.label}</span></button>)}</div>)}</nav></aside>
   <div className="settingsMain">{(section==='overview'||query)&&<><div className="settingsSectionHeading"><div><h2>{query?'Search results':'Make yourself at home'}</h2><p>{query?`${matches.length} settings match your search.`:'Your account, your team and the tools you use every day.'}</p></div></div><div className="settingsCategoryCards">{matches.map(c=><button key={c.id} className={'settingsCategoryCard '+c.tone} onClick={()=>choose(c.id)}><span className="settingsCategoryIcon"><c.Icon size={22}/></span><div><h3>{c.label}</h3><p>{c.description}</p>{c.admin&&<small>Admin settings</small>}</div><ArrowRight size={17}/></button>)}</div>{!matches.length&&<div className="settingsNoResults"><Search size={30}/><h3>No matching settings</h3><p>Try a different word, such as templates, users or columns.</p></div>}</>}
    {section!=='overview'&&!query&&current&&<header className="settingsSectionHeading"><div><button className="settingsBack" onClick={()=>choose('overview')}><ArrowLeft size={13}/>All settings</button>{section!=='users'&&<><h2>{current.label}</h2><p>{current.description}</p></>}</div></header>}
    {allowed.filter(c=>visited.has(c.id)).map(c=><div key={c.id} className="settingsPanel settingsCategoryGrid" hidden={section!==c.id||!!query} aria-label={c.label+' settings'}>{panels[c.id]}</div>)}
   </div></div>
 </section>;
}
