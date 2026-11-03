import {ToolProjectSelector} from '../shared/ToolProjectSelector';
import {ChopperQuickHelp} from '../features/assist/ChopperQuickHelp';
import {flushQualityDraft} from '../features/workhub/quality/bridge';
import {userStorage} from '../shared/userStorage';
import {BuildVersionNotice} from '../shared/BuildStatus';
import {useCallback,useEffect,useRef,useState} from 'react';
import '../styles.css';
import './workspace.css';
import type {MetaCol} from '../shared/types';
import {DEFAULT_META_COLS} from '../features/validation/metadataColumns';
import {ValidationPage} from '../features/validation/ValidationPage';
import {useValidationWorkspace} from '../features/validation/useValidationWorkspace';
import {ComparePage} from '../features/compare/ComparePage';
import {VirtualElectrical} from '../features/electrical/VirtualElectrical';
import {EDesignWorkspace} from '../features/edesign/EDesignWorkspace';
import {useCompareProjects} from '../features/compare/useCompareProjects';
import {useAccount} from '../features/account/AuthProvider';
import {HelpPage} from '../features/help/HelpPage';
import {RunHistory} from '../features/history/RunHistory';
import {HistoryResultDialog} from '../features/history/HistoryResultDialog';
import {WorkHub} from '../features/workhub/WorkHub';
import '../features/help/help.css';
import {PLCDataPage} from '../features/plc/PLCDataPage';
import {RulesPage} from '../features/rules/RulesPage';
import {validateEngineeringRules} from '../features/rules/api';
import {AssistWorkspace} from '../features/assist/AssistWorkspace';
import {SettingsPage} from '../features/settings/SettingsPage';
import {DEPARTMENTS} from '../features/rules/library';
import {DEFAULT_MACHINE_PREFIXES,type MachinePrefix} from '../features/validation/projectDetails';
import {TableLayoutProvider} from '../shared/TableLayout';
import './responsive.css';
import {WorkspaceTopBar} from '../shared/WorkspaceTopBar';
import {ShieldAlert} from 'lucide-react';
import {WorkspaceNavigation,WORKSPACE_NAVIGATION as navigation,type WorkspacePage as Page,type AssistTab} from '../shared/WorkspaceNavigation';
import {PAGE_MODULES,visibleModules} from '../shared/workspaceModules';

function App(){
  const {user,logout}=useAccount();
  const [page,setPageRaw]=useState<Page>('home');
  const [assistTabRequest,setAssistTabRequest]=useState<{tab:AssistTab;id:number}>();
  const modules=visibleModules(user),modulesRef=useRef(modules);modulesRef.current=modules;
  const setPage=(next:Page)=>{const module=PAGE_MODULES[next as keyof typeof PAGE_MODULES];if(module&&!modulesRef.current.includes(module)){setToast('This module is hidden for your account.');return}if(next!=='settings'&&window.location.hash.startsWith('#settings/'))history.replaceState(null,'',window.location.pathname+window.location.search);setPageRaw(next)};
  useEffect(()=>{const module=PAGE_MODULES[page as keyof typeof PAGE_MODULES];if(module&&!modules.includes(module)){const fallback=Object.entries(PAGE_MODULES).find(([,value])=>modules.includes(value))?.[0] as Page|undefined;setPageRaw(fallback||'settings')}},[page,modules.join('|')]);
  useEffect(()=>{const open=()=>{if(window.location.hash.startsWith('#e-design/'))setPage('edesign');else if(window.location.hash.startsWith('#settings/'))setPage('settings');};open();window.addEventListener('hashchange',open);return()=>window.removeEventListener('hashchange',open);},[]);
  useEffect(()=>{const open=()=>{setPage('help');setTimeout(()=>document.getElementById('help-frd-sample')?.scrollIntoView({behavior:'smooth'}),250);};window.addEventListener('workhub-help-frd',open);return()=>window.removeEventListener('workhub-help-frd',open);},[]);
  useEffect(()=>{
    const openSettings=()=>{setPage('settings');window.dispatchEvent(new CustomEvent('usopp-open-settings-section',{detail:'connections'}));};
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
  return <TableLayoutProvider><div className="app workspaceApp" data-workspace-modules={modules.join(',')}><WorkspaceNavigation page={page} projectLink={page==='validation'?<ToolProjectSelector key="bytemap" tool="bytemap" compact/>:page==='compare'||page==='circuit'?<ToolProjectSelector key="matchview" tool="matchview" compact/>:page==='plc'?<div id="datainspect-project-link"/>:undefined} onSelect={(target,tab)=>{setPage(target);if(tab)setAssistTabRequest({tab,id:Date.now()})}}/>
    <WorkspaceTopBar assistant={modules.includes('assistant')?<ChopperQuickHelp placement="top" context={{page,label:navigation.find(n=>n.id===page)?.label||'Workspace',projectName:page==='compare'?compare.newProjectInfo?.project_name||compare.result?.newName:page==='validation'||page==='rules'||page==='chatbot'?validation.projectName:undefined,projectPath:page==='compare'?compare.compareNewPath:page==='validation'||page==='rules'||page==='chatbot'?validation.localProjectPath||validation.result?.projectPath||ruleResults?.projectPath:undefined,details:page==='plc'?plcContext:{machineDepartment:validation.machineDepartment,hasValidationResult:!!validation.result,hasComparison:!!compare.result}}} onOpenChat={()=>{setPage('chatbot');setAssistTabRequest({tab:'chat',id:Date.now()});}}/>:undefined} user={user} page={navigation.find(n=>n.id===page)?.label||'Workspace'} theme={theme} health={health} onTheme={()=>setTheme(theme==='light'?'dark':'light')} onProfile={()=>{setPage('settings');window.dispatchEvent(new CustomEvent('usopp-open-settings-section',{detail:'profile'}));}} onLogout={async()=>{await flushQualityDraft();await logout();}} onNotification={(project,item)=>{setPage('home');window.dispatchEvent(new CustomEvent('workhub-open-project',{detail:{project,item}}));}}/>
    <main className={`main${page==='chatbot'?' assistantMain':''}`}><div className={`content${page==='plc'?' plcContent':page==='chatbot'?' assistantContent':''}`}><BuildVersionNotice health={health}/>{user.passwordChangeRequired&&<div className="adminCredentialNotice" role="alert"><ShieldAlert size={18}/><span><strong>Change the initial administrator password.</strong> Choose a private password before sharing this server.</span><button className="btn" onClick={()=>{setPage('settings');window.dispatchEvent(new CustomEvent('usopp-open-settings-section',{detail:'profile'}));}}>Change password</button></div>}
      <section className="workHubPage" hidden={page!=='home'}>
        <WorkHub active={page==='home'} renderRecentWork={historyActive=><RunHistory active={historyActive} onOpen={(kind,data)=>{if(kind==='data-model'||data.runStatus==='interrupted'||(data.runStatus==='failed'&&kind!=='datainspect')||['send-rtc','send-raw'].includes(data.operation)||(kind==='datainspect'&&!data.metadata?.length)){setHistoryDetail(data)}else if(kind==='datainspect'){setDataInspectHistoryId(data.historyId);setPage('plc')}else if(kind==='compare'){compare.openHistory(data);setPage('compare')}else if(kind==='rules'){setRuleResults(data);setPage('rules')}else{validation.openHistory(kind,data);setPage('validation')}}} onReuse={(project,kind)=>{validation.selectProject(project.projectPath,project.projectName);if(project.metadataPath)validation.selectMetadata(project.metadataPath,project.metadataPath.split(/[\\/]/).pop()||'Stored metadata');setPage(kind==='rules'?'rules':'validation');setToast('Stored project loaded. Run validation, generate metadata, or select rules using the normal controls.')}}/>}/>
      </section>
      <section hidden={page!=='validation'}><ValidationPage workspace={validation} metaCols={metaCols} departments={departments}/></section>
      {page==='plc'&&<section><PLCDataPage key={dataInspectHistoryId} theme={theme} historyId={dataInspectHistoryId} onLive={()=>setDataInspectHistoryId('')} onContext={setPLCContext}/></section>}
      <section hidden={page!=='compare'&&page!=='circuit'}><ComparePage {...compare} type={page==='circuit'?'circuit':'plc'}/></section>
      {page==='electrical'&&<VirtualElectrical/>}
      <section hidden={page!=='edesign'}><EDesignWorkspace active={page==='edesign'}/></section>
      <section hidden={page!=='rules'}><RulesPage onSourceSaved={(path,name)=>{validation.adoptEditedProject(path,name);setRuleResults(null);setToast("Source saved with backup. Run the pipeline again to refresh results.")}} projectReady={!!validation.localProjectPath||!!validation.projectFiles.length} projectName={validation.projectName||''} projectPath={validation.localProjectPath||''} machineDepartment={validation.machineDepartment} onProjectSelected={(path,name,files)=>validation.selectProject(path,name,files)} onMachineDepartmentChange={validation.setMachineDepartment} departments={departments} ruleResults={ruleResults} runRules={runRules} busy={ruleBusy} revision={ruleRevision} onAssist={(result,rule)=>{setAssistFinding({result,rule,projectName:ruleResults?.projectName||validation.projectName,projectPath:ruleResults?.projectPath||validation.localProjectPath||validation.result?.projectPath||'',requestId:Date.now()});setPage('chatbot')}}/></section>
      <section hidden={page!=='chatbot'}><AssistWorkspace requestedTab={assistTabRequest} comparisonResult={compare.result} onOpenFeature={feature=>{if(['home','validation','compare','rules','chatbot','settings','plc','help'].includes(feature))setPage(feature as Page)}} onSourceSaved={(path,name)=>{validation.adoptEditedProject(path,name);setRuleResults(null);setToast("Source saved with backup. Run validation again.")}} finding={assistFinding} revision={ruleRevision} onSaved={rulesSaved} result={validation.result} projectPath={validation.localProjectPath||validation.result?.projectPath||ruleResults?.projectPath||''} projectFiles={validation.projectFiles} projectName={validation.projectName} machineDepartment={validation.machineDepartment} departments={departments} ruleResults={ruleResults}/></section>
      {page==='help'&&<HelpPage onOpen={feature=>{if(feature==='virtual-plc'){if(modulesRef.current.includes('virtual_plc'))window.location.assign('/virtual-plc/');else setToast('This module is hidden for your account.')}else setPage(feature)}}/>}
      <section hidden={page!=='settings'}><SettingsPage testingProject={{path:validation.localProjectPath||validation.result?.projectPath||ruleResults?.projectPath||'',files:validation.projectFiles,name:validation.projectName,onSaved:rulesSaved}} theme={theme} setTheme={setTheme} accent={accent} setAccent={setAccent} metaCols={metaCols} setMetaCols={setMetaCols} departments={departments} machinePrefixes={machineConfig.prefixes} onMachineConfigChange={saveMachineConfig} boolMetadataMode={validation.boolMetadataMode} setBoolMetadataMode={validation.setBoolMetadataMode} localMetadataPath={validation.localMetadataPath} setLocalMetadataPath={p=>validation.selectMetadata(p,p.split(/[\\/]/).pop()||'')} localMetadataName={validation.localMetadataName} setLocalMetadataName={validation.setLocalMetadataName} onClearResults={()=>{validation.clearResults();compare.clearResults()}}/></section>
    </div></main>{historyDetail&&<HistoryResultDialog result={historyDetail} onClose={()=>setHistoryDetail(null)}/>} {toast&&<div className="toast" role="status">{toast}</div>}
  </div></TableLayoutProvider>;
}
export default App;
