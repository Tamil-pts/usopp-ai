import {userStorage} from './userStorage';
import {TopMenu} from './TopMenu';
import {routeEvent,routeParams} from './navigation';
import {useEffect,useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import './workspace-subnav.css';
import {LayoutDashboard,ShieldCheck,GitCompare,BookOpen,MessageSquare,Settings,Activity,HelpCircle,FilePenLine,Cpu,ChevronRight, BrainCircuit, Bot, CircuitBoard,FolderOpen,ClipboardCheck,Clock,ListTodo,Users,FileText,CalendarDays,History} from 'lucide-react';
import {useAccount} from '../features/account/AuthProvider';
import {FEATURES} from './features';
import {PAGE_MODULES,visibleModules,type WorkspaceModule} from './workspaceModules';
import usoppLogo from '../usopp_logo.png';

export type WorkspacePage='home'|'validation'|'compare'|'circuit'|'edesign'|'rules'|'chatbot'|'settings'|'plc'|'help'|'electrical';
export type AssistTab='chat'|'configure'|'learning'|'documents'|'presentations';
export const WORKSPACE_NAVIGATION=[
  {id:'home',label:'WorkHub',Icon:LayoutDashboard}, {id:'validation',label:FEATURES.validation.name,Icon:ShieldCheck},
  {id:'plc',label:FEATURES.plc.name,Icon:Activity}, {id:'rules',label:FEATURES.rules.name,Icon:BookOpen},
  {id:'compare',label:FEATURES.compare.name,Icon:GitCompare}, {id:'circuit',label:'Circuit Compare',Icon:CircuitBoard},
  {id:'electrical',label:'Virtual Electrical',Icon:CircuitBoard}, {id:'edesign',label:'e-design',Icon:FilePenLine}, {id:'chatbot',label:'AI Assist',Icon:MessageSquare},
  {id:'settings',label:'Settings',Icon:Settings}, {id:'help',label:'Help',Icon:HelpCircle},
] as const;
type Group='workhub'|'plc'|'design'|'assist'|'virtual';
export function WorkspaceNavigation({page,onSelect,projectLink}:{page:WorkspacePage;onSelect:(page:WorkspacePage,tab?:AssistTab)=>boolean|void;projectLink?:ReactNode}){
  const {user}=useAccount();const modules=visibleModules(user);const [collapsed,setCollapsed]=useState(()=>userStorage.getItem('usopp_nav_collapsed')==='true');
  const pageGroup=(value:WorkspacePage):Group|null=>value==='home'?'workhub':['validation','plc','compare','rules'].includes(value)?'plc':['edesign','circuit'].includes(value)?'design':value==='chatbot'?'assist':value==='electrical'?'virtual':null;
  const [assistTab,setAssistTab]=useState(()=>routeParams().get('assistTab')||'chat');
  useEffect(()=>{const update=()=>setAssistTab(routeParams().get('assistTab')||'chat');window.addEventListener(routeEvent,update);return()=>window.removeEventListener(routeEvent,update)},[]);
  const [group,setGroup]=useState<Group|null>(()=>pageGroup(page)),[spin,setSpin]=useState(false),[hubSection,setHubSection]=useState<'documents'|null>(null),[hubView,setHubView]=useState('dashboard');
  const spinTrigger=useRef<HTMLButtonElement>(null),spinMenu=useRef<HTMLDivElement>(null);
  const [spinPosition,setSpinPosition]=useState({left:8,top:64,maxHeight:300});
  useLayoutEffect(()=>{if(!spin)return;const position=()=>{const rect=spinTrigger.current?.getBoundingClientRect();if(!rect)return;const top=rect.bottom+116>window.innerHeight?Math.max(8,rect.top-112):rect.bottom+4;setSpinPosition({left:Math.max(8,Math.min(rect.left,window.innerWidth-248)),top,maxHeight:Math.max(60,window.innerHeight-top-8)});};position();window.addEventListener('resize',position);window.addEventListener('scroll',position,true);return()=>{window.removeEventListener('resize',position);window.removeEventListener('scroll',position,true);};},[spin]);
  useEffect(()=>{if(!spin)return;const outside=(event:PointerEvent)=>{if(!spinMenu.current?.contains(event.target as Node)&&!spinTrigger.current?.contains(event.target as Node))setSpin(false);};const keys=(event:KeyboardEvent)=>{if(event.key==='Escape'){setSpin(false);spinTrigger.current?.focus();}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',keys);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',keys);};},[spin]);
  const can=(id:WorkspaceModule)=>modules.includes(id);
  useEffect(()=>{setGroup(pageGroup(page));setHubSection(null);setSpin(false);},[page,modules.join('|')]);
  useEffect(()=>{const change=(event:Event)=>setHubView(String((event as CustomEvent).detail).split(':')[0]);window.addEventListener('workhub-view-changed',change);return()=>{window.removeEventListener('workhub-view-changed',change);};},[]);
  const choose=(target:WorkspacePage,tab?:AssistTab)=>{setHubSection(null);setSpin(false);onSelect(target,tab);};
  const button=({id,label,Icon}:typeof WORKSPACE_NAVIGATION[number])=>{const module=PAGE_MODULES[id as keyof typeof PAGE_MODULES];if(module&&!can(module))return null;return <button type="button" key={id} className={page===id?'active':''} aria-current={page===id?'page':undefined} onClick={()=>choose(id)}><span className="railIcon"><Icon aria-hidden="true"/></span><span className="railLinkCopy">{label}</span></button>};
  const item=(id:WorkspacePage)=>button(WORKSPACE_NAVIGATION.find(value=>value.id===id)!);
  const open=(name:Group)=>{if(pageGroup(page)===name){setGroup(name);setHubSection(null);setSpin(false);return;}
    const target:WorkspacePage=name==='workhub'?'home':name==='plc'?(can('bytemap')?'validation':can('datainspect')?'plc':can('matchview')?'compare':'rules'):name==='design'?'edesign':name==='assist'?'chatbot':'electrical';
    if(name==='virtual'&&!can('edesign')){setGroup(name);return;}
    if(onSelect(target,name==='assist'?'chat':undefined)===false)return;
    setGroup(name);setHubSection(null);setSpin(false);if(name==='workhub')window.dispatchEvent(new CustomEvent('workhub-select-view',{detail:user.isDemo?'recent':'dashboard'}));
  };
  const chooseHub=(view:string)=>{setHubSection(null);if(onSelect('home')===false)return;window.dispatchEvent(new CustomEvent('workhub-select-view',{detail:view}));};
  const groupButton=(name:Group,label:string,Icon:typeof Cpu,_active:boolean)=><button type="button" className={group===name?'active':''} aria-label={label} title={label} aria-expanded={group===name} aria-controls={group===name?'workspace-subnav':undefined} onClick={()=>open(name)}><span className="railIcon"><Icon aria-hidden="true"/></span><span className="railLinkCopy">{label}<small>{{workhub:"Projects & delivery",plc:"Validation & insights",design:"Drawings & reviews",assist:"Knowledge & assistance",virtual:"Models & simulation"}[name]}</small></span><ChevronRight className="workspaceGroupChevron" aria-hidden="true"/></button>;
  const entry=(label:string,Icon:typeof Cpu,action:()=>void,selected=false)=><button type="button" className={'workspaceFlyoutEntry'+(selected?' active':'')} onClick={action} aria-current={selected?'page':undefined}><Icon aria-hidden="true"/><span>{label}</span></button>;
  const showProject=!!projectLink&&(group==='plc'||group==='design');
  const plcVisible=['bytemap','datainspect','matchview','logicscan'].some(id=>can(id as WorkspaceModule));
  return <><aside className="rail" data-collapsed={collapsed}><button className="railBrand" type="button" aria-label={collapsed?'Expand sidebar':'Collapse sidebar'} aria-expanded={!collapsed} title={collapsed?'Expand navigation':'Compact navigation'} onClick={()=>setCollapsed(value=>{userStorage.setItem('usopp_nav_collapsed',String(!value));return !value})}><div className="brand"><img src={usoppLogo} alt="uSOPp.ai"/></div><div className="railBrandCopy"><b>uSOPp.ai</b><small>ENGINEERING WORKSPACE</small></div></button><div className="railSectionLabel">YOUR WORKSPACE</div><nav className="nav railMainNav" aria-label="Main navigation">
    {can('workhub')&&groupButton('workhub','WorkHub',LayoutDashboard,page==='home')}{plcVisible&&groupButton('plc','PLC',Cpu,['validation','plc','compare','rules'].includes(page))}
    {can('edesign')&&groupButton('design','e-design',FilePenLine,['edesign','circuit'].includes(page))}
    {can('assistant')&&groupButton('assist','AI Assist',MessageSquare,page==='chatbot')}
    {(can('virtual_plc')||can('edesign'))&&groupButton('virtual','Virtual',Cpu,page==='electrical')}
    </nav><nav className="nav railUtilities" aria-label="Settings and help">{item('settings')}{item('help')}</nav></aside>
    <nav id="workspace-subnav" className={'workspaceSubnav'+(!group?' isEmpty':'')+(showProject?' hasProjectLink':'')} role="group" data-workspace={group||''} aria-label={`${group==='workhub'?'WorkHub':group==='design'?'e-design':group==='assist'?'AI Assist':group==='virtual'?'Virtual':'PLC'} submenu`} onKeyDown={event=>{if(event.key==='Escape'){setHubSection(null);setSpin(false);}}}><div className="workspaceSubnavRow">
      {group==='workhub'&&<>{entry(user.isDemo?'Recent activity':'Overview',LayoutDashboard,()=>chooseHub(user.isDemo?'recent':'dashboard'),hubView==='dashboard'||hubView==='recent')}{!user.isDemo&&<><TopMenu label="Inbox" icon={<MessageSquare aria-hidden="true"/>}>{[['mine','My Work'],['approvals','Approvals'],['tasks','Tasks & assignments'],['timesheet','Log hours & timesheets']].map(([view,label])=><div key={view}>{entry(label,view==='timesheet'?Clock:ClipboardCheck,()=>window.dispatchEvent(new CustomEvent('usopp-open-inbox',{detail:{view}})))}</div>)}</TopMenu>{entry('Projects',FolderOpen,()=>chooseHub('projects'),hubView==='projects')}<TopMenu label="Documents" icon={<FileText aria-hidden="true"/>} active={hubView==='documents'}>{entry('All documents',FolderOpen,()=>chooseHub('documents'))}{[['mom','Meeting minutes'],['frd','Requirements / FRD'],['flowchart','Flowcharts & visuals'],['mindmap','Mind maps'],['test','Validation reports'],['test_report','Test reports'],['fat','Factory acceptance / FAT'],['closure','Project closure']].map(([id,label])=><div key={id}>{entry(label,FileText,()=>chooseHub('documents:'+id))}</div>)}</TopMenu>{entry('Competency Hub',Activity,()=>chooseHub('praxis'),hubView==='praxis')}{entry('TechShare',BookOpen,()=>chooseHub('passport'),hubView==='passport')}</>}</>}

      {group==='plc'&&<>{(can('bytemap')||can('datainspect'))&&<div className="workspaceSpinGroup"><button ref={spinTrigger} type="button" className="workspaceFlyoutEntry workspaceNestedToggle" aria-expanded={spin} aria-controls="spin-connect-submenu" onClick={()=>setSpin(v=>!v)} onKeyDown={event=>{if(event.key==='ArrowDown'){event.preventDefault();setSpin(true);setTimeout(()=>spinMenu.current?.querySelector<HTMLButtonElement>('button')?.focus(),0);}}}><Activity aria-hidden="true"/><span>Spin Connect Workspace</span><ChevronRight className={spin?'expanded':''} aria-hidden="true"/></button></div>}{can('matchview')&&entry('MatchView',GitCompare,()=>choose('compare'),page==='compare')}{can('logicscan')&&entry('LogicScan',BookOpen,()=>choose('rules'),page==='rules')}</>}
      {group==='design'&&<>{entry('MatchView',CircuitBoard,()=>choose('circuit'),page==='circuit')}{entry('Review',FilePenLine,()=>choose('edesign'),page==='edesign')}</>}
      {group==='assist'&&<>{entry('Chat',MessageSquare,()=>choose('chatbot','chat'),assistTab==='chat')}{entry('Rule configuration',Bot,()=>choose('chatbot','configure'),assistTab==='configure')}{entry('KnowHub',BrainCircuit,()=>choose('chatbot','learning'),assistTab==='learning')}{entry('Document Compare',FileText,()=>choose('chatbot','documents'),assistTab==='documents')}{entry('Presentation Studio',FileText,()=>choose('chatbot','presentations'),assistTab==='presentations')}</>}
      {group==='virtual'&&<>{can('virtual_plc')&&<a className="workspaceFlyoutEntry virtualPlcNav" href="/virtual-plc/" aria-label="Open Virtual PLC workspace"><Cpu aria-hidden="true"/><span>PLC</span></a>}{can('edesign')&&entry('Electrical',CircuitBoard,()=>choose('electrical'),page==='electrical')}</>}
    </div>{showProject&&<div className="workspaceSubnavProject">{projectLink}</div>}</nav>
    {spin&&group==='plc'&&createPortal(<div ref={spinMenu} id="spin-connect-submenu" className="workspaceSpinMenu" style={spinPosition} role="group" aria-label="Spin Connect tools">{can('bytemap')&&entry('ByteMap',ShieldCheck,()=>choose('validation'),page==='validation')}{can('datainspect')&&entry('DataInspect',Activity,()=>choose('plc'),page==='plc')}</div>,document.body)}</>;
}
