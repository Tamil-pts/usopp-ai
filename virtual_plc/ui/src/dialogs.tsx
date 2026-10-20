import React, { useState } from 'react';
import { Box, ChevronRight, Download, Save } from 'lucide-react';
import { Item, Project } from './model';
import { Badge } from './views';

export function SettingsDialog({project,busy,autosave,setAutosave,save,close,exportProject}: {project:Project;busy:boolean;autosave:boolean;setAutosave:(v:boolean)=>void;save:(extra:Item)=>Promise<boolean>;close:()=>void;exportProject:()=>void}) {
  const [manual,setManual]=useState(JSON.stringify(project.manualCorrections||{},null,2));
  const [scenarios,setScenarios]=useState(JSON.stringify(project.scenarios||[],null,2));
  const [templateKind,setTemplateKind]=useState(project.settings?.templateKind||'');
  const [activeScenario,setActiveScenario]=useState(project.settings?.activeScenario||'');
  const [backgroundLoad,setBackgroundLoad]=useState(project.settings?.backgroundLoad||'balanced');
  const [error,setError]=useState('');
  let available:Item[]=[];try{const parsed=JSON.parse(scenarios);if(Array.isArray(parsed))available=parsed;}catch{/* The editable JSON may temporarily be incomplete. */}
  const apply=async()=>{try{const parsedManual=JSON.parse(manual),parsedScenarios=JSON.parse(scenarios);if(!parsedManual||Array.isArray(parsedManual)||typeof parsedManual!=='object')throw new Error('Manual corrections must be a JSON object.');if(!Array.isArray(parsedScenarios))throw new Error('Scenarios must be a JSON array.');const extra:Item={settings:{...project.settings,templateKind,activeScenario,autosave,backgroundLoad},scenarios:parsedScenarios};if(JSON.stringify(parsedManual)!==JSON.stringify(project.manualCorrections||{}))extra.manualCorrections=parsedManual;if(await save(extra))close();}catch(e){setError((e as Error).message);}};
  return <form onSubmit={e=>{e.preventDefault();void apply();}}>
    <h2>Virtual PLC configuration</h2>
    <p>Save simulation settings and reusable controller, I/O or simulation templates. Explicit virtual overrides are separate from the imported PLC source.</p>
    <div className="form-grid"><label>Reusable template type<select value={templateKind} onChange={e=>setTemplateKind(e.target.value)}><option value="">Regular workspace</option><option value="controller">Controller configuration template</option><option value="io">I/O mapping template</option><option value="simulation">Simulation template</option></select></label><label>Active scenario<select value={activeScenario} onChange={e=>setActiveScenario(e.target.value)}><option value="">No scheduled scenario</option>{available.map((scenario,index)=><option key={scenario.id||index} value={scenario.id}>{scenario.name||scenario.id||`Scenario ${index+1}`}</option>)}</select></label></div>
    <label className="check-label"><input type="checkbox" checked={autosave} onChange={e=>setAutosave(e.target.checked)}/> Autosave watchlist and simulation settings</label>
    <label>Background simulation load<select value={backgroundLoad} onChange={e=>setBackgroundLoad(e.target.value)}><option value="responsive">Responsive - 10% scan CPU budget</option><option value="balanced">Balanced - 25% scan CPU budget</option><option value="fast">Fast - 75% scan CPU budget</option></select><small>Lower load keeps the application responsive. Large projects advance more slowly than real machine time.</small></label>
    <div className="form-grid"><label>Virtual overrides (JSON)<textarea rows={12} className="mono" value={manual} onChange={e=>setManual(e.target.value)}/><small>Supported keys: taskIntervals, programAssignments, taskEnabled, ioMappings, cpuServices, simulationProfile and sourceCorrections. Use analyzed IDs. Initial profiles and source-copy corrections are recorded in the workspace.</small></label><label>Simulation scenarios (JSON array)<textarea rows={12} className="mono" value={scenarios} onChange={e=>setScenarios(e.target.value)}/><small>Each scenario has id, name and events. Each event has timeMs, name, value, and optional force. Times use the deterministic clock.</small></label></div>
    <div className="notice warning">Pause before changing virtual task or I/O overrides. Applying changed overrides reconstructs virtual memory and compatibility; original project files are never modified. Scenario events run only when the selected supported simulation is running.</div>
    {error&&<div className="notice error">{error}</div>}
    <div className="dialog-actions"><button type="button" onClick={exportProject}><Download size={15}/> Export reusable workspace</button><button className="primary" disabled={busy}><Save size={15}/> Save configuration</button></div>
  </form>;
}

export function TemplatesDialog({projects,busy,useTemplate}: {projects:Item[];busy:boolean;useTemplate:(project:Item)=>void}) {
  const [kind,setKind]=useState('');
  const templates=projects.filter(p=>p.settings?.templateKind&&(!kind||p.settings.templateKind===kind));
  return <><div className="dialog-eyebrow"><Box size={17}/> REUSABLE ENGINEERING MODELS</div><h2>Workspace templates</h2><p>Reuse saved, project-derived controller, I/O and simulation configurations. Using a template creates a separate workspace with its original source evidence.</p><label>Template category<select value={kind} onChange={e=>setKind(e.target.value)}><option value="">All templates</option><option value="controller">Controller</option><option value="io">I/O</option><option value="simulation">Simulation</option></select></label><div className="workspace-list">{templates.length?templates.map(template=><button key={template.id} disabled={busy} onClick={()=>useTemplate(template)}><Box size={18}/><span><strong>{template.name}</strong><small>Create a separate workspace</small></span><Badge>{template.settings.templateKind}</Badge><ChevronRight size={15}/></button>):<div className="inline-empty">No templates in this category. Open a project, choose Workspace settings, and save its template type.</div>}</div></>;
}
