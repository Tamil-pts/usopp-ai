import {ToolProjectSelector} from '../shared/ToolProjectSelector';
import {flushQualityDraft} from '../features/workhub/quality/bridge';
import {userStorage} from '../shared/userStorage';
import {BuildVersionBadge,BuildVersionNotice} from '../shared/BuildStatus';
import {useCallback,useEffect,useState} from 'react';
import {LayoutDashboard,ShieldCheck,GitCompare,BookOpen,MessageSquare,Settings,Activity,HelpCircle} from 'lucide-react';
import '../styles.css';
import './workspace.css';
import type {MetaCol} from '../shared/types';
import {DEFAULT_META_COLS} from '../features/validation/metadataColumns';
import {normalizeResult} from '../features/validation/normalizeResult';
import {ValidationPage} from '../features/validation/ValidationPage';
import {useValidationWorkspace} from '../features/validation/useValidationWorkspace';
import {ComparePage} from '../features/compare/ComparePage';
import {useCompareProjects} from '../features/compare/useCompareProjects';
import {UserAvatar} from '../features/account/UserAvatar';
import {useAccount} from '../features/account/AuthProvider';
import {HelpPage} from '../features/help/HelpPage';
import {RunHistory} from '../features/history/RunHistory';
import {HistoryResultDialog} from '../features/history/HistoryResultDialog';
import {WorkHub} from '../features/workhub/WorkHub';
import {NotificationBell} from '../features/workhub/NotificationBell';
import {FeatureRecommendation} from '../shared/FeatureRecommendation';
import {FEATURES,type EngineeringFeature} from '../shared/features';
import '../features/help/help.css';
import {PLCDataPage} from '../features/plc/PLCDataPage';
import {RulesPage} from '../features/rules/RulesPage';
import {validateEngineeringRules} from '../features/rules/api';
import {AssistWorkspace} from '../features/assist/AssistWorkspace';
import {ChopperQuickHelp} from '../features/assist/ChopperQuickHelp';
import {SettingsPage} from '../features/settings/SettingsPage';
import {DEPARTMENTS} from '../features/rules/library';
import {DEFAULT_MACHINE_PREFIXES,type MachinePrefix} from '../features/validation/projectDetails';
import {TableLayoutProvider} from '../shared/TableLayout';
import './responsive.css';
import usoppLogo from '../usopp_logo.png';
import petrusLogo from '../petrus_logo.png';

type Page='home'|'validation'|'compare'|'rules'|'chatbot'|'settings'|'plc'|'help';
const navigation=[{id:'home',label:'WorkHub',Icon:LayoutDashboard},{id:'validation',label:FEATURES.validation.name,Icon:ShieldCheck},{id:'plc',label:FEATURES.plc.name,Icon:Activity},{id:'compare',label:FEATURES.compare.name,Icon:GitCompare},{id:'rules',label:FEATURES.rules.name,Icon:BookOpen},{id:'chatbot',label:FEATURES.chatbot.name,Icon:MessageSquare},{id:'settings',label:'Settings',Icon:Settings},{id:'help',label:'Help',Icon:HelpCircle}] as const;
function App(){
  const {user,logout}=useAccount();
  const [page,setPage]=useState<Page>('home');
  useEffect(()=>{const open=()=>{setPage('help');setTimeout(()=>document.getElementById('help-frd-sample')?.scrollIntoView({behavior:'smooth'}),250);};window.addEventListener('workhub-help-frd',open);return()=>window.removeEventListener('workhub-help-frd',open);},[]);
  useEffect(()=>{
    const openSettings=()=>{setPage('settings');requestAnimationFrame(()=>document.getElementById('workhub-notifications')?.scrollIntoView({block:'start',behavior:'smooth'}));};
    if(new URLSearchParams(window.location.search).has('workhubConnections'))openSettings();
    window.addEventListener('workhub-open-settings',openSettings);const openGrowth=()=>setPage('home');window.addEventListener('workhub-open-growth',openGrowth);window.addEventListener('workhub-open-dashboard',openGrowth);
    return()=>{window.removeEventListener('workhub-open-settings',openSettings);window.removeEventListener('workhub-open-growth',openGrowth);window.removeEventListener('workhub-open-dashboard',openGrowth);};
  },[]);
  const [dataInspectHistoryId,setDataInspectHistoryId]=useState('');
  const [plcContext,setPLCContext]=useState<Record<string,unknown>>({});
  const [historyDetail,setHistoryDetail]=useState<any>(null);
  const [theme,setTheme]=useState<'light'|'dark'>(()=>userStorage.getItem('usopp_theme')==='dark'?'dark':'light');
  const [accent,setAccent]=useState(()=>userStorage.getItem('usopp_accent')||'#4f7ff2');
  const [machineConfig,setMachineConfig]=useState<{departments:string[];prefixes:MachinePrefix[]}>({departments:DEPARTMENTS,prefixes:DEFAULT_MACHINE_PREFIXES});
  const departments=machineConfig.departments;
  const [health,setHealth]=useState<any>(null);
  const [toast,setToast]=useState('');
  const [metaCols,setMetaCols]=useState<MetaCol[]>(()=>{
    try{const saved=JSON.parse(userStorage.getItem('usopp_meta_cols_v4.30')||'null');if(!Array.isArray(saved))return DEFAULT_META_COLS;
      const valid=saved.filter((c:any,i:number)=>DEFAULT_META_COLS.some(d=>d.key===c.key)&&saved.findIndex((x:any)=>x.key===c.key)===i);
      return [...valid,...DEFAULT_META_COLS.filter(d=>!valid.some((c:any)=>c.key===d.key))];
    }catch{return DEFAULT_META_COLS}
  });
  const validation=useValidationWorkspace(machineConfig.prefixes);
  const compare=useCompareProjects(setToast);
  const [ruleResults,setRuleResults]=useState<any>(null);
  const [ruleBusy,setRuleBusy]=useState('');
  const [ruleRevision,setRuleRevision]=useState(0);
  const [assistFinding,setAssistFinding]=useState<any>(null);
  const rulesSaved=useCallback(()=>setRuleRevision(v=>v+1),[]);
  useEffect(()=>{setRuleResults(null);setAssistFinding(null)},[validation.localProjectPath,validation.projectFiles,validation.machineDepartment]);
  useEffect(()=>{document.documentElement.dataset.theme=theme;document.documentElement.style.setProperty('--accent',accent);userStorage.setItem('usopp_theme',theme);userStorage.setItem('usopp_accent',accent)},[theme,accent]);
  useEffect(()=>{userStorage.setItem('usopp_meta_cols_v4.30',JSON.stringify(metaCols))},[metaCols]);
  useEffect(()=>{let cancelled=false;const check=()=>fetch('/api/health',{cache:'no-store'}).then(r=>r.json()).then(j=>{if(typeof j.version!=='string')throw new Error();if(!cancelled)setHealth(j)}).catch(()=>{if(!cancelled)setHealth(null)});const visible=()=>{if(document.visibilityState==='visible')void check()};void check();const id=setInterval(check,15000);document.addEventListener('visibilitychange',visible);return()=>{cancelled=true;clearInterval(id);document.removeEventListener('visibilitychange',visible)}},[]);
  useEffect(()=>{let active=true;fetch('/api/admin/settings/machine-departments',{cache:'no-store'}).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not load machine departments.');if(active&&Array.isArray(data.departments)&&Array.isArray(data.prefixes))setMachineConfig(data)}).catch(()=>{});return()=>{active=false}},[]);
  const saveMachineConfig=async(next:{departments:string[];prefixes:MachinePrefix[]})=>{const response=await fetch('/api/admin/settings/machine-departments',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not save machine / department settings.');setMachineConfig(data)};
  useEffect(()=>{if(!toast)return;const id=setTimeout(()=>setToast(''),8000);return()=>clearTimeout(id)},[toast]);
  const runRules=async(rules:any)=>{
    if(!validation.localProjectPath&&!validation.projectFiles.length){setToast('Select a project in the pipeline project box to continue.');return {error:'Select a project in the pipeline project box to continue.'}}
    setRuleBusy('rules');setRuleResults(null);try{const data={...await validateEngineeringRules({...validation,rules}),pipelineRunId:rules.pipelineRunId};setRuleResults(data);setToast('Rule validation completed.');return data}catch(e:any){setToast(e.message);return {error:e.message}}finally{setRuleBusy('')}
  };
  const normalized=validation.result?normalizeResult(validation.result):null;
  const helpRows=page==='validation'?validation.result?.issues:page==='rules'?(ruleResults?.results||ruleResults?.checks||ruleResults?.checkpoints):[];
  const helpFindings=(Array.isArray(helpRows)?helpRows:[]).filter((row:any)=>!['pass','passed'].includes(String(row.status||row.severity||'').toLowerCase())).slice(0,5).map((row:any)=>Object.fromEntries(['id','name','status','severity','actual','expected','message','description','sourceFile','lineNumber','suggestedFix'].filter(key=>row[key]!=null).map(key=>[key,String(row[key]).slice(0,700)])));
  const helpContext={page,label:navigation.find(item=>item.id===page)?.label||'Workspace',projectName:validation.projectName||'',projectPath:validation.localProjectPath||'',details:page==='plc'?plcContext:undefined,findings:helpFindings,counts:page==='validation'&&validation.result?normalized?.counts:undefined};
  return <TableLayoutProvider><div className="app workspaceApp"><aside className="rail"><div className="brand"><img src={usoppLogo} alt="usop.ai"/></div><nav className="nav railMainNav" aria-label="Main navigation">{navigation.filter(n=>n.id!=='settings'&&n.id!=='help').map(({id,label,Icon})=><button key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><Icon/><span>{label}</span></button>)}</nav><nav className="nav railUtilities" aria-label="Settings and help">{navigation.filter(n=>n.id==='settings'||n.id==='help').map(({id,label,Icon})=><button key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><Icon/><span>{label}</span></button>)}</nav></aside>
    <header className="top"><div className="crumb"><b>usop.ai</b><span> / </span>{navigation.find(n=>n.id===page)?.label}</div><div className="topSpacer"/><button className="btn" aria-pressed={theme==='dark'} onClick={()=>setTheme(theme==='light'?'dark':'light')}>{theme==='light'?'Dark mode':'Light mode'}</button><div className="accountTop"><button className="accountProfileButton" aria-label="Open my profile" onClick={()=>setPage('settings')}><UserAvatar user={user}/></button><span title={`${user.designation} / ${user.company}`}>{user.username}<small className="accountRoleLabel">{user.role==='admin'?'Admin':'User'}</small></span><button className="btn" onClick={()=>{void flushQualityDraft().then(()=>logout()).catch((error:Error)=>setToast(error.message))}}>Sign out</button></div><NotificationBell onOpen={(project,item)=>{setPage('home');window.dispatchEvent(new CustomEvent('workhub-open-project',{detail:{project,item}}));}}/><BuildVersionBadge health={health}/><ChopperQuickHelp context={helpContext} onOpenChat={()=>setPage('chatbot')}/><img className="petrusTopLogo" src={petrusLogo} alt="Petrus"/></header>
    <main className={`main${page==='chatbot'?' assistantMain':''}`}><div className={`content${page==='plc'?' plcContent':page==='chatbot'?' assistantContent':''}`}><BuildVersionNotice health={health}/>
      {page in FEATURES&&page!=='chatbot'&&<FeatureRecommendation feature={page as EngineeringFeature} projectReady={!!validation.localProjectPath||!!validation.projectFiles.length} hasResult={page==='validation'?!!validation.result:page==='compare'?!!compare.result:page==='rules'?!!ruleResults:false} failures={normalized?.counts.fail||0} warnings={normalized?.counts.warn||0}/>}
      <section className="workHubPage" hidden={page!=='home'}>
        <WorkHub active={page==='home'} renderRecentWork={historyActive=><RunHistory active={historyActive} onOpen={(kind,data)=>{if(kind==='data-model'||data.runStatus==='interrupted'||(data.runStatus==='failed'&&kind!=='datainspect')||['send-rtc','send-raw'].includes(data.operation)||(kind==='datainspect'&&!data.metadata?.length)){setHistoryDetail(data)}else if(kind==='datainspect'){setDataInspectHistoryId(data.historyId);setPage('plc')}else if(kind==='compare'){compare.openHistory(data);setPage('compare')}else if(kind==='rules'){setRuleResults(data);setPage('rules')}else{validation.openHistory(kind,data);setPage('validation')}}} onReuse={(project,kind)=>{validation.selectProject(project.projectPath,project.projectName);if(project.metadataPath)validation.selectMetadata(project.metadataPath,project.metadataPath.split(/[\\/]/).pop()||'Stored metadata');setPage(kind==='rules'?'rules':'validation');setToast('Stored project loaded. Run validation, generate metadata, or select rules using the normal controls.')}}/>}/>
      </section>
      <section hidden={page!=='validation'}>{page==='validation'&&<ToolProjectSelector tool="bytemap"/>}<ValidationPage workspace={validation} metaCols={metaCols} departments={departments}/></section>
      {page==='plc'&&<section><PLCDataPage theme={theme} setTheme={setTheme} historyId={dataInspectHistoryId} onLive={()=>setDataInspectHistoryId('')} onContext={setPLCContext}/></section>}
      <section hidden={page!=='compare'}>{page==='compare'&&<ToolProjectSelector tool="matchview"/>}<ComparePage {...compare}/></section>
      <section hidden={page!=='rules'}><RulesPage onSourceSaved={(path,name)=>{validation.adoptEditedProject(path,name);setRuleResults(null);setToast("Source saved with backup. Run the pipeline again to refresh results.")}} projectReady={!!validation.localProjectPath||!!validation.projectFiles.length} projectName={validation.projectName||''} projectPath={validation.localProjectPath||''} machineDepartment={validation.machineDepartment} onProjectSelected={(path,name,files)=>validation.selectProject(path,name,files)} onMachineDepartmentChange={validation.setMachineDepartment} departments={departments} ruleResults={ruleResults} runRules={runRules} busy={ruleBusy} revision={ruleRevision} onAssist={(result,rule)=>{setAssistFinding({result,rule,projectName:ruleResults?.projectName||validation.projectName,projectPath:ruleResults?.projectPath||validation.localProjectPath||validation.result?.projectPath||'',requestId:Date.now()});setPage('chatbot')}}/></section>
      <section hidden={page!=='chatbot'}><AssistWorkspace comparisonResult={compare.result} onOpenFeature={feature=>{if(['home','validation','compare','rules','chatbot','settings','plc','help'].includes(feature))setPage(feature as Page)}} onSourceSaved={(path,name)=>{validation.adoptEditedProject(path,name);setRuleResults(null);setToast("Source saved with backup. Run validation again.")}} finding={assistFinding} revision={ruleRevision} onSaved={rulesSaved} result={validation.result} projectPath={validation.localProjectPath||validation.result?.projectPath||ruleResults?.projectPath||''} projectFiles={validation.projectFiles} projectName={validation.projectName} machineDepartment={validation.machineDepartment} departments={departments} ruleResults={ruleResults}/></section>
      {page==='help'&&<HelpPage onOpen={feature=>{if(feature==='virtual-plc')window.location.assign('/virtual-plc/');else setPage(feature)}}/>}
      <section hidden={page!=='settings'}><SettingsPage testingProject={{path:validation.localProjectPath||validation.result?.projectPath||ruleResults?.projectPath||'',files:validation.projectFiles,name:validation.projectName,onSaved:rulesSaved}} theme={theme} setTheme={setTheme} accent={accent} setAccent={setAccent} metaCols={metaCols} setMetaCols={setMetaCols} departments={departments} machinePrefixes={machineConfig.prefixes} onMachineConfigChange={saveMachineConfig} boolMetadataMode={validation.boolMetadataMode} setBoolMetadataMode={validation.setBoolMetadataMode} localMetadataPath={validation.localMetadataPath} setLocalMetadataPath={p=>validation.selectMetadata(p,p.split(/[\\/]/).pop()||'')} localMetadataName={validation.localMetadataName} setLocalMetadataName={validation.setLocalMetadataName} onClearResults={()=>{validation.clearResults();compare.clearResults()}}/></section>
    </div></main>{historyDetail&&<HistoryResultDialog result={historyDetail} onClose={()=>setHistoryDetail(null)}/>} {toast&&<div className="toast" role="status">{toast}</div>}
  </div></TableLayoutProvider>;
}
export default App;
