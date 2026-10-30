import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {LayoutDashboard,ShieldCheck,GitCompare,BookOpen,MessageSquare,Settings,Activity,HelpCircle,FilePenLine,Cpu,ChevronRight, BrainCircuit, Bot, CircuitBoard,FolderOpen,ClipboardCheck,ListTodo,Users,FileText,CalendarDays,History} from 'lucide-react';
import {useAccount} from '../features/account/AuthProvider';
import {FEATURES} from './features';
import {PAGE_MODULES,visibleModules,type WorkspaceModule} from './workspaceModules';
import usoppLogo from '../usopp_logo.png';

export type WorkspacePage='home'|'validation'|'compare'|'circuit'|'edesign'|'rules'|'chatbot'|'settings'|'plc'|'help';
export type AssistTab='chat'|'configure'|'learning';
export const WORKSPACE_NAVIGATION=[
  {id:'home',label:'WorkHub',Icon:LayoutDashboard}, {id:'validation',label:FEATURES.validation.name,Icon:ShieldCheck},
  {id:'plc',label:FEATURES.plc.name,Icon:Activity}, {id:'rules',label:FEATURES.rules.name,Icon:BookOpen},
  {id:'compare',label:FEATURES.compare.name,Icon:GitCompare}, {id:'circuit',label:'Circuit Compare',Icon:CircuitBoard},
  {id:'edesign',label:'e-design',Icon:FilePenLine}, {id:'chatbot',label:'AI Assist',Icon:MessageSquare},
  {id:'settings',label:'Settings',Icon:Settings}, {id:'help',label:'Help',Icon:HelpCircle},
] as const;
type Group='workhub'|'plc'|'design'|'assist'|'virtual';
export function WorkspaceNavigation({page,onSelect}:{page:WorkspacePage;onSelect:(page:WorkspacePage,tab?:AssistTab)=>void}){
  const {user}=useAccount();const modules=visibleModules(user);const [group,setGroup]=useState<Group|null>(null),[spin,setSpin]=useState(false),[hubSection,setHubSection]=useState<'overview'|'projects'|'documents'|null>(null),[position,setPosition]=useState({left:0,top:0});
  const panel=useRef<HTMLDivElement>(null),anchor=useRef<HTMLButtonElement|null>(null);
  const can=(id:WorkspaceModule)=>modules.includes(id);
  useEffect(()=>{if(!group)return;const close=(event:PointerEvent)=>{if(!panel.current?.contains(event.target as Node)&&!anchor.current?.contains(event.target as Node))setGroup(null)};const keys=(event:KeyboardEvent)=>{if(event.key==='Escape'){setGroup(null);anchor.current?.focus()}};document.addEventListener('pointerdown',close);document.addEventListener('keydown',keys);return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',keys)}},[group]);
  useEffect(()=>{setGroup(null)},[modules.join('|')]);
  const choose=(target:WorkspacePage,tab?:AssistTab)=>{setGroup(null);onSelect(target,tab)};
  const button=({id,label,Icon}:typeof WORKSPACE_NAVIGATION[number])=>{const module=PAGE_MODULES[id as keyof typeof PAGE_MODULES];if(module&&!can(module))return null;return <button type="button" key={id} className={page===id?'active':''} aria-current={page===id?'page':undefined} onClick={()=>choose(id)}><Icon aria-hidden="true"/><span>{label}</span></button>};
  const item=(id:WorkspacePage)=>button(WORKSPACE_NAVIGATION.find(value=>value.id===id)!);
  const open=(name:Group,event:React.MouseEvent<HTMLButtonElement>)=>{if(group===name){setGroup(null);return}const rect=event.currentTarget.getBoundingClientRect();anchor.current=event.currentTarget;setPosition({left:Math.max(8,Math.min(rect.right+8,window.innerWidth-290)),top:Math.max(8,Math.min(rect.top,window.innerHeight-260))});setSpin(false);setHubSection(null);setGroup(name);if(name==='workhub'&&page!=='home'){onSelect('home');window.dispatchEvent(new CustomEvent('workhub-select-view',{detail:user.isDemo?'recent':'dashboard'}));}};
  const chooseHub=(view:string)=>{setGroup(null);onSelect('home');window.dispatchEvent(new CustomEvent('workhub-select-view',{detail:view}));};
  const groupButton=(name:Group,label:string,Icon:typeof Cpu,active:boolean)=><button type="button" className={active?'active':''} aria-expanded={group===name} aria-controls={group===name?'workspace-flyout':undefined} onClick={e=>open(name,e)}><Icon aria-hidden="true"/><span>{label}</span><ChevronRight className="workspaceGroupChevron" aria-hidden="true"/></button>;
  const entry=(label:string,Icon:typeof Cpu,action:()=>void,selected=false)=><button type="button" className={'workspaceFlyoutEntry'+(selected?' active':'')} onClick={action} aria-current={selected?'page':undefined}><Icon aria-hidden="true"/><span>{label}</span></button>;
  const plcVisible=['bytemap','datainspect','matchview','logicscan'].some(id=>can(id as WorkspaceModule));
  return <><aside className="rail"><div className="brand"><img src={usoppLogo} alt="uSOPp.ai"/></div><nav className="nav railMainNav" aria-label="Main navigation">
    {can('workhub')&&groupButton('workhub','WorkHub',LayoutDashboard,page==='home')}{plcVisible&&groupButton('plc','PLC',Cpu,['validation','plc','compare','rules'].includes(page))}
    {can('edesign')&&groupButton('design','e-design',FilePenLine,['edesign','circuit'].includes(page))}
    {can('assistant')&&groupButton('assist','AI Assist',MessageSquare,page==='chatbot')}
    {can('virtual_plc')&&groupButton('virtual','Virtual',Cpu,false)}
    </nav><nav className="nav railUtilities" aria-label="Settings and help">{item('settings')}{item('help')}</nav></aside>
    {group&&createPortal(<div ref={panel} id="workspace-flyout" className="workspaceFlyout" style={{left:position.left,top:position.top}} role="group" aria-label={`${group==='workhub'?'WorkHub':group==='design'?'e-design':group==='assist'?'AI Assist':group==='virtual'?'Virtual':'PLC'} submenu`}>
      <div className="workspaceFlyoutHeading">{group==='workhub'?'WorkHub':group==='plc'?'PLC':group==='design'?'e-design':group==='assist'?'AI Assist':'Virtual'}</div>
      {group==='workhub'&&<>{([{id:'overview',label:'Overview',Icon:LayoutDashboard},{id:'projects',label:'Projects',Icon:FolderOpen},{id:'documents',label:'Documents',Icon:FileText}] as const).filter(({id})=>!user.isDemo||id==='overview').map(({id,label,Icon})=><div key={id}><button type="button" className="workspaceFlyoutEntry workspaceNestedToggle" aria-expanded={hubSection===id} aria-controls={`workhub-${id}-submenu`} onClick={()=>setHubSection(v=>v===id?null:id)}><Icon aria-hidden="true"/><span>{label}</span><ChevronRight className={hubSection===id?'expanded':''} aria-hidden="true"/></button>{hubSection===id&&<div id={`workhub-${id}-submenu`} className="workspaceNestedMenu">{id==='overview'?user.isDemo?entry('Recent activity',History,()=>chooseHub('recent')):<>{entry('Dashboard',LayoutDashboard,()=>chooseHub('dashboard'))}{entry('Approval',ClipboardCheck,()=>chooseHub('approvals'))}{entry('My Work',ListTodo,()=>chooseHub('mine'))}{entry('Team Activity',Users,()=>chooseHub('activity'))}</>:id==='projects'&&!user.isDemo?<>{entry('Project Portfolio',FolderOpen,()=>chooseHub('projects'))}{entry('Reports',FileText,()=>chooseHub('reports'))}{entry('Task Management',CalendarDays,()=>chooseHub('workload'))}{entry('All documents',FileText,()=>chooseHub('documents'))}</>:!user.isDemo&&<>{entry('MOM',FileText,()=>chooseHub('documents:mom'))}{entry('FRD',FileText,()=>chooseHub('documents:frd'))}{entry('Validation',FileText,()=>chooseHub('documents:test'))}{entry('FAT',FileText,()=>chooseHub('documents:fat'))}{entry('Release',FileText,()=>chooseHub('documents:closure'))}</>}</div>}</div>)}</>}
      {group==='plc'&&<>{(can('bytemap')||can('datainspect'))&&<><button type="button" className="workspaceFlyoutEntry workspaceNestedToggle" aria-expanded={spin} aria-controls="spin-connect-submenu" onClick={()=>setSpin(v=>!v)}><Activity aria-hidden="true"/><span>Spin connect</span><ChevronRight className={spin?'expanded':''} aria-hidden="true"/></button>{spin&&<div id="spin-connect-submenu" className="workspaceNestedMenu">{can('bytemap')&&entry('ByteMap',ShieldCheck,()=>choose('validation'),page==='validation')}{can('datainspect')&&entry('DataInspect',Activity,()=>choose('plc'),page==='plc')}</div>}</>}{can('matchview')&&entry('MatchView',GitCompare,()=>choose('compare'),page==='compare')}{can('logicscan')&&entry('LogicScan',BookOpen,()=>choose('rules'),page==='rules')}</>}
      {group==='design'&&<>{entry('MatchView',CircuitBoard,()=>choose('circuit'),page==='circuit')}{entry('Review',FilePenLine,()=>choose('edesign'),page==='edesign')}</>}
      {group==='assist'&&<>{entry('Chat',MessageSquare,()=>choose('chatbot','chat'))}{entry('Rule configuration',Bot,()=>choose('chatbot','configure'))}{entry('KnowHub',BrainCircuit,()=>choose('chatbot','learning'))}</>}
      {group==='virtual'&&<a className="workspaceFlyoutEntry virtualPlcNav" href="/virtual-plc/" aria-label="Open Virtual PLC workspace"><Cpu aria-hidden="true"/><span>PLC</span></a>}
    </div>,document.body)}</>;
}
