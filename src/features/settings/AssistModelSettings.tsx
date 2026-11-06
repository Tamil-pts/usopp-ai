import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Bot,Check,Cloud,Cpu,FolderOpen,LoaderCircle,Monitor,Plug,Power,RefreshCw,Settings2} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {apiJson} from '../rules/library';
import {LocalFileTree} from '../../shared/LocalFileBrowser';
import {copyChatText} from '../assist/chatFiles';
import './assist-model-settings.css';
import {SemanticRetrievalSettings} from './SemanticRetrievalSettings';

const MODES=[
 {id:'embedded',name:'Local CPU model',description:'Recommended · Runs on your uSOPp server',Icon:Cpu},
 {id:'local',name:'Engineering tools',description:'Validation and log decoding without AI',Icon:Settings2},
 {id:'ollama',name:'Ollama',description:'Connect an existing model service',Icon:Plug},
 {id:'api',name:'Model API',description:'Connect a compatible provider',Icon:Cloud},
];
export function AssistModelSettings(){
 const {user}=useAccount();const admin=user.role==='admin';
 const [cfg,setCfg]=useState({provider:'embedded',baseUrl:'http://127.0.0.1:8202/v1',model:'chopper-local',modelPath:'',modelFileAvailable:false,localPort:8202,contextSize:4096,cpuThreads:4,maxTokens:512,responseTimeoutSeconds:1800,autoStart:true,allowFallback:true,hasApiKey:false,localOnly:true});
 const [cpu,setCpu]=useState<any>(null),[runtime,setRuntime]=useState<any>(null);
 const [key,setKey]=useState(''),[clearKey,setClearKey]=useState(false),[models,setModels]=useState<string[]>([]);
 const [message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[browse,setBrowse]=useState(false),[dirty,setDirty]=useState(false);
 const [mcp,setMcp]=useState<any>(null),[token,setToken]=useState('');
 const installation=useRef(false);
 const refresh=()=>apiJson('/api/assist/model/runtime').then(setRuntime);
 const patch=(value:Partial<typeof cfg>)=>{setCfg(current=>({...current,...value}));setDirty(true);setMessage('')};
 useEffect(()=>{
  if(!admin)return;let active=true;
  apiJson('/api/assist/model').then(value=>{if(active)setCfg(value)}).catch(reason=>{if(active)setError(reason.message)});
  apiJson('/api/assist/mcp').then(value=>{if(active)setMcp(value)}).catch(()=>{});
  const poll=()=>apiJson('/api/assist/model/cpu').then(state=>{
   if(!active)return;setCpu(state);
   if(installation.current&&['installed','failed'].includes(state.phase)){
    installation.current=false;
    if(state.phase==='installed'){void apiJson('/api/assist/model').then(value=>{if(active){setCfg(value);setDirty(false)}});void refresh().catch(()=>{});setMessage('Local model installed. Chopper is loading; wait for Ready.')}
    else setError(state.error);
   }
  }).catch(reason=>{if(active)setError(reason.message)});
  void poll();const timer=setInterval(()=>void poll(),4000);
  return()=>{active=false;clearInterval(timer)};
 },[admin]);
 useEffect(()=>{
  if(!admin||cfg.provider!=='embedded')return;let active=true;
  const poll=()=>apiJson('/api/assist/model/runtime').then(value=>{if(active)setRuntime(value)}).catch(reason=>{if(active)setError(reason.message)});
  void poll();const timer=setInterval(()=>void poll(),5000);return()=>{active=false;clearInterval(timer)};
 },[admin,cfg.provider]);
 const setup=async(modelId='primary')=>{
  setBusy(true);setError('');try{setCpu(await apiJson('/api/assist/model/cpu/install',{modelId}));installation.current=true;setMessage('Model setup is running in the background. You can continue validation.')}catch(reason:any){setError(reason.message)}finally{setBusy(false)}
 };
 const selectModel=async(modelId:string)=>{
  setBusy(true);setError('');try{setCfg(await apiJson('/api/assist/model/cpu/select',{modelId}));setDirty(false);setRuntime(await apiJson('/api/assist/model/runtime/start',{}));setMessage('Selected model is loading. Wait for Ready.')}catch(reason:any){setError(reason.message)}finally{setBusy(false)}
 };
 const save=async(check=false)=>{
  setBusy(true);setMessage('');setError('');try{
   setCfg(await apiJson('/api/assist/model',{...cfg,apiKey:key,clearApiKey:clearKey}));setKey('');setClearKey(false);setDirty(false);
   if(check){const result=await apiJson('/api/assist/model/check',{});setModels(result.models||[]);setMessage(result.message)}else setMessage('Chopper settings saved.');
  }catch(reason:any){setError(reason.message)}finally{setBusy(false)}
 };
 const action=async(which:'start'|'stop'|'restart')=>{
  setBusy(true);setError('');setMessage('');try{
   if(which!=='stop'){
    const settings={...cfg,provider:'embedded',modelPath:cfg.modelPath||(cpu?.installed?cpu.modelPath:''),apiKey:key,clearApiKey:clearKey};
    setCfg(await apiJson('/api/assist/model',settings));setDirty(false);setKey('');setClearKey(false);
   }
   const state=await apiJson(`/api/assist/model/runtime/${which}`,{});setRuntime(state);setMessage(state.message||'Local model stopped.');
  }catch(reason:any){setError(reason.message)}finally{setBusy(false)}
 };
 const testModel=async()=>{
  setBusy(true);setError('');setMessage('Checking Chopper…');try{const result=await apiJson('/api/assist/model/check',{});setModels(result.models||[]);setMessage(result.message||'Connection check complete.');await refresh()}catch(reason:any){setMessage('');setError(reason.message)}finally{setBusy(false)}
 };
 if(!admin)return null;
 const installing=['preparing','downloading','verifying'].includes(cpu?.phase);
 const ready=runtime?.ready,running=runtime?.running,modelAvailable=cfg.modelFileAvailable||cpu?.installed||(dirty&&!!cfg.modelPath);
 const statusLabel=ready?'Ready':running?'Starting':runtime?.failed?'Needs attention':'Stopped';
 const stages=[{name:'Runtime',done:runtime?.runtimeAvailable},{name:'Model file',done:modelAvailable},{name:'Active',done:running},{name:'Ready',done:ready}];
 return <><section className="card setting assistModelSettings wide">
  <header className="modelSetupHead"><div className="modelSetupIcon"><Bot size={26}/></div><div><h3>Chopper setup</h3><p>Choose a connection. Your local CPU model is ready to activate once its file is installed.</p></div>{cfg.provider==='embedded'&&<span className={'modelState '+(ready?'ready':running?'loading':'stopped')}>{running&&!ready?<LoaderCircle size={15} className="modelSpinning"/>:<span className="modelStateDot"/>}{statusLabel}</span>}</header>
  <div className="modelModeGrid" role="group" aria-label="Chopper connection mode">{MODES.map(({id,name,description,Icon})=><button type="button" key={id} disabled={busy||installing} className={'modelMode '+(cfg.provider===id?'selected':'')} aria-pressed={cfg.provider===id} onClick={()=>patch({provider:id,...(id==='embedded'?{autoStart:true}:{}),...(id==='ollama'?{baseUrl:'http://127.0.0.1:11434',model:cfg.provider==='ollama'?cfg.model:''}:id==='api'?{baseUrl:cfg.provider==='api'?cfg.baseUrl:'',model:cfg.provider==='api'?cfg.model:''}:{})})}><Icon size={21}/><strong>{name}</strong><small>{description}</small>{cfg.provider===id&&<Check size={15} className="modelModeCheck"/>}</button>)}</div>
  <label className="modelStartup"><input type="checkbox" checked={cfg.localOnly??true} disabled={busy} onChange={event=>patch({localOnly:event.target.checked})}/><span><b>Local-only model connections</b><small>Enforce loopback model endpoints and bypass system proxies for local requests. Changing this setting requires saving.</small></span></label>
  {cfg.provider==='embedded'?<>
   <div className="modelConnectionFlow" aria-label="Browser connects to uSOPp server, which runs the local CPU model"><span><Monitor size={20}/><b>Your browser</b></span><ArrowRight size={18}/><span><Bot size={20}/><b>uSOPp server</b></span><ArrowRight size={18}/><span><Cpu size={20}/><b>Local CPU model</b></span></div>
   <ol className="modelSetupStages">{stages.map((stage,index)=><li key={stage.name} className={stage.done?'complete':''}><span>{stage.done?<Check size={15}/>:index+1}</span>{stage.name}</li>)}</ol>
   <div className="modelActivation"><div><b>{cpu?.models?.find((item:any)=>item.modelPath===cfg.modelPath)?.model.name||cpu?.model?.name||'Qwen2.5-Coder 3B Instruct · CPU'}</b><p>{ready?'Chopper is available to all signed-in users.':running?'Loading the model. Engineering validation remains available.':modelAvailable?'Activate the installed model to answer engineering questions.':'Set up the CPU model once, or select your own GGUF under Advanced settings.'}</p><small>One-time setup: 2.10 GB; 1.5B fallback retained · CPU runtime included · No Ollama service required.</small></div><div className="actions">{modelAvailable?<button className="btn primary" disabled={busy||installing||(running&&!dirty)} onClick={()=>void action(running?'restart':'start')}><Power size={16}/>{ready&&!dirty?'Chopper active':running&&!dirty?'Loading…':'Activate local Chopper'}</button>:<button className="btn primary" disabled={busy||installing} onClick={()=>void setup()}><Cpu size={16}/>{installing?'Setting up…':'Set up local Chopper'}</button>}</div></div>
   {installing&&<div className="modelInstallProgress" role="status"><progress max={100} value={cpu.phase==='downloading'?cpu.percent:undefined}/><span>{cpu.phase==='downloading'?`Downloading ${cpu.percent}%`:cpu.phase==='verifying'?'Verifying model file…':'Preparing setup…'}</span></div>}
   {cpu?.error&&<p className="failText" role="alert">{cpu.error}</p>}
   <div className="modelCpuChoices">{cpu?.models?.map((item:any)=><div key={item.choice}><b>{item.model.name}</b><small>{item.model.license} · {(item.model.size/1e9).toFixed(2)} GB · {item.installed?'Installed':'Not installed'}</small><button className="btn" disabled={busy||installing||!item.installed} onClick={()=>void selectModel(item.choice)}>Use {item.choice==='primary'?'3B primary':'1.5B fallback'}</button>{!item.installed&&<button className="btn" disabled={busy||installing} onClick={()=>void setup(item.choice)}>Install {item.choice==='primary'?'3B':'1.5B'}</button>}</div>)}</div>
   <label className="modelStartup"><input type="checkbox" checked={cfg.allowFallback??true} onChange={event=>patch({allowFallback:event.target.checked})}/><span><b>Use installed 1.5B if the primary cannot start</b><small>Only one model runs at a time. No download occurs during startup.</small></span></label>
   {runtime&&<p>{runtime.modelName||'No model running'} · {runtime.ramMB==null?'RAM —':`${runtime.ramMB} MB RAM`} · {runtime.contextLimit||cfg.contextSize} context tokens{runtime.responseSeconds!=null?` · Last answer ${runtime.responseSeconds}s`:''}{runtime.fallbackReason?` · ${runtime.fallbackReason}`:''}</p>}
   {!runtime?.runtimeAvailable&&runtime&&<p className="failText">The local runtime is missing. Install the complete application package.</p>}
   <label className="modelStartup"><input type="checkbox" disabled={busy} checked={cfg.autoStart} onChange={event=>patch({autoStart:event.target.checked})}/><span><b>Start with the server</b><small>Load this model automatically when uSOPp starts.</small></span></label>
   <div className="actions modelRuntimeActions"><button className="btn" disabled={busy||!ready||dirty} onClick={()=>void testModel()}>Check connection</button><button className="btn" disabled={busy||!running} onClick={()=>void action('restart')}><RefreshCw size={15}/>Restart</button><button className="btn" disabled={busy||!running} onClick={()=>void action('stop')}>Stop</button><button className="btn" disabled={busy} onClick={()=>void refresh().catch(reason=>setError(reason.message))}>Refresh status</button></div>
  </>:cfg.provider==='local'?<div className="modelToolsNotice"><Settings2 size={25}/><div><b>Engineering tools</b><p>Validation, metadata generation and local log decoding work without a model. Chopper also provides workflow guides.</p></div></div>:<div className="assistExternalFields"><label>Service base URL<input className="textInput" disabled={busy} value={cfg.baseUrl} onChange={event=>patch({baseUrl:event.target.value})} placeholder={cfg.provider==='ollama'?'http://127.0.0.1:11434':'https://your-provider/v1'}/></label><label>Model name<input className="textInput" list="chopperModels" disabled={busy} value={cfg.model} onChange={event=>patch({model:event.target.value})}/><datalist id="chopperModels">{models.map(model=><option key={model} value={model}/>)}</datalist></label>{cfg.provider==='api'&&<label>API key<input className="textInput" type="password" autoComplete="new-password" disabled={busy} value={key} onChange={event=>{setKey(event.target.value);setDirty(true)}} placeholder={cfg.hasApiKey?'Saved; leave blank to keep it':'Optional for a local API'}/>{cfg.hasApiKey&&<span><input type="checkbox" checked={clearKey} onChange={event=>{setClearKey(event.target.checked);setDirty(true)}}/> Remove saved key</span>}</label>}<small>Use the service address reachable from the uSOPp server.</small></div>}
  <details className="modelAdvanced"><summary><Settings2 size={16}/> Advanced settings</summary>
   {cfg.provider==='embedded'&&<><label>GGUF file on the server<input className="textInput" disabled={busy} value={cfg.modelPath} onChange={event=>patch({modelPath:event.target.value})}/></label><button className="btn" disabled={busy} onClick={()=>setBrowse(true)}><FolderOpen size={15}/>Browse server files</button><div className="assistModelControls"><label>Model port<input className="textInput" type="number" min={8200} max={8500} disabled={busy} value={cfg.localPort} onChange={event=>patch({localPort:Number(event.target.value)})}/></label><label>Context tokens<input className="textInput" type="number" min={512} max={32768} disabled={busy} value={cfg.contextSize} onChange={event=>patch({contextSize:Number(event.target.value)})}/></label><label>CPU threads<input className="textInput" type="number" min={1} max={64} disabled={busy} value={cfg.cpuThreads} onChange={event=>patch({cpuThreads:Number(event.target.value)})}/></label><label>Answer tokens<input className="textInput" type="number" min={64} max={2048} step={64} disabled={busy} value={cfg.maxTokens} onChange={event=>patch({maxTokens:Number(event.target.value)})}/></label></div></>}
   {cfg.provider!=='local'&&<label>Response timeout (minutes)<input className="textInput" type="number" min={0.5} max={30} step={0.5} disabled={busy} value={cfg.responseTimeoutSeconds/60} onChange={event=>patch({responseTimeoutSeconds:Math.round(Number(event.target.value)*60)})}/><small>Includes CPU queue time and answer generation.</small></label>}
   {runtime?.logFile&&<p>Runtime log: <code>{runtime.logFile}</code></p>}
   {cfg.provider==='embedded'&&!installing&&<button className="btn" disabled={busy} onClick={()=>void setup()}>{cpu?.installed?'Verify and use the bundled CPU model':'Install the bundled CPU model'}</button>}
  </details>
  <footer className="modelSaveBar"><span>{dirty?'Unsaved changes':cfg.provider==='embedded'&&runtime?.ready?'Connected to local Chopper':'Settings saved on this server'}</span><div className="actions"><button className="btn primary" disabled={busy||installing} onClick={()=>void save()}>Save settings</button>{!['local','embedded'].includes(cfg.provider)&&<button className="btn" disabled={busy} onClick={()=>void save(true)}>Save & check</button>}</div></footer>
  {message&&<p className="modelFeedback" role="status">{message}</p>}{error&&<p className="failText" role="alert">{error}</p>}
  <SemanticRetrievalSettings/>
  <LocalFileTree open={browse} onClose={()=>setBrowse(false)} allowedExts={['.gguf']} selectedPath={cfg.modelPath} onSelect={path=>patch({modelPath:path})}/>
 </section><details className="card setting modelMcp"><summary>Advanced integration · Chopper MCP tools</summary><p>Connect an MCP client to this application to inspect sources, prepare rule drafts and run engineering tools.</p><p>Endpoint: <code>{mcp?.endpoint||'Loading…'}</code></p><small>{mcp?.protocol}</small><div className="actions"><button className="btn" disabled={busy} onClick={()=>{setError('');apiJson('/api/assist/mcp/token',{}).then(result=>{setToken(result.token);setMessage(`MCP token created for ${Math.round(result.expiresInSeconds/3600)} hours.`)}).catch(reason=>setError(reason.message))}}>Create access token</button>{token&&<><button className="btn" onClick={()=>void copyChatText(token).then(()=>setMessage('Token copied.')).catch(reason=>setError(reason.message))}>Copy token</button><button className="btn" onClick={()=>void apiJson('/api/assist/mcp/revoke',{token}).then(()=>{setToken('');setMessage('Token revoked.')}).catch(reason=>setError(reason.message))}>Revoke token</button></>}</div></details></>;
}
