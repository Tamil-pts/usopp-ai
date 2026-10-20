import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Check, Keyboard, Locate, Minus, Plus, X} from 'lucide-react';
import {Item, list, memoryValue, request, valueText, hmiTextGroup} from './model';
import type {ViewProps} from './views';
import './hmi-simulation.css';

export function HMISimulation({project, select, openHmiPreview}:ViewProps) {
  const pages=list(project.model?.hmi?.pages), groups=list(project.model?.hmi?.alarmGroups);
  const [pageId,setPageId]=useState(''),[zoom,setZoom]=useState(1),[values,setValues]=useState<Item>({});
  const [controlStates,setControlStates]=useState<Item>({}),[layerStates,setLayerStates]=useState<Item>({}),[formattedTexts,setFormattedTexts]=useState<Item>({}),[previewBusy,setPreviewBusy]=useState(false),[inspect,setInspect]=useState(false);
  const [readErrors,setReadErrors]=useState<Item>({}),[error,setError]=useState(''),[showAlarms,setShowAlarms]=useState(false);
  const [editing,setEditing]=useState<Item|null>(null),[draft,setDraft]=useState(''),[saving,setSaving]=useState(false),[pressed,setPressed]=useState('');
  const [passwordSources,setPasswordSources]=useState<Item>({}),[loginStarting,setLoginStarting]=useState(false);
  const [lowercase,setLowercase]=useState(false);
  const viewport=useRef<HTMLDivElement>(null),holds=useRef(new Map<string,()=>Promise<void>>());
  const page=pages.find(p=>p.id===pageId)||pages[0],objects=list(page?.objects);
  const alarmItems:Item[]=groups.flatMap(group=>list(group.items).map(item=>({...item,group:group.name,source:group.source})));
  const names=useMemo(()=>[...new Set([
    ...list(page?.objects).flatMap(o=>[o.binding,o.textBinding,o.textIndexBinding,o.statusBinding,o.layerState?.statusBinding,o.lockingBinding,o.passwordLevelBinding,o.visibilityBinding,o.minBinding,o.maxBinding,o.bitmapIndexBinding,...list(o.actions).map(a=>a.variable)]),
    ...(showAlarms||list(page?.objects).some(o=>o.kind==='alarm')?groups.flatMap(g=>list(g.items).map(a=>a.binding)):[])
  ].filter((name):name is string=>typeof name==='string'&&!!name))].slice(0,1024),[page,project.model?.hmi?.alarmGroups,showAlarms]);
  useEffect(()=>{
    const controller=new AbortController();let busy=false;
    const load=async()=>{if(busy||document.hidden||!page)return;busy=true;try{const result=await request(`/projects/${project.id}/interface-values`,{method:'POST',signal:controller.signal,body:JSON.stringify({names,pageId:page?.id})});if(!controller.signal.aborted){setValues(result.values||{});setReadErrors(result.errors||{});setControlStates(result.controls||{});setLayerStates(result.layers||{});setFormattedTexts(result.texts||{});setPasswordSources(result.passwordSources||{});}}catch(e){if(!controller.signal.aborted)setError((e as Error).message);}finally{busy=false;}};
    setValues({});setReadErrors({});setControlStates({});setLayerStates({});setPasswordSources({});void load();const timer=setInterval(()=>void load(),1000);
    return()=>{clearInterval(timer);controller.abort();};
  },[project.id,names,page?.id]);
  useEffect(()=>{
    const release=()=>{for(const [id,stop] of holds.current){holds.current.delete(id);void stop().catch(e=>setError(String(e.message)));}setPressed('');};
    window.addEventListener('pointerup',release);window.addEventListener('pointercancel',release);window.addEventListener('blur',release);
    return()=>{release();window.removeEventListener('pointerup',release);window.removeEventListener('pointercancel',release);window.removeEventListener('blur',release);};
  },[project.id]);
  const read=(name:string|undefined)=>name&&Object.hasOwn(values,name)?values[name]:memoryValue(project,name);
  const action=async(object:Item,phase:string,value?:any)=>{const result=await request(`/projects/${project.id}/hmi-action`,{method:'POST',body:JSON.stringify({pageId:page.id,objectId:object.id,phase,value})});if(result.controls)setControlStates(result.controls);if(result.layers)setLayerStates(result.layers);return result;};
  const activate=async(object:Item)=>{
    select('HMI object',object);setError('');
    if(inspect)return;
    setPressed(object.id);
    // Register release before awaiting press, so quick clicks cannot leave a momentary input on.
    const pending=action(object,'press');
    holds.current.set(object.id,()=>pending.catch(()=>{}).then(async()=>{await action(object,'release');}));
    try{
      const result=await pending;
      if(result.navigation){
        const target=pages.find(p=>p.id===result.navigation||p.name===result.navigation);
        if(!target)throw Error('Navigation page could not be resolved: '+result.navigation);
        setPageId(target.id);setEditing(null);
      }
    }catch(e){setPressed('');setError((e as Error).message);}
  };
  const beginInput=(object:Item)=>{select('HMI object',object);if(inspect||object.kind!=='password'&&!object.binding)return;setEditing(object);setDraft(object.kind==='password'?'':String(read(object.binding)??''));setError('');};
  const blocked=(object:Item,state:Item)=>{select('HMI object',object);setError(state.reason||object.limitation||'No supported source action is configured for this control. Inspect its virtual key.');};
  const runLogin=async()=>{setLoginStarting(true);try{await request(`/projects/${project.id}/control`,{method:'POST',body:JSON.stringify({action:'run'})});setError('');}catch(e){setError((e as Error).message);}finally{setLoginStarting(false);}};
  const confirm=async()=>{
    if(!editing||saving)return;setSaving(true);setError('');
    try{
      let next:any=draft;const p=editing.properties||{};
      if(editing.kind==='numeric'){
        next=Number(draft);if(!draft.trim()||!Number.isFinite(next))throw Error('Enter a finite numeric value.');
        const min=editing.minBinding?Number(read(editing.minBinding)):Number(p.MinValue),max=editing.maxBinding?Number(read(editing.maxBinding)):Number(p.MaxValue);
        const hasMin=editing.minBinding||p.MinValue!=null&&p.MinValue!==''&&p.MinValue!=='None',hasMax=editing.maxBinding||p.MaxValue!=null&&p.MaxValue!==''&&p.MaxValue!=='None';
        if(hasMin&&!Number.isFinite(min)||hasMax&&!Number.isFinite(max))throw Error('Configured input limit is unresolved; inspect its PLC binding first.');
        if(hasMin&&Number.isFinite(min)&&next<min||hasMax&&Number.isFinite(max)&&next>max)throw Error(`Value must be within the configured limits (${hasMin?min:'no minimum'} to ${hasMax?max:'no maximum'}).`);
      }else if(p.MaxChars&&draft.length>Number(p.MaxChars))throw Error('Input exceeds MaxChars ('+p.MaxChars+').');
      const result=await action(editing,'input',next);
      if(result.loginLevel===0)throw Error('Password not accepted by the configured virtual HMI source.');
      setEditing(null);setDraft('');
    }catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  if(!page)return <div className="empty"><strong>No HMI pages resolved</strong><p>Refresh the imported project to decode its HMI resources.</p></div>;
  const width=Number(page.width)||800,height=Number(page.height)||600;
  const fit=()=>setZoom(Math.max(.25,Math.min(9,((viewport.current?.clientWidth||width)-30)/width)));
  const color=(value:any,fallback:string)=>page.palette?.[String(value)]||(/^#[\da-f]{3,8}$/i.test(String(value))?value:fallback);
  const alarmList=(className='')=><div className={`virtual-alarm-list ${className}`}><strong>Active AlarmImage states</strong>{alarmItems.filter(a=>read(a.binding)===true||read(a.binding)===1).map(a=><button key={`${a.source}:${a.index}`} onClick={()=>select('HMI alarm',a)}><b>{a.group} · {a.index}</b><span>{a.text}</span></button>)}{!alarmItems.some(a=>read(a.binding)===true||read(a.binding)===1)&&<p>No active bits in the resolved alarm images.</p>}<small>{alarmItems.filter(a=>readErrors[a.binding]).length} unresolved alarm bindings. History, latching and vendor acknowledgement are not simulated.</small></div>;
  const bitmap=(object:Item)=>{
    const state=object.bitmaps?.[pressed===object.id?'pressed':'released']||object.bitmaps?.released;
    const index=Number(read(object.bitmapIndexBinding)||0);
    const variants=list(state?.variants),dynamic=!!object.bitmapIndexBinding||state?.dynamic,entry=dynamic?variants.find(v=>v.index===(Number(state?.offset)||0)+index&&v.status==='resolved'):variants.find(v=>v.level===0&&v.status==='resolved');
    return project.model?.hmi?.bitmapAssets?.[entry?.asset_id]?.data_uri;
  };
  const key=(value:string)=>setDraft(previous=>value==='⌫'?previous.slice(0,-1):value==='Clear'?'':value==='±'?(previous.startsWith('-')?previous.slice(1):'-'+previous):previous+value);
  return <section className="hmi-view virtual-hmi"><header className="view-toolbar"><select aria-label="HMI page" value={page.id} onChange={e=>{setPageId(e.target.value);setEditing(null);}}>{pages.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select><button onClick={()=>setShowAlarms(!showAlarms)}>Alarm groups ({groups.length})</button><button className={inspect?'active':''} aria-pressed={inspect} onClick={()=>{setInspect(!inspect);setEditing(null);}}>{inspect?'Inspecting objects':'Inspect objects'}</button>{openHmiPreview&&objects.some(o=>o.kind==='password')&&project.model?.executionScope?.mode!=='hmi-preview'&&<button disabled={previewBusy} onClick={()=>{setPreviewBusy(true);void openHmiPreview(page.id).finally(()=>setPreviewBusy(false));}}>{previewBusy?'Preparing...':'Create password/login preview'}</button>}<span className="spacer"/><button aria-label="Zoom out HMI" onClick={()=>setZoom(v=>Math.max(.25,Math.round((v-.25)*100)/100))}><Minus size={14}/></button><select aria-label="HMI zoom" value={zoom} onChange={e=>setZoom(Number(e.target.value))}>{[...new Set([.25,.5,.75,1,1.5,2,3,4,5,6,7,8,9,zoom])].sort((a,b)=>a-b).map(v=><option key={v} value={v}>{Math.round(v*100)}%</option>)}</select><button aria-label="Zoom in HMI" onClick={()=>setZoom(v=>Math.min(9,Math.round((v+.25)*100)/100))}><Plus size={14}/></button><button onClick={fit}><Locate size={14}/>Fit</button><button onClick={()=>select('HMI page',page)}>Properties</button></header>
    {error&&!editing&&<div className="notice error" role="alert">{error}<button onClick={()=>setError('')}><X size={12}/></button></div>}
    {showAlarms&&alarmList('alarm-panel')}
    {inspect&&<details className="hmi-layer-panel" open><summary>Runtime layers ({list(page.layers).length})</summary>{list(page.layers).map(layer=>{
      const state=layerStates[layer.id],word=state?.statusWords?.layer;
      const target=String(page.source).split('/Pages/')[0]+'/';
      const switches=pages.filter(p=>String(p.source).startsWith(target)).flatMap(p=>list(p.objects).flatMap(o=>list(o.actions).filter(a=>layer.statusBinding&&a.variable===layer.statusBinding).map(a=>({page:p.id,control:o.name,virtualKey:o.properties?.VirtualKey,kind:a.kind,value:a.value}))));
      const commands=[...new Set(switches.map(s=>`${s.kind} ${s.value}`))];
      return <button key={layer.id} title="Inspect layer configuration" onClick={()=>select('HMI layer',{...layer,statusWord:word,switchControls:switches})}><strong>{layer.name}</strong><code>{layer.statusBinding||'Always visible: no runtime status binding'}</code><span>{word===undefined?(layer.statusConfigured?'Unresolved: input locked':'Visible'):word&1?'Hidden':word&2?'Visible: input locked':'Visible'}</span><small>{switches.length?`${switches.length} source keys: ${commands.join('; ')}`:layer.statusBinding?'Follows status datapoint; no HMI switch found.':'No trigger required.'}</small></button>;
    })}<small>Runtime uses the configured status datapoint: 0 shows, 1 hides, and bit 1 locks input. The editor active layer selects where controls are edited. Layer rows inspect configuration; the original HMI keys perform switching.</small></details>}

    <div className="hmi-canvas-scroll" ref={viewport}><div style={{width:width*zoom,height:height*zoom,position:'relative'}}><div className="hmi-canvas" style={{width,height,transform:`scale(${zoom})`,transformOrigin:'top left',background:color(page.properties?.BackColor,'var(--surface-2)')}}>{objects.map((object,i)=>{
      const props=object.properties||{},kind=object.kind,value=read(object.binding),state=controlStates[object.id];
      if(!state||state.visible===false)return null;
      const layerIndex=list(page.layers).findIndex(l=>l.id===object.layerState?.id);
      const style:React.CSSProperties={zIndex:Math.max(0,layerIndex)*2+1,left:Number(object.x)||0,top:Number(object.y)||0,width:Math.max(1,Number(object.width)||100),height:Math.max(1,Number(object.height)||30),color:color(props.ForeColor,'var(--text)'),background:props.FillStyle==='Transparent'?'transparent':color(props.BackColor,'transparent'),fontSize:Math.max(8,Math.min(36,Number(/_(\d+)/.exec(props.Font||'')?.[1])||12))};
      const asset=bitmap(object),picture=asset?<img src={asset} alt={object.text||object.name} draggable={false}/>:null;
      const locked=state.locked;const title=state.reason||object.limitation||object.binding||object.name;
      if(kind==='button'||kind==='hotspot'){
        const hasActions=list(object.actions).length||object.action;
        return <button key={object.id||i} style={style} className={`hmi-object hmi-button ${kind==='hotspot'?'virtual-hotspot':''} ${inspect?'hmi-inspecting':''}`} aria-disabled={!hasActions||!!locked||inspect} title={title} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);if(inspect)select('HMI object',object);else if(!locked&&hasActions)void activate(object);else blocked(object,state);}} onKeyDown={e=>{if((e.key==='Enter'||e.key===' ')&&!e.repeat){e.preventDefault();if(inspect)select('HMI object',object);else if(!locked&&hasActions)void activate(object);else blocked(object,state);}}} onKeyUp={()=>{const stop=holds.current.get(object.id);holds.current.delete(object.id);if(stop)void stop().catch(e=>setError(e.message));setPressed('');}}>{kind==='hotspot'?(inspect?object.name:null):picture||object.text}</button>;
      }
      if(kind==='numeric'||kind==='string')return <button key={object.id||i} className="hmi-object hmi-number" style={style} title={title} aria-disabled={!object.input||locked||inspect} onClick={()=>object.input&&!locked&&!inspect?beginInput(object):select('HMI object',object)}>{object.input&&<Keyboard size={10}/>} {value===undefined?'—':valueText(value)}</button>;
      if(kind==='bitmap')return picture?<div className="hmi-object virtual-bitmap" key={object.id||i} style={style} onClick={()=>select('HMI object',object)}>{picture}</div>:<button className={`hmi-object hmi-missing-bitmap ${inspect?'hmi-inspecting':''}`} style={{...style,background:'transparent'}} key={object.id||i} title={'Missing bitmap: '+object.name} aria-label={'Missing bitmap '+object.name} onClick={()=>select('HMI object',object)}>{inspect?'Missing bitmap':null}</button>;
      if(kind==='alarm')return <div key={object.id||i} style={style} className="hmi-object virtual-alarm-control">{alarmList()}</div>;
      if(kind==='line'){
        const x1=Number(props.StartX)||0,y1=Number(props.StartY)||0,x2=Number(props.EndX)||0,y2=Number(props.EndY)||0;
        return <svg key={object.id||i} className="hmi-object virtual-line" style={{left:0,top:0,width,height,zIndex:style.zIndex,pointerEvents:'none',background:'none'}}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color(props.ForeColor,'var(--text)')} strokeWidth={Number(props.LineWidth)||1}/></svg>;
      }
      if(kind==='dropdown'){
        const group=hmiTextGroup(project,object);return <select key={object.id||i} style={style} className="hmi-object" aria-label={object.name} value={String(value??'')} disabled={!!locked||!object.binding||inspect} title={title} onChange={e=>void action(object,'input',e.target.value).catch(e=>setError(e.message))}>{Object.entries(group||{}).map(([index,caption])=><option key={index} value={index}>{typeof caption==='object'&&caption?(caption as Item).en||Object.values(caption)[0]:String(caption)}</option>)}</select>;
      }
      if(kind==='shape')return <div key={object.id||i} className="hmi-object" style={{...style,border:`${Number(props.LineWidth)||1}px solid ${color(props.ForeColor,'var(--line)')}`}} onClick={()=>select('HMI object',object)}/>;
      if(kind==='password')return <button key={object.id||i} style={style} title={title} aria-label="Enter HMI password" aria-disabled={locked||inspect} className="hmi-object hmi-password" onClick={()=>!locked&&!inspect?beginInput(object):select('HMI object',object)}><Keyboard size={12}/> <span>******</span></button>;
      if(kind==='text'||kind==='datetime'||kind==='listbox'){
        const group=hmiTextGroup(project,object),mode=String(props.TextSource||'');
        const textValue=object.textBinding?read(object.textBinding):value;
        const index=Number(read(object.textIndexBinding)??0)+Number(props.TextIndexOffset||0);
        const captions=group?.[String(index)],caption=typeof captions==='object'&&captions?captions.en||Object.values(captions)[0]:captions;
        const label=Object.hasOwn(formattedTexts,object.id)?formattedTexts[object.id]:mode==='SingleString'?valueText(textValue??''):mode==='MultipleTexts'?caption??'':mode==='MultipleStrings'?valueText(Array.isArray(textValue)?textValue[index]??'':''):object.binding?valueText(value??''):object.text||'';
        return <div key={object.id||i} className="hmi-object hmi-text" style={style} title={inspect?object.name:undefined} onClick={()=>inspect&&select('HMI object',object)}>{label}</div>;
      }
      return <button key={object.id||i} className={`hmi-object hmi-unsupported ${inspect?'hmi-inspecting':''}`} style={style} title={object.limitation||'Unsupported '+kind} onClick={()=>select('HMI object',object)}>{inspect?object.name:null}</button>;
    })}</div></div></div>
    <footer className="source-footer"><span>{page.name} · {width} × {height} · {objects.length} objects / {objects.filter(o=>controlStates[o.id]?.visible===false).length} hidden</span><span className="spacer"/><span>{project.runtime?.status==='running'?'Live PLC memory':'PLC stopped: visibility logic needs scans'} / {Object.keys(readErrors).length} unresolved bindings</span></footer>
    {editing&&<div className="v-hmi-keypad-backdrop"><form className="v-hmi-keypad" role="dialog" aria-modal="true" aria-label="HMI input keypad" onSubmit={e=>{e.preventDefault();void confirm();}}><header><Keyboard size={18}/><strong>{editing.kind==='password'?'HMI password':editing.text||editing.binding}</strong><button type="button" aria-label="Cancel HMI input" onClick={()=>{setEditing(null);setDraft('');}}><X size={17}/></button></header><input autoFocus type={editing.kind==='password'?'password':'text'} autoComplete="off" aria-label="HMI input value" value={draft} inputMode={editing.kind==='numeric'?'decimal':'text'} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setEditing(null);}}/><div className="v-hmi-keypad-keys">{(editing.kind==='numeric'?['7','8','9','4','5','6','1','2','3','±','0','.']:['Q','W','E','R','T','Y','U','I','O','P','A','S','D','F','G','H','J','K','L','Z','X','C','V','B','N','M','0','1','2','3','4','5','6','7','8','9',' ','_','-','.']).map(k=><button type="button" key={k} disabled={saving} onClick={()=>key(lowercase&&/^[A-Z]$/.test(k)?k.toLowerCase():k)}>{k===' '?'Space':lowercase&&/^[A-Z]$/.test(k)?k.toLowerCase():k}</button>)}</div><div className="v-hmi-keypad-actions">{editing.kind!=='numeric'&&<button type="button" aria-label="Toggle letter case" aria-pressed={lowercase} onClick={()=>setLowercase(!lowercase)}>{lowercase?'ABC':'abc'}</button>}<button type="button" onClick={()=>key('⌫')}>⌫ Backspace</button><button type="button" onClick={()=>key('Clear')}>Clear</button><button type="submit" className="primary" disabled={saving}><Check size={15}/>{saving?'Writing…':'Enter'}</button></div>{error&&<p className="notice error" role="alert">{error}</p>}{editing.kind==='password'&&passwordSources[editing.id]&&<section className="hmi-password-readiness" aria-label="Password source readiness"><strong>{passwordSources[editing.id].readyLevels} source levels ready</strong><p>{passwordSources[editing.id].message}</p>{list(passwordSources[editing.id].producers).filter((p,i,all)=>all.findIndex(a=>a.source===p.source&&a.task===p.task)===i).map((p,i)=><small key={i}>{p.source} / {p.task}, every {p.intervalMs} ms / {p.executionCount?'executed':'waiting for first execution'}</small>)}{list(passwordSources[editing.id].waitingLevels).length>0&&project.runtime?.status!=='running'&&<button type="button" disabled={loginStarting} onClick={()=>void runLogin()}>{loginStarting?'Starting PLC...':'Run PLC to initialize login sources'}</button>}</section>}<small>{editing.kind==='password'?'Checks the configured local password source and writes its login level.':'Current layer, status bits and login level are checked again before writing.'}</small></form></div>}
  </section>;
}
