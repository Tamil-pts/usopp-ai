import {useCallback,useEffect,useRef,useState,lazy,Suspense,type ReactNode} from 'react';
import {BarChart3,Plus,Settings2} from 'lucide-react';
import {useAccount} from '../../account/AuthProvider';
import {hub,type HubRow as Row} from '../projectApi';
import {projectPresentation,savePreference,PROJECT_KEY,type ProjectPresentation} from './workspacePreferences';
import './workspace-dashboards.css';
const DashboardBuilder=lazy(()=>import('./DashboardBuilder'));
type Props={items:Row[];projects:Row[];users:Row[];filteredIds:string[];active:boolean;children:ReactNode;onView:(view:string)=>void;onOpen:(row:Row)=>void};
export function ProjectsDashboard({items,projects,users,filteredIds,active,children,onView,onOpen}:Props){
 const {user}=useAccount(),[prefs,setPrefs]=useState<ProjectPresentation>(projectPresentation),[creating,setCreating]=useState(false),[createRequest,setCreateRequest]=useState(0),[options,setOptions]=useState(false),[boards,setBoards]=useState<Row[]>([]),[error,setError]=useState('');
 const dirty=useRef(false),dirtyChanged=useCallback((value:boolean)=>{dirty.current=value;},[]);
 useEffect(()=>{setPrefs(projectPresentation());setCreating(false);dirty.current=false;},[user.id]);
 useEffect(()=>{if(!active)return;let disposed=false;const selected=projectPresentation().id;
  void hub('/dashboards').then(value=>{if(disposed)return;setBoards(value.items);if(selected&&projectPresentation().id===selected&&!value.items.some((row:Row)=>row.id===selected)){
   const next={...projectPresentation(),id:''};setPrefs(next);setError('The previous project dashboard is no longer available. Standard project cards are shown.');
   void savePreference(PROJECT_KEY,next).catch(e=>{if(!disposed)setError(e.message);});
  }}).catch(e=>{if(!disposed)setError(e.message);});return()=>{disposed=true;};
 },[active,user.id]);
 const update=async(next:ProjectPresentation)=>{setError('');setPrefs(next);try{await savePreference(PROJECT_KEY,next);}catch(e){setError((e as Error).message);}};
 const create=()=>{if(dirty.current&&!window.confirm('Discard unsaved dashboard changes?'))return;dirty.current=false;setCreating(true);setCreateRequest(v=>v+1);};
 const saved=useCallback(async(record:Row)=>{const current=projectPresentation(),next={...current,id:record.id,visible:true};await savePreference(PROJECT_KEY,next);setPrefs(next);setCreating(false);dirty.current=false;},[]);
 return <section className="wh-project-dashboard" aria-label="Project cards and graphs"><header className="wh-project-dashboard-toolbar"><div><strong><BarChart3 size={16}/>Project cards &amp; graphs</strong><small>{filteredIds.length} filtered projects</small></div><div className="actions"><button className="btn" onClick={create}><Plus size={14}/>{prefs.id?'New project dashboard':'Customize cards & graphs'}</button><button className="btn" aria-expanded={options} onClick={()=>{setOptions(v=>!v);void hub('/dashboards').then(r=>setBoards(r.items)).catch(e=>setError(e.message));}}><Settings2 size={14}/>Display options</button></div></header>{options&&<div className="wh-project-dashboard-options"><label><input type="checkbox" checked={prefs.visible} onChange={e=>{if(dirty.current&&!window.confirm('Discard unsaved dashboard changes?'))return;dirty.current=false;setCreating(false);void update({...prefs,visible:e.target.checked});}}/>Show project cards and graphs</label><label>Saved dashboard<select aria-label="Project summary dashboard" value={prefs.id} onChange={e=>{if(dirty.current&&!window.confirm('Discard unsaved dashboard changes?'))return;dirty.current=false;setCreating(false);void update({...prefs,id:e.target.value});}}><option value="">Standard project cards</option>{boards.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label></div>}{error&&<p className="wh-error" role="alert">{error}</p>}{prefs.visible||creating?(prefs.id||creating)?<Suspense fallback={<p role="status">Opening project dashboard...</p>}><DashboardBuilder controlledId={creating?'':prefs.id} createRequest={creating?createRequest:0} defaultTemplate="project-summary" defaultName="Project cards & graphs" compactHeader hideGlobalFilters scope={{project_ids:filteredIds}} items={items} projects={projects} users={users} active={active} onView={onView} onOpen={onOpen} onSaved={saved} onDeleted={async()=>{await update({...projectPresentation(),id:''});dirty.current=false;}} onDirtyChange={dirtyChanged} onCancelCreate={()=>setCreating(false)}/></Suspense>:children:null}</section>;
}
