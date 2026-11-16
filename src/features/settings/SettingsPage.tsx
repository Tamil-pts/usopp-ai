import {ThemeGallery} from '../../shared/ThemePicker';
import {SettingsShell} from './SettingsShell';
import {userStorage} from '../../shared/userStorage';
import React,{useEffect,useState} from 'react';
import {LayoutDashboard,FolderOpen,ArrowRightLeft,Table2,SlidersHorizontal,MessageSquare,Settings,Download,FileText,ChevronRight,Clock3,Search,Sparkles,FolderTree,FileSpreadsheet,Play,Plus,Trash2,Save,RefreshCw,ShieldCheck,Upload,CheckCircle2,AlertTriangle,AlertCircle,XCircle,Eye,GitCompare,GitCompareArrows,BookOpen,ChevronDown,Minus,X} from 'lucide-react';
import type {MetaCol} from '../../shared/types';
import {useTableLayout} from '../../shared/TableLayout';
import {DEFAULT_META_COLS} from '../validation/metadataColumns';
import {LocalFileTree} from '../../shared/LocalFileBrowser';
import {logEvent} from '../../shared/logging';
import type {BoolMetadataMode} from '../validation/api';
import {useAccount} from '../account/AuthProvider';
import {AccountSettings} from '../account/AccountSettings';
import {UserManagement} from '../account/UserManagement';
import {WorkHubConnections} from '../workhub/WorkHubConnections';
import {AssistModelSettings} from './AssistModelSettings';
import {MachineDepartmentSettings} from './MachineDepartmentSettings';
import {AdminKnowledgeTransfer} from './AdminKnowledgeTransfer';
import {DocumentBrandingSettings} from './DocumentBrandingSettings';
import {DocumentStudioSettings} from './DocumentStudioSettings';
import {EngineeringQualitySettings} from './EngineeringQualitySettings';
import type {MachinePrefix} from '../validation/projectDetails';



export function SettingsPage({theme,setTheme,accent,setAccent,metaCols,setMetaCols,onClearResults,localMetadataPath,setLocalMetadataPath,localMetadataName,setLocalMetadataName,departments,machinePrefixes,onMachineConfigChange,boolMetadataMode,setBoolMetadataMode,testingProject}:{theme:any,setTheme:any,accent:string,setAccent:any,metaCols:MetaCol[],setMetaCols:(v:MetaCol[])=>void,onClearResults:()=>void,localMetadataPath:string,setLocalMetadataPath:(s:string)=>void,localMetadataName:string;setLocalMetadataName:(s:string)=>void;departments:string[];machinePrefixes:MachinePrefix[];onMachineConfigChange:(value:{departments:string[];prefixes:MachinePrefix[]})=>Promise<void>;boolMetadataMode:BoolMetadataMode;setBoolMetadataMode:(v:BoolMetadataMode)=>void;testingProject?:{path:string;files:File[];name:string;onSaved:()=>void}}){
 const {user}=useAccount();
 const [metadataBrowserOpen,setMetadataBrowserOpen]=useState(false);
 const section=(k:string)=>['sl','plcTagCode','logicComment','gc','lt','lo','size','dropdown','hmiMin','hmiMax','valueSource','inputType'].includes(k)?'plc':'metadata';
 const move=(i:number,dir:number)=>{const indices=metaCols.map((_,n)=>n).filter(n=>section(metaCols[n].key)===section(metaCols[i].key));const at=indices.indexOf(i);const j=indices[at+dir];if(j===undefined)return;const a=[...metaCols];[a[i],a[j]]=[a[j],a[i]];setMetaCols(a)};
 const reset=()=>setMetaCols(DEFAULT_META_COLS);
 const {layout,setLayout}=useTableLayout();
 const clearCache=async()=>{try{const response=await fetch('/api/cache/clear',{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Cache clear failed');onClearResults();userStorage.removeItem('usopp_compare_base_path_v4.31');userStorage.removeItem('usopp_compare_new_path_v4.31');alert(`${data.message} Removed ${data.removed||0} temporary workspace item(s).`)}catch(error:any){alert(error.message||'Cache clear failed')}};
 return <><SettingsShell panels={{
 profile:<AccountSettings/>,
 appearance:<><div className="card setting"><h3>Appearance</h3><p>Choose a complete workspace palette. Your selection is saved with your account.</p><ThemeGallery theme={theme} onChange={setTheme}/></div> <div className="card setting"><h3>Accent</h3><p>Personal accent for Light and Dark. Retro, Classic and Monochrome use their curated palette.</p><div className="seg">{['#4f7ff2','#6b63e6','#15946b','#d08a22'].map(c=><button key={c} onClick={()=>setAccent(c)} className={'chip '+(accent===c?'active':'')} style={{color:c}}>● {c}</button>)}</div></div></>,
 users:<UserManagement/>,
 'document-studio':<DocumentStudioSettings embedded/>,
 documents:<DocumentBrandingSettings/>,
 workflow:<EngineeringQualitySettings/>,
 connections:<WorkHubConnections/>,
 assistant:<AssistModelSettings/>,
 plc:<>{user.role==='admin'&&<MachineDepartmentSettings departments={departments} prefixes={machinePrefixes} onSave={onMachineConfigChange}/>} <div className="card setting wide"><h3>PLC BOOL metadata representation</h3><p>This setting controls metadata generation and validation together. It does not change the PLC declaration.</p><div className="boolModeOptions"><button className={'boolModeOption '+(boolMetadataMode==='BOOL'?'active':'')} onClick={()=>setBoolMetadataMode('BOOL')}><strong>PLC BOOL = BOOL</strong><span>Default. Generated metadata stays BOOL. Validation requires BOOL. No conversion rows are required in Sheet2.</span></button><button className={'boolModeOption '+(boolMetadataMode==='USINT'?'active':'')} onClick={()=>setBoolMetadataMode('USINT')}><strong>PLC BOOL = USINT</strong><span>Generated metadata uses USINT. Validation requires USINT and Sheet2 mappings 0 = ON and 1 = OFF.</span></button></div><div className="boolModeCurrent">Active contract: <b>{boolMetadataMode==='BOOL'?'PLC BOOL → metadata BOOL':'PLC BOOL → metadata USINT · Sheet2 0 = ON · 1 = OFF'}</b></div></div> <div className="card setting"><h3>Metadata workbook configuration</h3><p>Select the local metadata workbook used by validation. The configured file remains on this PC.</p><div className="actions"><button className="btn primary" onClick={()=>setMetadataBrowserOpen(true)}><FolderTree size={13}/> Browse This PC</button>{localMetadataPath&&<button className="btn" onClick={()=>{setLocalMetadataPath('');setLocalMetadataName('')}}><Trash2 size={13}/> Clear</button>}</div>{localMetadataPath?<><div className="fileName">✓ {localMetadataName||'Metadata workbook'}</div><div className="localPath mono">{localMetadataPath}</div></>:<div className="mono">No local metadata workbook configured.</div>}</div></>,
 tables:<><div className="card setting"><h3>Metadata table columns</h3><p>Choose which columns appear and change their position. Extra HMI, Min/Max and Value Source fields are hidden by default.</p><div className="columnConfig">{metaCols.map((c,i)=><div className="columnRow" key={c.key}><button className="chip" disabled={c.key==='result'} onClick={()=>setMetaCols(metaCols.map((x,n)=>n===i?{...x,enabled:!x.enabled}:x))}>{c.enabled?'Shown':'Hidden'}</button><span>{c.label}</span><div className="columnMove"><button className="chip" disabled={i===0} onClick={()=>move(i,-1)}>↑</button><button className="chip" disabled={i===metaCols.length-1} onClick={()=>move(i,1)}>↓</button></div></div>)}</div><button className="btn" onClick={reset}><RefreshCw size={13}/> Reset column layout</button></div> <div className="card setting"><h3>Table layout</h3><p>Applies to all tables. Column widths recalculate when columns are shown or hidden.</p><div className="seg">{(['auto','fit','custom'] as const).map(mode=><button key={mode} className={'chip '+(layout.mode===mode?'active':'')} onClick={()=>setLayout({...layout,mode})}>{mode==='auto'?'Auto width':mode==='fit'?'Fit to window':'Custom width'}</button>)}</div>{layout.mode==='custom'&&<label className="pathLabel">Minimum column width: {layout.width}px<input type="range" min="80" max="400" step="10" value={layout.width} onChange={e=>setLayout({...layout,width:Number(e.target.value)})}/></label>}<p>Wide tables scroll horizontally. Fit to window wraps long values.</p></div></>,
 data:<><div className="card setting"><h3>Temporary workspace</h3><p>Browser-uploaded projects and session results are stored in a temporary workspace. Clear cache removes them; exported reports remain available.</p><button className="btn" onClick={()=>void clearCache()}><Trash2 size={13}/> Clear temporary workspace</button></div> {user.role==='admin'&&<AdminKnowledgeTransfer/>} <div className="card setting"><h3>Safety boundary</h3><p>Assist generates explanations and configuration only. No automatic PLC source modification.</p><div className="badge pass"><i className="dot"/> PLC auto-fix disabled</div></div> <div className="card setting"><h3>Diagnostics</h3><p>Every navigation, upload, validation, metadata generation, rule and Assist request is recorded by the backend.</p><div className="actions"><button className="btn" onClick={()=>window.open('/api/logs/today','_blank')}><FileSpreadsheet size={13}/> View today log</button></div><div className="mono">Logs folder: logs\usopp_backend_YYYYMMDD.log</div></div></>,
 }}/>
 <LocalFileTree open={metadataBrowserOpen} onClose={()=>setMetadataBrowserOpen(false)} selectedPath={localMetadataPath} onSelect={(path,name)=>{setLocalMetadataPath(path);setLocalMetadataName(name);}}/>
 </>;
}
