import {useEffect,useRef,useState} from 'react';
import {Check,Code2,Copy,Download,FileCode2,LoaderCircle,RefreshCw} from 'lucide-react';
import type {ValidationWorkspace} from './useValidationWorkspace';
import {stageBrowserProject} from './api';
import {copyChatText} from '../assist/chatFiles';
import './write-st.css';

type Hmi={id:string;page:string;control:string;displayMin:string|null;displayMax:string|null;min:string|null;max:string|null;minDatapoint:string|null;maxDatapoint:string|null;scale:string;datasource:string;unitSource?:string;issues:string[]};
type Field={id:string;index:number;size:number;type:string;description:string;readVariable:string;destinations:string[];sourceAssignments:string[];writable:boolean;temporary:string;line:number;writeOffsets:number[];errorPositions:number[];hmiOptions:Hmi[];hmiId:string;min:string|null;max:string|null;sourceChecks:string[];paths:{offset:number;errorPosition:number;when:string}[]};
type Group={code:number;description:string;readLine:number;writeLine:number|null;payloadVariants:number[];readPayloadVariants:number[];legacyPayloadVariants:number[];machineConditions:string[];warnings:string[];issues:string[];fields:Field[]};
type Discovery={readSources:string[];writeSources:string[];hmiTargets:string[];hmiTarget:string;activeConfiguration:string|null};
type Analysis=Discovery&{readSource:string;writeSource:string;fingerprint:string;projectName:string;groups:Group[];notes:string[]};
type Draft={files:{name:string;text:string}[];groups:number[];reviewedFields:number;bundleName:string;bundleBase64:string};
type Review={hmiId?:string;min?:string;max?:string};

async function request(action:string,body:unknown,signal:AbortSignal){
 const response=await fetch('/api/spinconnect/write-st/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'The write ST request could not be completed.');return data;
}
function download(name:string,body:BlobPart,type='text/plain;charset=utf-8'){
 const url=URL.createObjectURL(new Blob([body],{type})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function WriteSTGenerator({workspace:w}:{workspace:ValidationWorkspace}){
 const [discovery,setDiscovery]=useState<Discovery|null>(null),[analysis,setAnalysis]=useState<Analysis|null>(null);
 const [readSource,setReadSource]=useState(''),[writeSource,setWriteSource]=useState(''),[target,setTarget]=useState(''),[projectPath,setProjectPath]=useState('');
 const [groups,setGroups]=useState<number[]>([]),[focus,setFocus]=useState(130),[fields,setFields]=useState<Record<string,Review>>({});
 const [jumpToField,setJumpToField]=useState('');
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[reviewed,setReviewed]=useState(false),[draft,setDraft]=useState<Draft|null>(null),[file,setFile]=useState('');
 const turn=useRef(0),controller=useRef<AbortController|null>(null),lock=useRef(false);
 const output=useRef<HTMLElement|null>(null),reviewConfirmation=useRef<HTMLInputElement|null>(null);
 useEffect(()=>{if(draft)output.current?.scrollIntoView?.({behavior:'smooth',block:'start'})},[draft]);
 useEffect(()=>{if(jumpToField){const row=document.getElementById('write-st-field-'+jumpToField);row?.scrollIntoView?.({behavior:'smooth',block:'center'});row?.querySelector('select')?.focus();setJumpToField('')}},[jumpToField,focus]);
 useEffect(()=>{turn.current++;controller.current?.abort();lock.current=false;setBusy('');setDiscovery(null);setAnalysis(null);setDraft(null);setFields({});setGroups([]);setTarget('');setReadSource('');setWriteSource('');setProjectPath('');setError('');setNotice('');setReviewed(false);return()=>{turn.current++;controller.current?.abort()}},[w.localProjectPath,w.projectFiles]);
 const invalidate=()=>{setDraft(null);setReviewed(false);setNotice('');setError('')};
 const scan=async()=>{
  if(lock.current)return;lock.current=true;setBusy('analyze');setError('');setNotice('Reading SpinConnect sources and HMI settings…');setAnalysis(null);setDraft(null);setReviewed(false);setFields({});
  const current=++turn.current,abort=new AbortController();controller.current=abort;
  try{
   const root=w.localProjectPath||(await stageBrowserProject({projectFiles:w.projectFiles,projectName:w.projectName},(done,total)=>{if(current===turn.current)setNotice(`Uploading project: ${done.toLocaleString()} / ${total.toLocaleString()} files`)})).projectPath;
   if(current!==turn.current)return;setProjectPath(root);
   const choices:Discovery=await request('discover',{project_path:root},abort.signal);
   if(current!==turn.current)return;setDiscovery(choices);
   const r=choices.readSources.includes(readSource)?readSource:choices.readSources.length===1?choices.readSources[0]:'';
   const wr=choices.writeSources.includes(writeSource)?writeSource:choices.writeSources.length===1?choices.writeSources[0]:'';
   const hmi=choices.hmiTargets.includes(target)?target:choices.hmiTarget||(choices.hmiTargets.length===1?choices.hmiTargets[0]:'');
   setReadSource(r);setWriteSource(wr);setTarget(hmi);
   if(!r||!wr)throw new Error('Select mms_nw_r for group codes and packet layout, and mms_nw_w for the transport and setting-write policies, then analyze again.');
   if(!hmi)throw new Error('Select one HMI target, then analyze again. Limits from different screens are kept separate.');
   const data:Analysis=await request('analyze',{project_path:root,readSource:r,writeSource:wr,hmiTarget:hmi},abort.signal);
   if(current!==turn.current)return;setAnalysis(data);
   const defaults=data.groups.filter(g=>!g.issues.length&&[130,140].includes(g.code)).map(g=>g.code);
   const selected=defaults.length?defaults:data.groups.filter(g=>!g.issues.length).slice(0,1).map(g=>g.code);
   setGroups(selected);setFocus(selected[0]||data.groups[0]?.code||130);setNotice(`${data.groups.length} groups found in mms_nw_r; ${data.groups.filter(g=>!g.issues.length).length} have compatible setting-write policies. Review the selected groups and limits below.`);
  }catch(reason){if(current===turn.current&&!abort.signal.aborted)setError(reason instanceof Error?reason.message:'Source analysis failed.')}
  finally{if(current===turn.current){setBusy('');lock.current=false}}
 };
 const generate=async()=>{
  if(lock.current)return;
  if(!analysis){await scan();return}
  if(!groups.length){setError('Select at least one compatible group before generating ST.');return}
  if(pendingControls.length){setError('Choose the HMI input controls listed under Required choices before generating ST.');setFocus(pendingControls[0].groupCode);setJumpToField(pendingControls[0].field.id);return}
  if(!reviewed){setError('Confirm that you reviewed the selected groups, HMI limits and machine conditions, then choose Generate ST.');reviewConfirmation.current?.focus();return}
  lock.current=true;setBusy('generate');setError('');setNotice('Generating the complete write ST draft…');setDraft(null);
  const current=++turn.current,abort=new AbortController();controller.current=abort;
  try{
   const output:Draft=await request('generate',{project_path:projectPath,readSource:analysis.readSource,writeSource:analysis.writeSource,hmiTarget:analysis.hmiTarget,fingerprint:analysis.fingerprint,groups,fields,reviewed},abort.signal);
   if(current!==turn.current)return;setDraft(output);setFile(output.files[0]?.name||'');setNotice(`Draft ready: ${output.files.length} files. Review and copy the ST or download the complete bundle.`);
  }catch(reason){if(current===turn.current&&!abort.signal.aborted)setError(reason instanceof Error?reason.message:'Code generation failed.')}
  finally{if(current===turn.current){setBusy('');lock.current=false}}
 };
 const edit=(id:string,value:Review)=>{invalidate();setFields(current=>({...current,[id]:{...current[id],...value}}))};
 const group=analysis?.groups.find(g=>g.code===focus),selectedFile=draft?.files.find(item=>item.name===file);
 const pendingControls=(analysis?.groups||[]).filter(g=>groups.includes(g.code)).flatMap(g=>g.fields.filter(f=>f.writable&&f.hmiOptions.length&&!f.hmiOptions.some(h=>h.id===(fields[f.id]?.hmiId??f.hmiId))).map(f=>({groupCode:g.code,field:f})));
 const bundle=()=>{if(!draft)return;const bytes=Uint8Array.from(atob(draft.bundleBase64),c=>c.charCodeAt(0));download(draft.bundleName,bytes,'application/zip')};
 const sourceSettingsChanged=(setter:(v:string)=>void,value:string)=>{setter(value);invalidate();setAnalysis(null);setFields({})};
 return <section className="writeST card" aria-labelledby="write-st-title">
  <header className="writeSTHeading"><span className="writeSTIcon"><Code2 size={26}/></span><div><h2 id="write-st-title">SpinConnect · Write ST generator</h2><p>Use mms_nw_r group codes and packet bytes to generate a settings writer, with the existing mms_nw_w assignments, interlocks and HMI limits.</p></div><div className="actions writeSTActions">{discovery&&<button className="btn" disabled={!!busy||!!w.busy} onClick={()=>void scan()}><RefreshCw size={16}/>{' '}Analyze again</button>}<button className="btn primary" aria-busy={!!busy} disabled={!!busy||!!w.busy||(!w.localProjectPath&&!w.projectFiles.length)} onClick={()=>void generate()}>{busy?<LoaderCircle size={16} className="spin"/>:<Code2 size={16}/>} {busy==='analyze'?'Analyzing project…':busy==='generate'?'Generating ST…':'Generate ST'}</button></div></header>
  <ol className="writeSTSteps"><li><b>1. Analyze</b><span>Choose the project and HMI target.</span></li><li><b>2. Review</b><span>Check groups, PLC units and interlocks.</span></li><li><b>3. Generate</b><span>Copy ST and its declarations.</span></li><li><b>4. Integrate</b><span>Compile, read settings, write and read back.</span></li></ol>
  {discovery&&<div className="writeSTSelectors"><label>Read routine<select className="textInput" disabled={!!busy} value={readSource} onChange={e=>sourceSettingsChanged(setReadSource,e.target.value)}><option value="">Choose mms_nw_r source</option>{discovery.readSources.map(p=><option key={p}>{p}</option>)}</select></label><label>Write routine<select className="textInput" disabled={!!busy} value={writeSource} onChange={e=>sourceSettingsChanged(setWriteSource,e.target.value)}><option value="">Choose mms_nw_w source</option>{discovery.writeSources.map(p=><option key={p}>{p}</option>)}</select></label><label>HMI target<select className="textInput" disabled={!!busy} value={target} onChange={e=>sourceSettingsChanged(setTarget,e.target.value)}><option value="">Choose one HMI target</option>{discovery.hmiTargets.map(p=><option key={p}>{p}</option>)}</select></label></div>}
  {notice&&<p className="writeSTNotice" role="status">{notice}</p>}{error&&<p className="writeSTError" role="alert">{error}</p>}
  {!analysis&&!busy&&<div className="writeSTEmpty"><FileCode2 size={34}/><h3>{w.localProjectPath||w.projectFiles.length?'Project selected — choose Generate ST':'Select a project to begin'}</h3><p>Generate ST first analyzes this project. Review the group mappings and HMI limits, confirm the review below, then choose Generate ST again to create the files.</p></div>}
  {analysis&&<>
   <div className="writeSTContext"><span>Configuration <b>{analysis.activeConfiguration||'Not recorded'}</b></span><span>HMI <b>{analysis.hmiTarget}</b></span><span>Read <code>{analysis.readSource}</code></span><span>Write <code>{analysis.writeSource}</code></span></div>
   {!!pendingControls.length&&<div className="writeSTRequired" role="status"><strong>Required choices ({pendingControls.length})</strong><p>These parameters have multiple HMI input controls. Select the control that applies to this machine configuration.</p>{pendingControls.map(({groupCode,field})=><button className="btn" key={field.id} onClick={()=>{setFocus(groupCode);setJumpToField(field.id)}}>GC {groupCode} · field {field.index}: {field.destinations[0]||field.description}</button>)}</div>}
   <p className="muted">Groups and field order below come from <code>mms_nw_r</code>. Inspect an unavailable group to see its missing setting policy or byte-layout finding.</p>
   <div className="writeSTGroups" aria-label="Groups from mms_nw_r">{analysis.groups.map(g=><label key={g.code} className={groups.includes(g.code)?'selected':''}><input type="checkbox" checked={groups.includes(g.code)} disabled={!!busy||!!g.issues.length} onChange={event=>{invalidate();setGroups(current=>event.target.checked?[...current,g.code]:current.filter(code=>code!==g.code));setFocus(g.code)}}/><span><b>GC {g.code}</b><small>{g.description}</small></span><button className="btn" disabled={!!busy} onClick={()=>setFocus(g.code)}>Inspect{g.issues.length?` · ${g.issues.length} findings`:''}</button></label>)}</div>
   {group&&<div className="writeSTMapping"><div className="widgetHead"><div><h3>GC {group.code} · {group.description}</h3><p>Packet layout from <code>mms_nw_r</code>: <b>{group.payloadVariants.join(' / ')||'Unresolved'} bytes</b>. Function 1 response adds 7 bytes; function 2 request adds 9 bytes.</p>{!!group.legacyPayloadVariants.length&&<p>Existing setting-policy frame: {group.legacyPayloadVariants.join(' / ')} bytes. The generated adapter handles this difference inside the PLC.</p>}</div><span className="badge">{group.fields.length} source fields</span></div>
    {!!group.machineConditions.length&&<p className="writeSTInterlock">Machine condition retained: <code>{group.machineConditions.join(' · ')}</code></p>}
    {group.issues.map((issue,index)=><p className="writeSTError" key={index}>{issue}</p>)}
    {!!group.warnings.length&&<details className="writeSTFindings" open><summary>Layout notes to review ({group.warnings.length})</summary><ul>{group.warnings.map((issue,index)=><li key={index}>{issue}</li>)}</ul></details>}
    <div className="tableWrap"><table className="writeSTTable"><thead><tr><th>Field / PLC destination</th><th>Wire type</th><th>Write byte(s)</th><th>HMI control</th><th>Minimum · PLC units</th><th>Maximum · PLC units</th><th>Source checks</th></tr></thead><tbody>{group.fields.map(field=>{
     const review=fields[field.id]||{},chosen=field.hmiOptions.find(h=>h.id===(review.hmiId??field.hmiId));
     return <tr id={'write-st-field-'+field.id} key={field.id}><td><b>{field.index}. {field.description}</b><code>{field.destinations.join(', ')||field.readVariable||field.temporary}</code><span className={'badge '+(field.writable?'pass':'')}>{field.writable?'Writable':'Readonly / context'}</span><small>Source line {field.line}</small></td><td><code>{field.type}</code><small>{field.size} bytes</small></td><td>{field.writeOffsets.join(' / ')}<small>Error position {field.errorPositions.join(' / ')}</small></td><td>{field.writable&&field.hmiOptions.length?<><select aria-label={`HMI control for field ${field.index}`} className="textInput" disabled={!!busy} value={review.hmiId??field.hmiId} onChange={e=>{invalidate();setFields(current=>({...current,[field.id]:{hmiId:e.target.value}}))}}><option value="">Choose input control</option>{field.hmiOptions.map(h=><option key={h.id} value={h.id}>{h.page.split('/').pop()} · {h.control}</option>)}</select>{chosen&&<small>Display {chosen.displayMin??'—'} to {chosen.displayMax??'—'} · scale × {chosen.scale}{chosen.minDatapoint?` · min ${chosen.minDatapoint}`:''}{chosen.maxDatapoint?` · max ${chosen.maxDatapoint}`:''}</small>}{chosen?.issues.map((issue,index)=><small className="writeSTErrorText" key={index}>{issue}</small>)}</>:<span className="muted">{field.writable?'Original source checks':'Position retained'}</span>}</td><td>{field.writable?<input aria-label={`Minimum for field ${field.index}`} className="textInput" disabled={!!busy} value={review.min??chosen?.min??''} placeholder="Source guard" onChange={e=>edit(field.id,{min:e.target.value})}/>: '—'}</td><td>{field.writable?<input aria-label={`Maximum for field ${field.index}`} className="textInput" disabled={!!busy} value={review.max??chosen?.max??''} placeholder="Source guard" onChange={e=>edit(field.id,{max:e.target.value})}/>: '—'}</td><td><details><summary>{field.sourceChecks.length?'View conditions':'View mapping'}</summary>{field.sourceChecks.map((check,index)=><pre key={index}>{check}</pre>)}<p>Read reference: <code>{field.readVariable||'See source'}</code></p>{field.paths.map((path,index)=><p key={index}>Byte {path.offset} when <code>{path.when||'Always'}</code></p>)}{chosen&&<p>Datasource: <code>{chosen.datasource}</code><br/>Units: <code>{chosen.unitSource||'Native PLC units'}</code></p>}</details></td></tr>
    })}</tbody></table></div>
    <p className="muted">Source lines refer to mms_nw_r. Additional limits keep the selected HMI bounds and original setting checks. Conditional fields can share a byte position. Read-only context fields retain their read-layout positions.</p>
   </div>}
   <div className="writeSTGenerate"><label><input ref={reviewConfirmation} type="checkbox" checked={reviewed} disabled={!!busy} onChange={e=>{setReviewed(e.target.checked);setError('')}}/>I reviewed the selected groups, HMI limits, machine conditions and read/write payload differences.</label><a className="btn" href="#write-st-title">Back to Generate ST ↑</a></div>
   <details className="writeSTFindings"><summary>How to use the generated code</summary><ol><li>Review the cyclic ST, variable declarations and write mapping.</li><li>Copy the matching files into the original mms_nw_w program and compile in Automation Studio for the selected CPU.</li><li>Read settings with function 1 on the write port. Build function 2 from the write field map and its active variant.</li><li>Check the write response, then read the values again to confirm.</li></ol><p>Current transport and per-parameter commit behavior are retained. Review the included instructions when a later source check rejects part of a request.</p></details>
  </>}
  {draft&&<section ref={output} className="writeSTOutput"><header className="widgetHead"><div><h3><Check size={18}/> Write ST draft ready</h3><p>Groups {draft.groups.join(', ')} · {draft.reviewedFields} writable fields · {draft.files.length} files</p></div><button className="btn primary" onClick={bundle}><Download size={16}/>Download complete ZIP</button></header><div className="writeSTFileTabs">{draft.files.map(item=><button className={'btn '+(file===item.name?'selected':'')} key={item.name} onClick={()=>setFile(item.name)}>{item.name}</button>)}</div>{selectedFile&&<><div className="actions"><button className="btn" onClick={()=>void copyChatText(selectedFile.text).then(ok=>setNotice(ok?'Code copied.':'Copy was blocked by the browser. Select the code or download the file.'))}><Copy size={15}/>Copy {selectedFile.name}</button><button className="btn" onClick={()=>download(selectedFile.name,selectedFile.text)}><Download size={15}/>Download file</button></div><textarea className="writeSTCode" aria-label={`Generated ${selectedFile.name}`} readOnly spellCheck={false} value={selectedFile.text}/></>}</section>}
 </section>;
}
