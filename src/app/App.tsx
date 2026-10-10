import {userStorage} from '../shared/userStorage';
import packageInfo from '../../package.json';
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
import {useAccount} from '../features/account/AuthProvider';
import {HelpPage} from '../features/help/HelpPage';
import {UserManagement} from '../features/account/UserManagement';
import {RunHistory} from '../features/history/RunHistory';
import {HistoryResultDialog} from '../features/history/HistoryResultDialog';
import {FeatureRecommendation} from '../shared/FeatureRecommendation';
import {FEATURES,type EngineeringFeature} from '../shared/features';
import '../features/help/help.css';
import {PLCDataPage} from '../features/plc/PLCDataPage';
import {RulesPage} from '../features/rules/RulesPage';
import {validateEngineeringRules} from '../features/rules/api';
import {AssistWorkspace} from '../features/assist/AssistWorkspace';
import {SettingsPage} from '../features/settings/SettingsPage';
import {DEPARTMENTS} from '../features/rules/library';
import {TableLayoutProvider} from '../shared/TableLayout';
import './responsive.css';
import usoppLogo from '../usopp_logo.png';
import petrusLogo from '../petrus_logo.png';

type Page='home'|'validation'|'compare'|'rules'|'chatbot'|'settings'|'plc'|'help';
const navigation=[{id:'home',label:'WorkHub',Icon:LayoutDashboard},{id:'validation',label:FEATURES.validation.name,Icon:ShieldCheck},{id:'plc',label:FEATURES.plc.name,Icon:Activity},{id:'compare',label:FEATURES.compare.name,Icon:GitCompare},{id:'rules',label:FEATURES.rules.name,Icon:BookOpen},{id:'chatbot',label:FEATURES.chatbot.name,Icon:MessageSquare},{id:'settings',label:'Settings',Icon:Settings},{id:'help',label:'Help',Icon:HelpCircle}] as const;
function App(){
  const {user,logout}=useAccount();
  const [page,setPage]=useState<Page>('home');
  const [manageUsers,setManageUsers]=useState(false);
  const [dataInspectHistoryId,setDataInspectHistoryId]=useState('');
  const [historyDetail,setHistoryDetail]=useState<any>(null);
  const [theme,setTheme]=useState<'light'|'dark'>(()=>userStorage.getItem('usopp_theme')==='dark'?'dark':'light');
  const [accent,setAccent]=useState(()=>userStorage.getItem('usopp_accent')||'#4f7ff2');
  const [departments,setDepartments]=useState<string[]>(()=>{try{return [...new Set([...DEPARTMENTS,...JSON.parse(userStorage.getItem('usopp_custom_departments_v1')||'[]')])]}catch{return DEPARTMENTS}});
  const [health,setHealth]=useState<any>(null);
  const [toast,setToast]=useState('');
  const [metaCols,setMetaCols]=useState<MetaCol[]>(()=>{
    try{const saved=JSON.parse(userStorage.getItem('usopp_meta_cols_v4.30')||'null');if(!Array.isArray(saved))return DEFAULT_META_COLS;
      const valid=saved.filter((c:any,i:number)=>DEFAULT_META_COLS.some(d=>d.key===c.key)&&saved.findIndex((x:any)=>x.key===c.key)===i);
      return [...valid,...DEFAULT_META_COLS.filter(d=>!valid.some((c:any)=>c.key===d.key))];
    }catch{return DEFAULT_META_COLS}
  });
  const validation=useValidationWorkspace();
  const compare=useCompareProjects(setToast);
  const [ruleResults,setRuleResults]=useState<any>(null);
  const [ruleBusy,setRuleBusy]=useState('');
  const [ruleRevision,setRuleRevision]=useState(0);
  const [assistFinding,setAssistFinding]=useState<any>(null);
  const rulesSaved=useCallback(()=>setRuleRevision(v=>v+1),[]);
  useEffect(()=>{setRuleResults(null);setAssistFinding(null)},[validation.localProjectPath,validation.projectFiles,validation.machineDepartment]);
  useEffect(()=>{document.documentElement.dataset.theme=theme;document.documentElement.style.setProperty('--accent',accent);userStorage.setItem('usopp_theme',theme);userStorage.setItem('usopp_accent',accent)},[theme,accent]);
  useEffect(()=>{userStorage.setItem('usopp_meta_cols_v4.30',JSON.stringify(metaCols))},[metaCols]);
  useEffect(()=>{let cancelled=false;const check=()=>fetch('/api/health').then(r=>{if(!r.ok)throw new Error();return r.json()}).then(j=>{if(!cancelled)setHealth(j)}).catch(()=>{if(!cancelled)setHealth(null)});void check();const id=setInterval(check,15000);return()=>{cancelled=true;clearInterval(id)}},[]);
  useEffect(()=>{if(!toast)return;const id=setTimeout(()=>setToast(''),8000);return()=>clearTimeout(id)},[toast]);
  const runRules=async(rules:any)=>{
    if(!validation.localProjectPath&&!validation.projectFiles.length){setToast('Select a project in the pipeline project box to continue.');return {error:'Select a project in the pipeline project box to continue.'}}
    setRuleBusy('rules');setRuleResults(null);try{const data={...await validateEngineeringRules({...validation,rules}),pipelineRunId:rules.pipelineRunId};setRuleResults(data);setToast('Rule validation completed.');return data}catch(e:any){setToast(e.message);return {error:e.message}}finally{setRuleBusy('')}
  };
  const normalized=validation.result?normalizeResult(validation.result):null;
  return <TableLayoutProvider><div className="app workspaceApp"><aside className="rail"><div className="brand"><img src={usoppLogo} alt="uSOPp.ai"/></div><nav className="nav railMainNav" aria-label="Main navigation">{navigation.filter(n=>n.id!=='settings'&&n.id!=='help').map(({id,label,Icon})=><button key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><Icon/><span>{label}</span></button>)}</nav><nav className="nav railUtilities" aria-label="Settings and help">{navigation.filter(n=>n.id==='settings'||n.id==='help').map(({id,label,Icon})=><button key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><Icon/><span>{label}</span></button>)}</nav></aside>
    <header className="top"><div className="crumb"><b>uSOPp.ai</b><span> / </span>{navigation.find(n=>n.id===page)?.label}</div><div className="topSpacer"/><div className="accountTop"><span title={`${user.designation} / ${user.company}`}>{user.username}</span><button className="btn" onClick={()=>{void logout().catch((error:Error)=>setToast(error.message))}}>Sign out</button></div><span className={'badge '+(health?'pass':'warn')}>{health?`UI ${packageInfo.version} | API ${health.version}`:'API unavailable — check launcher logs'}</span><img className="petrusTopLogo" src={petrusLogo} alt="Petrus"/></header>
    <main className={`main${page==='chatbot'?' assistantMain':''}`}><div className={`content${page==='plc'?' plcContent':page==='chatbot'?' assistantContent':''}`}>{health&&health.version!==packageInfo.version&&<div className="ruleMessage" role="status">The interface and server versions differ. Save any edits, then <button className="btn" onClick={()=>window.location.reload()}>Reload interface</button></div>}
      {page in FEATURES&&page!=='chatbot'&&<FeatureRecommendation feature={page as EngineeringFeature} projectReady={!!validation.localProjectPath||!!validation.projectFiles.length} hasResult={page==='validation'?!!validation.result:page==='compare'?!!compare.result:page==='rules'?!!ruleResults:false} failures={normalized?.counts.fail||0} warnings={normalized?.counts.warn||0}/>}
      <section hidden={page!=='home'}><div className="pageHead"><div><div className="eyebrow">LOCAL ENGINEERING WORKSPACE</div><h1>WorkHub</h1><p>ByteMap, DataInspect, MatchView, LogicScan and AI Assistant in one engineering workspace.</p></div></div>
        <div className="card homeProject"><h2>{validation.projectName||'No project selected'}</h2><p className="mono">{validation.localProjectPath|| (validation.projectFiles.length?`${validation.projectFiles.length} uploaded files`:'Choose your project in ByteMap to begin.')}</p><button className="btn primary" onClick={()=>setPage('validation')}>Open ByteMap</button></div>
        <div className="kpis">{[['Checks',validation.result?.totalChecks??validation.result?.summary?.totalChecks??'—'],['Passed',normalized?.counts.pass??'—'],['Warnings',normalized?.counts.warn??'—'],['Failed',normalized?.counts.fail??'—']].map(([label,value])=><div className="card kpi" key={label}><div className="label">{label}</div><div className="value">{value}</div><div className="sub">{validation.result?'Latest validation run':'Awaiting validation'}</div></div>)}</div>
        <div className="homeFeatures">{[['validation',FEATURES.validation.name,'Select a project, validate packets and metadata, and edit Excel workbook copies.'],['plc',FEATURES.plc.name,'Read and verify live PLC data with Nami V1.5.'],['compare',FEATURES.compare.name,'Review the differences between two project versions.'],['rules',FEATURES.rules.name,'Select configured rules and run engineering validation.'],['chatbot',FEATURES.chatbot.name,'Chat with Chopper, configure rules and open the KnowHub.']].map(([id,title,description])=><button className="card featureCard" key={id} onClick={()=>setPage(id as Page)}><h2>{title}</h2><p>{description}</p><span>Open →</span></button>)}</div>
        {user.role==='admin'&&<><button className="btn primary" onClick={()=>setManageUsers(value=>!value)}>{manageUsers?'Close user management':'User management'}</button>{manageUsers&&<UserManagement/>}</>}
        <RunHistory active={page==='home'} onOpen={(kind,data)=>{if(kind==='data-model'||data.runStatus==='interrupted'||(data.runStatus==='failed'&&kind!=='datainspect')||['send-rtc','send-raw'].includes(data.operation)||(kind==='datainspect'&&!data.metadata?.length)){setHistoryDetail(data)}else if(kind==='datainspect'){setDataInspectHistoryId(data.historyId);setPage('plc')}else if(kind==='compare'){compare.openHistory(data);setPage('compare')}else if(kind==='rules'){setRuleResults(data);setPage('rules')}else{validation.openHistory(kind,data);setPage('validation')}}} onReuse={(project,kind)=>{validation.selectProject(project.projectPath,project.projectName);if(project.metadataPath)validation.selectMetadata(project.metadataPath,project.metadataPath.split(/[\\/]/).pop()||'Stored metadata');setPage(kind==='rules'?'rules':'validation');setToast('Stored project loaded. Run validation, generate metadata, or select rules using the normal controls.')}}/>
      </section>
      <section hidden={page!=='validation'}><ValidationPage workspace={validation} metaCols={metaCols} departments={departments}/></section>
      {page==='plc'&&<section><PLCDataPage theme={theme} setTheme={setTheme} historyId={dataInspectHistoryId} onLive={()=>setDataInspectHistoryId('')}/></section>}
      <section hidden={page!=='compare'}><ComparePage {...compare}/></section>
      <section hidden={page!=='rules'}><RulesPage onSourceSaved={(path,name)=>{validation.adoptEditedProject(path,name);setRuleResults(null);setToast("Source saved with backup. Run the pipeline again to refresh results.")}} projectReady={!!validation.localProjectPath||!!validation.projectFiles.length} projectName={validation.projectName||''} projectPath={validation.localProjectPath||''} machineDepartment={validation.machineDepartment} onProjectSelected={(path,name,files)=>validation.selectProject(path,name,files)} onMachineDepartmentChange={validation.setMachineDepartment} departments={departments} ruleResults={ruleResults} runRules={runRules} busy={ruleBusy} revision={ruleRevision} onAssist={(result,rule)=>{setAssistFinding({result,rule,projectName:ruleResults?.projectName||validation.projectName,projectPath:ruleResults?.projectPath||validation.localProjectPath||validation.result?.projectPath||'',requestId:Date.now()});setPage('chatbot')}}/></section>
      <section hidden={page!=='chatbot'}><AssistWorkspace comparisonResult={compare.result} onOpenFeature={feature=>{if(['home','validation','compare','rules','chatbot','settings','plc','help'].includes(feature))setPage(feature as Page)}} onSourceSaved={(path,name)=>{validation.adoptEditedProject(path,name);setRuleResults(null);setToast("Source saved with backup. Run validation again.")}} finding={assistFinding} revision={ruleRevision} onSaved={rulesSaved} result={validation.result} projectPath={validation.localProjectPath||validation.result?.projectPath||ruleResults?.projectPath||''} projectFiles={validation.projectFiles} projectName={validation.projectName} machineDepartment={validation.machineDepartment} departments={departments} ruleResults={ruleResults}/></section>
      {page==='help'&&<HelpPage onOpen={setPage}/>}
      <section hidden={page!=='settings'}><SettingsPage theme={theme} setTheme={setTheme} accent={accent} setAccent={setAccent} metaCols={metaCols} setMetaCols={setMetaCols} departments={departments} onDepartmentsChange={next=>{const custom=next.filter(d=>!DEPARTMENTS.includes(d));userStorage.setItem('usopp_custom_departments_v1',JSON.stringify(custom));setDepartments(next)}} boolMetadataMode={validation.boolMetadataMode} setBoolMetadataMode={validation.setBoolMetadataMode} localMetadataPath={validation.localMetadataPath} setLocalMetadataPath={p=>validation.selectMetadata(p,p.split(/[\\/]/).pop()||'')} localMetadataName={validation.localMetadataName} setLocalMetadataName={validation.setLocalMetadataName} onClearResults={()=>{validation.clearResults();compare.clearResults()}}/></section>
    </div></main>{historyDetail&&<HistoryResultDialog result={historyDetail} onClose={()=>setHistoryDetail(null)}/>} {toast&&<div className="toast" role="status">{toast}</div>}
  </div></TableLayoutProvider>;
}
export default App;
