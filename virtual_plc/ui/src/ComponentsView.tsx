import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDownLeft, ArrowUpRight, Check, ChevronLeft, ChevronRight, CircleHelp, CircuitBoard, FileCode2, Link2, Plus, Save, Search, Settings2, Trash2, Undo2, X } from 'lucide-react';
import { Item, Project, list, memoryValue, request, sourcePath, valueText } from './model';
import './components.css';
import {ComponentAction} from './ComponentAction';
import {ComponentLibrary} from './ComponentLibrary';
import {DeviceTopology} from './DeviceTopology';
import {EnvironmentAlarms} from './EnvironmentAlarms';

type Port = { key: string; label: string; direction: 'input' | 'output'; type: string; required?: boolean };
type Definition = { kind: string; label: string; description: string; ports: Port[]; configFields: Item[] };
type Device = { actionRequired?:string; mode?:string; proposalId?:string; position?: {x:number;y:number}; id: string; name: string; kind: string; enabled: boolean; bindings: Record<string, string>; links?:Record<string,Item>; evidence?:Item; assumptions?:string[]; config: Item; status?: Item; ports?: Item[]; current?: Item };
type Props = { project: Project; onChanged?: (response?: Item) => void; openSource?: (path: string, line?: number) => void };

const copyDevices = (devices: Device[]) => devices.map(device => ({ ...device, bindings: { ...device.bindings }, config: { ...device.config } }));
const savedConfig = (devices: Device[]) => devices.map(({ id, name, kind, enabled, bindings, links, evidence, assumptions, config, position }) => ({ id, name, kind, enabled, bindings, links:links||{}, evidence, assumptions, config, ...(position ? {position} : {}) }));
const kindIcon = (kind: string) => kind === 'pushbutton' ? 'PB' : kind === 'digital_input' ? 'DI' : kind === 'digital_output' ? 'DO' : kind === 'motor' ? 'MOTOR' : /encoder/i.test(kind) ? 'ENC' : /servo/i.test(kind) ? 'SERVO' : /vfd|drive/i.test(kind) ? 'VFD' : /output/i.test(kind) ? 'AO' : 'AI';
const readable = (value: any) => value === undefined || value === null ? '—' : typeof value === 'number' ? Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/\.?0+$/, '') : valueText(value);
const numericType = /^(?:S?INT|USINT|UINT|UDINT|DINT|LINT|ULINT|REAL|LREAL|BYTE|WORD|DWORD|LWORD)$/i;
const compatible = (variable: Item, port: Port) => !variable.valueTruncated && (port.type === 'BOOL' ? String(variable.type).toUpperCase() === 'BOOL' : numericType.test(variable.resolvedType || variable.type || variable.datatype || ''));
const referenceSetting=(kind:string,port:string)=>({vfd:{targetFrequency:'referenceFrequency'},motor:{targetSpeed:'nominalSpeed'},velocity_servo:{targetSpeed:'nominalSpeed'},servo:{target:'targetPosition'}} as Record<string,Record<string,string>>)[kind]?.[port];

function DeviceGraphic({ device }: { device: Device }) {
  const running = device.enabled && device.status?.state === 'active';
  const label = kindIcon(device.kind);
  return <svg className={`vpc-device-graphic ${running ? 'is-active' : ''}`} viewBox="0 0 152 94" role="img" aria-label={`${label} generic virtual component`}>
    <defs><pattern id={`vents-${device.id}`} width="8" height="6" patternUnits="userSpaceOnUse"><path d="M1 1h4" stroke="currentColor" opacity=".2" /></pattern></defs>
    <path className="vpc-device-body" d="M23 10h101v72H23z" rx="7" />
    <path d="M28 15h91v62H28z" fill={`url(#vents-${device.id})`} />
    <rect className="vpc-device-screen" x="34" y="20" width="79" height="29" rx="3" />
    <text x="73.5" y="38" textAnchor="middle">{label}</text>
    <circle cx="39" cy="61" r="4" className={`vpc-device-led ${running ? 'on' : ''}`} />
    <path d="M54 59h14m-14 5h23m9-5h15m-15 5h15M12 26h11M12 45h11M12 64h11m101-38h15m-15 19h15m-15 19h15" stroke="currentColor" opacity=".55" />
    <rect x="63" y="82" width="24" height="4" rx="1" fill="currentColor" opacity=".3" />
  </svg>;
}

function VariablePicker({ project, port, selected, choose, close, openSource }: { project: Project; port: Port; selected?: string; choose: (row: Item) => void; close: () => void; openSource?: Props['openSource'] }) {
  const [query, setQuery] = useState('');
  const [address, setAddress] = useState(selected || '');
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      void request(`/projects/${project.id}/variables?query=${encodeURIComponent(query)}&offset=${page * 40}&limit=40`, { signal: controller.signal }).then(result => {
        setRows(list(result.variables)); setTotal(Number(result.total) || 0); setError('');
      }).catch(e => { if (e.name !== 'AbortError') setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [project.id, query, page]);
  return <div className="vpc-picker-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}><section className="vpc-variable-picker" role="dialog" aria-modal="true" aria-label={`Connect ${port.label}`}>
    <header><Link2 size={17} /><div><strong>Connect {port.label}</strong><small>{port.direction === 'input' ? 'PLC command → component input' : 'Component feedback → PLC variable'} · {port.type === 'BOOL' ? 'BOOL' : 'Scalar numeric variable'}</small></div><button type="button" className="icon-button" aria-label="Close variable selector" onClick={close}><X size={17} /></button></header>
    <div className="vpc-scope-note"><CircleHelp size={15} /><p>The same name can belong to separate programs. Select the exact variable ID and scope; matching names alone do not share PLC memory.</p></div>
    <label className="search vpc-variable-search"><Search size={15} /><input autoFocus placeholder="Search variable name, ID or scope" aria-label="Search variables" value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} /></label>
    <div className="vpc-exact-binding"><label>Scoped array or structure member<input value={address} maxLength={400} placeholder="@global:Alarm[0] or logical/program:Axis.Position" onChange={e => setAddress(e.target.value)} /></label><button type="button" disabled={!address.trim().includes(':')} onClick={() => choose({ id: address.trim(), name: address.trim(), type: port.type })}>Use exact address</button><small>Copy the declaration ID, then add a literal array index or member. Type and bounds are checked when you save connections.</small></div>
    {error && <div className="notice error">{error}</div>}
    <div className="vpc-variable-results" aria-busy={loading}>{loading ? <div className="inline-empty">Searching project variables…</div> : rows.length ? rows.map(row => {
      const match = compatible(row, port);
      return <div className={`vpc-variable-result ${match ? '' : 'incompatible'}`} key={row.id}><button type="button" disabled={!match} onClick={() => choose(row)}><span><strong>{row.name}</strong><small>{row.scope || 'global'} · {row.type || row.datatype}</small><code>{row.id}</code></span><span className="vpc-variable-value">{readable(row.value)}{selected === row.id && <Check size={15} />}</span></button>{openSource && sourcePath(row) && <button type="button" className="icon-button" title="View variable declaration" onClick={() => { openSource(sourcePath(row), row.line); close(); }}><FileCode2 size={15} /></button>}{!match && <small className="vpc-type-note">Requires {port.type === 'BOOL' ? 'BOOL' : 'a supported scalar numeric type'}</small>}</div>;
    }) : <div className="inline-empty">No variables match this search.</div>}</div>
    <footer><span>{total.toLocaleString()} variables · page {page + 1}</span><button type="button" disabled={!page || loading} onClick={() => setPage(page - 1)} aria-label="Previous variables"><ChevronLeft size={15} /></button><button type="button" disabled={(page + 1) * 40 >= total || loading} onClick={() => setPage(page + 1)} aria-label="Next variables"><ChevronRight size={15} /></button></footer>
  </section></div>;
}

function DeviceEditor({ project, device, devices, catalog, variables, close, apply, openSource }: { project: Project; device: Device; devices:Device[]; catalog: Definition[]; variables: Map<string, Item>; close: () => void; apply: (device: Device) => void; openSource?: Props['openSource'] }) {
  const [draft, setDraft] = useState<Device>({ ...device, config: { ...device.config }, bindings: { ...device.bindings } });
  const [selecting, setSelecting] = useState<Port | null>(null);
  const [error, setError] = useState('');
  const definition = catalog.find(entry => entry.kind === draft.kind);
  const setKind = (kind: string) => { const entry = catalog.find(item => item.kind === kind); setDraft(previous => ({ ...previous, kind, enabled: false, bindings: {}, links:{}, ports:[],current:{},config: Object.fromEntries((entry?.configFields || []).map(field => [field.key, field.default])) })); };
  const submit = () => {
    if (!draft.name.trim()) { setError('Enter a component name.'); return; }
    if (draft.enabled && definition?.ports.some(port => port.required && !draft.bindings[port.key] && !draft.links?.[port.key])) { setError('Connect every required port before enabling this device.'); return; }
    for (const field of definition?.configFields || []) { const value = Number(draft.config[field.key]); if (draft.config[field.key] === '' || !Number.isFinite(value) || field.min != null && value < field.min || field.max != null && value > field.max) { setError(`Check ${field.label}: enter a finite value${field.min != null ? ` from ${field.min}` : ''}${field.max != null ? ` to ${field.max}` : ''}.`); return; } }
    apply({ ...draft, name: draft.name.trim(), evidence: {...draft.evidence,
      mappingSource:'manual',confidence:'confirmed',reason:'Connections reviewed and saved by the operator.'} });
  };
  return <div className="vpc-modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}><section className="dialog wide-dialog vpc-editor" role="dialog" aria-modal="true" aria-label="Configure virtual component"><button type="button" className="icon-button dialog-close" onClick={close} aria-label="Close component configuration"><X size={18} /></button><div className="dialog-eyebrow"><CircuitBoard size={17} /> VIRTUAL COMPONENT CONNECTIONS</div><h2>{device.name ? 'Configure component' : 'Add a component'}</h2><p>Connect a generic simulated device to exact PLC variables. Changes stay in your draft until you save connections.</p>
    <div className="form-grid"><label>Component name<input value={draft.name} maxLength={100} placeholder="For example, delivery servo" onChange={e => setDraft({ ...draft, name: e.target.value })} /></label><label>Component model<select value={draft.kind} onChange={e => setKind(e.target.value)}>{catalog.map(entry => <option key={entry.kind} value={entry.kind}>{entry.label}</option>)}</select></label></div>
    <div className="vpc-model-summary"><DeviceGraphic device={draft} /><div><strong>{definition?.label}</strong><p>{definition?.description}</p><span className="badge">Generic virtual model</span></div></div>
    <label className="check-label"><input type="checkbox" checked={draft.enabled} onChange={e=>setDraft({...draft,enabled:e.target.checked})}/>Enable simulated device feedback</label>
    <div className="vpc-editor-heading"><Link2 size={16} /><strong>Signal connections</strong></div><p className="vpc-connection-guide">Required inputs (*) can use a PLC variable or a device link. Linked drive, motor and encoder signals are shown below. Optional references use their displayed model setting; optional feedback needs a destination only when the PLC reads it.</p>
    <div className="vpc-edit-ports">{(definition?.ports || []).map(port => {
      const id=draft.bindings[port.key],variable=variables.get(id),link=draft.links?.[port.key],linked=devices.find(item=>item.id===link?.component);
      const linkedPort=catalog.find(entry=>entry.kind===linked?.kind)?.ports.find(item=>item.key===link?.port);
      const consumers=devices.flatMap(other=>Object.entries(other.links||{}).filter(([,target])=>target.component===draft.id&&target.port===port.key).map(([key])=>other.name+' / '+(catalog.find(entry=>entry.kind===other.kind)?.ports.find(item=>item.key===key)?.label||key)));
      const setting=referenceSetting(draft.kind,port.key),field=definition?.configFields.find(item=>item.key===setting),live=draft.ports?.find(item=>item.key===port.key);
      const caption=id?variable?.name||id:consumers.length?'Feeds device: '+consumers.join(', '):link?`Device link: ${linked?.name||'Missing device'} / ${linkedPort?.label||link.port}`:field?`Model reference: ${draft.config[setting]??field.default} ${field.unit||''}`:port.required?'Choose PLC variable or device link':port.direction==='output'?'No PLC feedback destination (optional)':'Not connected (optional)';
      return <div key={port.key}><span className={`vpc-port-symbol ${port.direction}`}>{port.direction==='input'?<ArrowDownLeft size={16}/>:<ArrowUpRight size={16}/>}</span><span className="vpc-port-description"><strong>{port.label}{port.required?' *':''}</strong><small>{port.direction==='input'?'Command input':'Feedback output'} · {port.type}</small></span><button type="button" className="vpc-binding-button" onClick={()=>setSelecting(port)}><Link2 size={14}/><span>{caption}{id&&<small>{variable?`${variable.scope||'global'} · ${variable.type} · `:''}{id}</small>}{live&&<small>Current: {readable(live.effectiveValue??live.value)}{live.unit?' '+live.unit:''}{id&&live.effectiveValue!=null&&live.effectiveValue!==live.value?' / PLC raw: '+readable(live.value):''}</small>}</span></button>{(id||link)&&<button type="button" className="icon-button" title={`Disconnect ${port.label}`} onClick={()=>{const links={...draft.links};delete links[port.key];setDraft({...draft,links,bindings:{...draft.bindings,[port.key]:''}});}}><X size={15}/></button>}</div>;
    })}</div>
    {Number(draft.config.faultInjected)===1&&<div className="notice error"><strong>Injected device fault is ON.</strong><p>This simulated fault prevents normal drive or motor operation. Clear it for a healthy run, or keep it to exercise fault handling.</p><button type="button" onClick={()=>setDraft({...draft,config:{...draft.config,faultInjected:0}})}>Clear injected fault in draft</button></div>}
    {(definition?.configFields || []).length > 0 && <><div className="vpc-editor-heading"><Settings2 size={16} /><strong>Model settings</strong></div><div className="form-grid vpc-config-fields">{definition!.configFields.map(field => <label key={field.key}>{field.label}{field.unit ? ` (${field.unit})` : ''}<input type="number" step="any" min={field.min} max={field.max} value={draft.config[field.key] ?? field.default ?? ''} onChange={e => setDraft({ ...draft, config: { ...draft.config, [field.key]: e.target.value === '' ? '' : Number(e.target.value) } })} /></label>)}</div></>}
    {definition?.ports.filter(p=>p.direction==='input').map(port=><label key={port.key}>Device link for {port.label}<select value={draft.links?.[port.key]?`${draft.links[port.key].component}|${draft.links[port.key].port}`:''} onChange={e=>{const links={...draft.links};if(e.target.value){const [component,key]=e.target.value.split('|');links[port.key]={component,port:key};setDraft({...draft,links,bindings:{...draft.bindings,[port.key]:''}});}else{delete links[port.key];setDraft({...draft,links});}}}><option value="">Use PLC binding or model default</option>{devices.filter(d=>d.id!==draft.id).flatMap(d=>(catalog.find(c=>c.kind===d.kind)?.ports||[]).filter(p=>p.direction==='output'&&p.type===port.type).map(p=><option key={`${d.id}|${p.key}`} value={`${d.id}|${p.key}`}>{d.name} / {p.label}</option>))}</select></label>)}
    {draft.evidence?.source&&<button type="button" onClick={()=>openSource?.(draft.evidence!.source,draft.evidence!.line)}>Connection source: {draft.evidence.source}:{draft.evidence.line}</button>}
    {draft.assumptions?.length? <div className="notice warning"><div><strong>Review inferred plant settings</strong>{draft.assumptions.map((value,index)=><p key={index}>{value}</p>)}</div></div>:null}
    <div className="notice"><CircleHelp size={15} /><p>Device links connect drives, shafts and encoders directly. PLC bindings use exact scoped tags. Model parameters remain editable and are saved with this workspace.</p></div>
    {error && <div className="notice error">{error}</div>}<div className="dialog-actions"><button type="button" onClick={close}>Cancel</button><button type="button" className="primary" onClick={submit}><Check size={15} /> {draft.proposalId?'Confirm these connections':'Apply to draft'}</button></div>
    {selecting && <VariablePicker project={project} port={selecting} selected={draft.bindings[selecting.key]} close={() => setSelecting(null)} openSource={openSource} choose={row => { const links={...draft.links};delete links[selecting.key];setDraft({ ...draft, links, bindings: { ...draft.bindings, [selecting.key]: row.id } }); variables.set(row.id, row); setSelecting(null); }} />}
  </section></div>;
}

export function ComponentsView({ project, onChanged, openSource }: Props) {
  const [display,setDisplay]=useState('topology');
  const [catalog, setCatalog] = useState<Definition[]>([]);
  const [draft, setDraft] = useState<Device[]>([]);
  const [live, setLive] = useState<Device[]>([]);
  const [libraryOpen,setLibraryOpen]=useState(false);
  const [environment,setEnvironment]=useState<Item>({});
  const [review,setReview]=useState<Item|null>(null);
  const [jig,setJig]=useState<Item>({enabled:!!project.settings?.simulationJigEnabled});
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [editing, setEditing] = useState<Device | null>(null);
  const [query, setQuery] = useState('');
  const [group,setGroup]=useState('all');
  const [page,setPage]=useState(0);
  const [mode,setMode]=useState<'operate'|'edit'|'move'>('operate');
  const [layoutSaving,setLayoutSaving]=useState(false);
  const layout=useRef<Record<string,{x:number;y:number}>>({});
  const layoutQueue=useRef(Promise.resolve());
  const running = project.runtime?.status === 'running';
  const withLayout=(devices:Device[])=>copyDevices(devices).map(d=>layout.current[d.id]?{...d,position:layout.current[d.id]}:d);
  const variables = useMemo(() => new Map<string, Item>([...list(project.model?.variables), ...list(project.runtime?.variables)].map(row => [row.id, row])), [project.model?.variables, project.runtime?.variables]);
  const patch = (devices: Device[]) => { dirtyRef.current = true; setDirty(true); setDraft(devices); setMessage(''); };
  useEffect(() => {
    const controller = new AbortController(); let pending = false;
    dirtyRef.current = false; layout.current={}; setMode('operate'); setDirty(false); setDraft([]); setLive([]); setLoading(true); setError(''); setMessage(''); setEditing(null);
    const load = async () => {
      if (pending || document.visibilityState === 'hidden') return;
      pending = true;
      try {
        const response = await request(`/projects/${project.id}/components`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        const devices = list(response.components) as Device[];
        setLive(devices);setEnvironment(response.environment||{});setJig(response.jig||{enabled:false}); if (!dirtyRef.current) setDraft(withLayout(devices));
        if (Array.isArray(response.catalog)) setCatalog(response.catalog);
        setError('');
      } catch (e) { if (!controller.signal.aborted) setError((e as Error).message); }
      finally { pending = false; if (!controller.signal.aborted) setLoading(false); }
    };
    void load();
    void request('/component-catalog', { signal: controller.signal }).then(response => { if (!controller.signal.aborted) setCatalog(list(response.catalog) as Definition[]); }).catch(() => { /* The component state also carries its catalog. */ });
    const timer = setInterval(() => { void load(); }, 1500);
    return () => { clearInterval(timer); controller.abort(); };
  }, [project.id]);
  useEffect(()=>{if(running&&mode==='edit'){setMode('operate');setEditing(null);}},[running]);
  const changeMode=async(next:'operate'|'edit'|'move')=>{
    if(saving)return false;
    try{
      if(next==='edit'&&running){setSaving(true);const response=await request(`/projects/${project.id}/control`,{method:'POST',body:JSON.stringify({action:'pause'})});onChanged?.(response);}
      setMode(next);setError('');return true;
    }catch(e){setError((e as Error).message);return false;}finally{setSaving(false);}
  };
  const configure=async(device:Device)=>{
    const proposal=list(environment.pendingMappings).find(item=>Object.values(item.bindings||{}).some(value=>Object.values(device.bindings||{}).includes(value as string)));
    if(proposal){setReview(proposal);return;}
    if(await changeMode('edit'))setEditing(device);
  };
  const confirmMapping=async(proposal:Item,bindings?:Record<string,string>,config?:Item)=>{
    if(dirty){setError('Save or discard the current connection draft before confirming a mapping.');return;}
    if(!await changeMode('edit'))return;
    setSaving(true);try{
      const response=await request(`/projects/${project.id}/environment/mappings/${proposal.id}/confirm`,{method:'POST',body:JSON.stringify({bindings,config})});
      const devices=list(response.components) as Device[];setLive(devices);setDraft(withLayout(devices));setEnvironment(response.environment||{});setReview(null);setEditing(null);setMessage('Mapping confirmed. Press Run PLC to continue.');onChanged?.(response);
    }catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  const move=(id:string,position:{x:number;y:number})=>{
    layout.current={...layout.current,[id]:position};
    setDraft(previous=>previous.map(d=>d.id===id?{...d,position}:d));
  };
  const savePosition=(id:string,position:{x:number;y:number})=>{
    move(id,position);
    if(dirtyRef.current){setMessage('Position added to the connection draft. Save connections to keep it.');return;}
    setLayoutSaving(true);
    layoutQueue.current=layoutQueue.current.catch(()=>{}).then(async()=>{
      try{await request(`/projects/${project.id}/component-layout`,{method:'PUT',body:JSON.stringify({positions:{[id]:position}})});setMessage('Device position saved.');}
      catch(e){setError('Position was not saved: '+(e as Error).message);}
    }).finally(()=>setLayoutSaving(false));
  };
  const save = async () => {
    if (running || saving) return;
    setSaving(true); setError('');
    try {
      const response = await request(`/projects/${project.id}/components`, { method: 'PUT', body: JSON.stringify({ components: savedConfig(draft).map(device => ({ ...device, bindings: Object.fromEntries(Object.entries(device.bindings).filter(([, id]) => id)) })) }) });
      const devices = list(response.components) as Device[]; setLive(devices); setDraft(withLayout(devices)); dirtyRef.current = false; setDirty(false); setMessage('Connections saved.'); onChanged?.(response);
    } catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  };
  const signal=async(id:string,value:number)=>{
    if(dirty||saving)return;
    try{const response=await request(`/projects/${project.id}/components/${encodeURIComponent(id)}/signal`,{method:'PUT',body:JSON.stringify({value})});const devices=list(response.components) as Device[];setLive(devices);setDraft(withLayout(devices));setError('');}catch(error){setError((error as Error).message);}
  };
  const fault=async(id:string,active:boolean)=>{
    if(dirty||saving)return;
    try{const response=await request(`/projects/${project.id}/components/${id}/fault`,{method:'PUT',body:JSON.stringify({active})});const devices=list(response.components) as Device[];setLive(devices);setDraft(withLayout(devices));setError('');}catch(e){setError((e as Error).message);}
  };
  const generate=async()=>{
    if(dirty||saving)return;setSaving(true);setError('');
    try{
      if(running)await request(`/projects/${project.id}/control`,{method:'POST',body:JSON.stringify({action:'pause'})});
      const response=await request(`/projects/${project.id}/environment`,{method:'POST',body:JSON.stringify({apply:true})});
      const devices=list(response.components) as Device[];setLive(devices);setDraft(copyDevices(devices));setCatalog(list(response.catalog) as Definition[]);setPage(0);setDisplay('topology');
      setMessage(`Added ${response.plan?.added||0} project-derived components. ${response.plan?.summary?.unresolvedChannels||0} I/O mappings require attention. Review inferred drive feedback, contact polarity and model settings in Configure.`);onChanged?.(response);
    }catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  const restoreDefaults=async()=>{if(dirty||saving)return;setSaving(true);setError('');try{const response=await request(`/projects/${project.id}/simulation-jig`,{method:'PUT',body:JSON.stringify({enabled:true,resetDefaults:true})});setJig(response.jig);setLive(list(response.components) as Device[]);setDraft(withLayout(list(response.components) as Device[]));setMessage(response.jig?.message||'Simulation jig defaults restored.');onChanged?.(response);}catch(e){setError((e as Error).message);}finally{setSaving(false);}};
  const automatic=async(id:string)=>{if(dirty||saving)return;try{const response=await request(`/projects/${project.id}/components/${id}/automatic`,{method:'PUT'});setLive(list(response.components) as Device[]);setDraft(withLayout(list(response.components) as Device[]));setJig(response.jig);setError('');}catch(e){setError((e as Error).message);}};
  const add = () => { const definition = catalog[0]; if (!definition) return; void configure({ id: `component-${crypto.randomUUID()}`, name: '', kind: definition.kind, enabled: false, bindings: {}, config: Object.fromEntries(definition.configFields.map(field => [field.key, field.default])) }); };
  const visible = draft.filter(device => `${device.name} ${device.kind}`.toLowerCase().includes(query.toLowerCase()) && (group==='all'||group==='controls'&&device.kind==='pushbutton'||group==='motion'&&['vfd','servo','velocity_servo','motor','encoder','cylinder'].includes(device.kind)||group==='inputs'&&['digital_input','analog_input'].includes(device.kind)||group==='outputs'&&['digital_output','analog_output'].includes(device.kind)));
  const topologyDevices=visible.map(device=>{const proposal=list(environment.pendingMappings).find(item=>Object.values(item.bindings||{}).some(value=>Object.values(device.bindings||{}).includes(value as string)));const actual=live.find(item=>item.id===device.id);return {...device,actionRequired:proposal?.reason||actual?.actionRequired};});
  const pageCount=Math.max(1,Math.ceil(visible.length/24));
  const shown=visible.slice(Math.min(page,pageCount-1)*24,(Math.min(page,pageCount-1)+1)*24);
  return <section className="vpc-components-view"><header className="vpc-components-toolbar"><div><CircuitBoard size={18} /><strong>Virtual components</strong><button className={display==='topology'?'active':''} onClick={()=>setDisplay('topology')}>Topology</button><button className={display==='cards'?'active':''} onClick={()=>setDisplay('cards')}>Device cards</button><button className={display==='alarms'?'active':''} onClick={()=>setDisplay('alarms')}>Alarm feedback</button><button className={display==='timers'?'active':''} onClick={()=>setDisplay('timers')}>PLC timers</button><span className="badge">{draft.length} / 2048</span></div><select aria-label="Device group" value={group} onChange={e=>{setGroup(e.target.value);setPage(0);}}><option value="all">All field devices</option><option value="controls">Operator controls</option><option value="motion">Drives, motors and encoders</option><option value="inputs">Sensor inputs</option><option value="outputs">Output indicators</option></select><label className="search"><Search size={14} /><input placeholder="Find a component" aria-label="Find a component" value={query} onChange={e => {setQuery(e.target.value);setPage(0);}} /></label><span className="spacer" />{dirty && <><span className="vpc-unsaved">Unsaved connections</span><button disabled={saving} onClick={() => { setDraft(withLayout(live)); dirtyRef.current = false; setDirty(false); setMessage(''); }}><Undo2 size={14} /> Discard draft</button></>}<button onClick={()=>void generate()} disabled={saving||dirty}>{saving?'Building / saving...':'Build from project'}</button><button disabled={saving||dirty||!draft.length} onClick={()=>setLibraryOpen(true)}>Component library</button><button onClick={add} disabled={!catalog.length || draft.length >= 2048 || saving}><Plus size={15} /> Add component</button><button className="primary" onClick={() => { void save(); }} disabled={!dirty || running || saving}><Save size={15} />{saving ? 'Saving…' : 'Save connections'}</button></header>
    <div className={`simulation-jig-panel ${jig.enabled?'on':''}`} role="region" aria-label="Simulation jig status"><div><strong>Simulation jig {jig.enabled?'ON':'OFF'}</strong><span>{jig.enabled?'Configured sensors, drives and encoder feedback feed PLC inputs.':'PLC execution is independent. Switch Simulation jig ON in the top toolbar to supply sensor feedback.'}</span>{jig.enabled&&jig.machine&&<small>Machine ready: {valueText(jig.machine.machineReady)} / FAST run: {valueText(jig.machine.fastRunning)} / Servo ready: {valueText(jig.machine.servoReady)} / {jig.automaticSensors||0} actuator sensors automatic</small>}</div><button disabled={dirty||saving} onClick={()=>void restoreDefaults()}>{saving?'Preparing...':'Restore healthy defaults'}</button></div>
    {display==='topology'&&draft.length>0&&<DeviceTopology projectId={project.id} timeMs={project.runtime?.timeMs||0} runtimeStatus={project.runtime?.status} openSource={openSource} devices={topologyDevices} catalog={catalog} live={live} disabled={saving} mode={mode} changeMode={next=>void changeMode(next)} layoutSaving={layoutSaving} signalDisabled={dirty || saving || mode!=='operate' || !jig.enabled} signal={(id,value)=>void signal(id,value)} fault={(id,active)=>void fault(id,active)} configure={device=>void configure(device as Device)} move={move} moveEnd={savePosition} automatic={id=>void automatic(id)}/>}
    {display==='cards'&&draft.length>0&&<div className="environment-pagination"><span>{visible.length} components | {shown.length} displayed</span><button disabled={page<=0} onClick={()=>setPage(v=>v-1)}>Previous</button><span>{Math.min(page+1,pageCount)} / {pageCount}</span><button disabled={page+1>=pageCount} onClick={()=>setPage(v=>v+1)}>Next</button></div>}{(display==='alarms'||display==='timers')&&<EnvironmentAlarms view={display} project={project} signal={(id,value)=>void signal(id,value)} openSource={openSource}/>}<div className="vpc-components-intro"><span className="vpc-virtual-pill"><Activity size={14} /> Generic virtual devices</span><p>Build field devices from the selected project I/O, then operate contacts and inspect drive, motor and encoder feedback. Configure names, connections and model values for your machine.</p></div>
    {error && <div className="notice error">{error}</div>}{message && <div className="notice vpc-saved-message"><Check size={15} />{message}</div>}
    <div className="vpc-components-content" style={{display:display==='cards'||(!draft.length&&display==='topology')?undefined:'none'}}>{loading ? <div className="empty"><CircuitBoard size={28} /><strong>Loading component connections…</strong></div> : !draft.length ? <div className="vpc-components-empty"><CircuitBoard size={40} /><h3>Connect your virtual equipment</h3><p>Add a component, map its ports to exact PLC variables, then save the connections. New components start disabled so feedback is only written after you explicitly enable them.</p><div className="vpc-kind-options">{catalog.map(definition => <button key={definition.kind} disabled={saving} onClick={() => void configure({ id: `component-${crypto.randomUUID()}`, name: '', kind: definition.kind, enabled: false, bindings: {}, config: Object.fromEntries(definition.configFields.map(field => [field.key, field.default])) })}><span>{kindIcon(definition.kind)}</span><strong>{definition.label}</strong><small>{definition.ports.length} signal ports</small><Plus size={15} /></button>)}</div></div> : <div className="vpc-component-grid">{(display==='cards'?shown:[]).map(device => {
      const definition = catalog.find(entry => entry.kind === device.kind); const actual = live.find(entry => entry.id === device.id); const state = device.enabled ? actual?.status?.state || 'ready' : 'disabled'; const telemetryMatches = JSON.stringify(savedConfig([device])) === JSON.stringify(savedConfig(actual ? [actual] : []));
      return <article className={`vpc-component-card ${!device.enabled ? 'is-disabled' : ''}`} key={device.id}><header><DeviceGraphic device={{ ...device, status: telemetryMatches ? actual?.status : undefined }} /><div className="vpc-device-heading"><span>{definition?.label || device.kind}</span><h3>{device.name}</h3><span className={`vpc-state ${state}`}><i />{telemetryMatches ? state : 'draft'}<span>· generic model</span></span></div><button className="icon-button" title="Configure component connections" disabled={saving} onClick={() => void configure(device)}><Settings2 size={16} /></button><ComponentAction name={device.name} reason={topologyDevices.find(item=>item.id===device.id)?.actionRequired} onClick={()=>void configure(device)}/></header>
        <div className="vpc-card-ports">{(definition?.ports || []).map(port => { const id = device.bindings[port.key]; const variable = variables.get(id); const feedback = actual?.ports?.find(row => row.key === port.key); const value = telemetryMatches && feedback ? feedback.value : memoryValue(project, id); return <div className={`vpc-card-port ${id ? 'connected' : ''}`} key={port.key}><span className={`vpc-port-symbol ${port.direction}`} title={port.direction === 'input' ? 'PLC → component' : 'Component → PLC'}>{port.direction === 'input' ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}</span><span className="vpc-port-label"><strong>{port.label}</strong><small title={id}>{id ? `${variable?.scope || 'PLC'} · ${variable?.name || id}` : 'Not connected'}</small></span><span className={`vpc-port-value ${feedback?.forced ? 'forced' : ''}`} title={feedback?.forced ? 'PLC variable is forced' : id}>{id ? readable(value) : '—'}{feedback?.forced && <small>forced</small>}</span></div>; })}</div>
        <small className="vpc-mapping-mode">{actual?.mode||'manual'} / {device.evidence?.confidence||'configured'} confidence</small>{telemetryMatches && actual?.status?.message && <p className={`vpc-device-message ${state}`}>{actual.status.message}</p>}
        <footer><label><input type="checkbox" checked={device.enabled} disabled={running || saving} onChange={e => patch(draft.map(item => item.id === device.id ? { ...item, enabled: e.target.checked } : item))} />{device.enabled ? 'Enabled' : 'Disabled'}</label><span className="spacer" /><button className="icon-button" title="Remove component from draft" disabled={running || saving} onClick={() => patch(draft.filter(item => item.id !== device.id))}><Trash2 size={15} /></button></footer>
      </article>;
    })}</div>}{!loading && draft.length > 0 && !visible.length && <div className="inline-empty">No components match this search.</div>}</div>
    <footer className="vpc-components-footer"><span><ArrowDownLeft size={13} /> PLC command in</span><span><ArrowUpRight size={13} /> Virtual feedback out</span><span>Configuration is saved with this workspace. Component model state resets on reopen or import.</span></footer>
    {list(environment.pendingMappings).length>0&&<section className="mapping-review-list" aria-label="Connections requiring confirmation"><h3>Connections requiring confirmation</h3>{list(environment.pendingMappings).map(item=><button key={item.id} onClick={()=>setReview(item)}><span aria-hidden="true">&#9888;</span><strong>{item.name}</strong><span>{item.reason}</span></button>)}</section>}
    {review&&<div className="vpc-modal-backdrop"><section className="dialog wide-dialog" role="dialog" aria-modal="true" aria-label="Review component mapping"><h2>Action required: {review.name}</h2><p>{review.reason}</p><p>The PLC will remain in control of its outputs. Confirm the physical association or change the exact PLC tags below.</p><dl>{Object.entries(review.bindings||{}).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd><code>{String(value)}</code></dd></React.Fragment>)}</dl>{Object.keys(review.candidates||{}).length>0&&<p>Several tags match. Choose the required connections before confirming.</p>}<div className="dialog-actions"><button onClick={()=>setReview(null)}>Close</button><button onClick={async()=>{if(await changeMode('edit')){setEditing({...review,proposalId:review.id} as Device);setReview(null);}}}>Edit proposed connections</button><button className="primary" disabled={saving||Object.keys(review.candidates||{}).length>0} onClick={()=>void confirmMapping(review)}>Confirm mapping</button></div></section></div>}
    {libraryOpen&&<ComponentLibrary projectId={project.id} devices={draft} catalog={catalog} close={()=>setLibraryOpen(false)} apply={async(identity,payload)=>{
      if(!await changeMode('edit'))throw new Error('Pause the PLC before adding library models.');
      const response=await request(`/projects/${project.id}/component-library/${identity}/apply`,{method:'POST',body:JSON.stringify(payload)});
      const devices=list(response.components) as Device[];setLive(devices);setDraft(withLayout(devices));setMessage(response.message);onChanged?.(response);
    }}/>}
    {editing && <DeviceEditor project={project} device={editing} devices={draft} catalog={catalog} variables={variables} close={() => setEditing(null)} openSource={openSource} apply={device => { if(device.proposalId){void confirmMapping({id:device.proposalId},device.bindings,device.config);return;} patch(draft.some(item => item.id === device.id) ? draft.map(item => item.id === device.id ? device : item) : [...draft, device]); setEditing(null); }} />}
  </section>;
}
