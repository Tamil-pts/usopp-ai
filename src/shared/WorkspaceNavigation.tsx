import {LayoutDashboard,ShieldCheck,GitCompare,BookOpen,MessageSquare,Settings,Activity,HelpCircle} from 'lucide-react';
import {FEATURES} from './features';
import usoppLogo from '../usopp_logo.png';

export type WorkspacePage='home'|'validation'|'compare'|'rules'|'chatbot'|'settings'|'plc'|'help';
export const WORKSPACE_NAVIGATION=[
  {id:'home',label:'WorkHub',Icon:LayoutDashboard},
  {id:'validation',label:FEATURES.validation.name,Icon:ShieldCheck},
  {id:'plc',label:FEATURES.plc.name,Icon:Activity},
  {id:'compare',label:FEATURES.compare.name,Icon:GitCompare},
  {id:'rules',label:FEATURES.rules.name,Icon:BookOpen},
  {id:'chatbot',label:FEATURES.chatbot.name,Icon:MessageSquare},
  {id:'settings',label:'Settings',Icon:Settings},
  {id:'help',label:'Help',Icon:HelpCircle},
] as const;

export function WorkspaceNavigation({page,onSelect}:{page:WorkspacePage;onSelect:(page:WorkspacePage)=>void}){
  const button=({id,label,Icon}:typeof WORKSPACE_NAVIGATION[number])=><button type="button" key={id} className={page===id?'active':''} aria-current={page===id?'page':undefined} onClick={()=>onSelect(id)}><Icon aria-hidden="true"/><span>{label}</span></button>;
  return <aside className="rail">
    <div className="brand"><img src={usoppLogo} alt="usop.ai"/></div>
    <nav className="nav railMainNav" aria-label="Main navigation">
      {WORKSPACE_NAVIGATION.filter(item=>!['settings','help','plc'].includes(item.id)).map(item=>item.id==='validation'?
        <div key="spinconnect" className="spinConnectNav" role="group" aria-label="Spin connect" data-active={page==='validation'||page==='plc'?true:undefined}>
          <div className="spinConnectNavLabel" aria-hidden="true"><span>Spin connect</span><span>🤖</span></div>
          <div className="spinConnectNavTools">{WORKSPACE_NAVIGATION.filter(tool=>tool.id==='validation'||tool.id==='plc').map(button)}</div>
        </div>:button(item))}
    </nav>
    <nav className="nav railUtilities" aria-label="Settings and help">{WORKSPACE_NAVIGATION.filter(item=>item.id==='settings'||item.id==='help').map(button)}</nav>
  </aside>;
}
