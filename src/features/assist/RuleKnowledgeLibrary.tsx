import {useEffect,useState} from 'react';
import {Copy,Trash2} from 'lucide-react';
import {RuleDetails} from '../rules/RuleDetails';
import {apiJson,categoryFor,useRuleLibrary} from '../rules/library';
export function RuleKnowledgeLibrary({revision,onEdit,onRulesChanged}:{revision:number;onEdit:(rule:any)=>void;onRulesChanged:()=>void}){
 const {rules,error,reload}=useRuleLibrary(revision);const [query,setQuery]=useState('');const [viewed,setViewed]=useState<any>(null);const [busy,setBusy]=useState('');const [message,setMessage]=useState('');
 const [duplicate,setDuplicate]=useState<any>(null);const [duplicateName,setDuplicateName]=useState('');
 const [features,setFeatures]=useState<any[]>([]),[featureId,setFeatureId]=useState(''),[linkId,setLinkId]=useState('');
 const [pipelines,setPipelines]=useState<any[]>([]),[pipeline,setPipeline]=useState<any>(null),[stageId,setStageId]=useState('');
 const [selectionDirty,setSelectionDirty]=useState(false);
 const refreshFeatures=async()=>{try{const data=await apiJson('/api/rules/features');setFeatures(data.features||[]);setPipelines(data.pipelines||[])}catch(e:any){setMessage(e.message)}};
 useEffect(()=>{void refreshFeatures()},[revision,rules]);
 const feature=features.find(item=>item.id===featureId);
 const stage=pipeline?.stages?.find((item:any)=>item.id===stageId);
 const scope=(rule:any)=>!pipeline||pipeline.machineDepartment==='All'||(rule.machineScope||['All']).some((value:string)=>value.toLowerCase()==='all'||value.toLowerCase()===String(pipeline.machineDepartment||'All').toLowerCase());
 const linked=(rule:any)=>features.filter(item=>(item.ruleIds||[]).includes(rule.id));
 const selectable=(rule:any)=>!!stage&&rule.enabled!==false&&scope(rule)&&linked(rule).some(item=>item.id===stage.featureId);
 const selectRules=(ids:string[])=>{setPipeline((current:any)=>({...current,stages:current.stages.map((item:any)=>item.id===stageId?{...item,ruleIds:ids}:item)}));setSelectionDirty(true)};
 const saveSelection=async()=>{if(!pipeline||busy)return;setBusy('pipeline');try{const saved=await apiJson('/api/rules/feature-pipeline',pipeline);setPipeline(saved);setSelectionDirty(false);await refreshFeatures();onRulesChanged();setMessage('Pipeline rule selection saved. Reload this saved pipeline in Rules to use the updated selection.')}catch(e:any){setMessage(e.message)}finally{setBusy('')}};
 const linkRule=async()=>{if(!feature||!linkId||busy)return;setBusy('link');try{await apiJson('/api/rules/features/'+encodeURIComponent(feature.id),{...feature,ruleIds:[...new Set([...(feature.ruleIds||[]),linkId])]});setLinkId('');await refreshFeatures();await reload();onRulesChanged();setMessage('Rule linked to '+feature.name+'.')}catch(e:any){setMessage(e.message)}finally{setBusy('')}};
 const beginDuplicate=(rule:any)=>{
  const base=(rule.name||rule.id)+' (copy)';let name=base;let number=2;
  while(rules.some(item=>String(item.name||'').toLowerCase()===name.toLowerCase()))name=`${base} ${number++}`;
  setDuplicate(structuredClone(rule));setDuplicateName(name);setMessage('');
 };
 const saveDuplicate=async()=>{
  if(!duplicate||busy)return;
  const name=duplicateName.trim();
  if(!name||rules.some(rule=>String(rule.name||'').trim().toLowerCase()===name.toLowerCase())){setMessage('Enter a different, unused rule name.');return}
  setBusy(duplicate.id);setMessage('');
  try{
   const {id}=await apiJson('/api/rules/next-id',{});
   const copy={...structuredClone(duplicate),id,standardId:id,name,version:'1.0',enabled:false,reviewStatus:'Needs engineer review'};
   for(const key of ['moduleFile','createdAt','updatedAt','testResults','lastResult','lastTest','reviewedAt'])delete copy[key];
   await apiJson('/api/rules/modules',{config:{rules:[copy]},createOnly:true});
   setDuplicate(null);await reload();onRulesChanged();setMessage(`Created draft ${name} (${id}). Use Configure / test to review and enable it.`);
  }catch(error:any){setMessage(error.message||'Could not duplicate the rule.')}finally{setBusy('')}
 };
 const visible=rules.filter(rule=>(!featureId||linked(rule).some(item=>item.id===featureId))&&[rule.standardId,rule.id,rule.name,categoryFor(rule),rule.description].some(value=>String(value||'').toLowerCase().includes(query.toLowerCase())));
 const deleteRule=async(rule:any)=>{
  if(!window.confirm(`Delete ${rule.id} — ${rule.name||rule.id} from the rule library and unlink it from its features and pipelines?`))return;
  setBusy(rule.id);setMessage('');
  try{await apiJson(`/api/rules/library/${encodeURIComponent(rule.id)}`,undefined,'DELETE');if(viewed?.id===rule.id)setViewed(null);await reload();onRulesChanged();setMessage(`${rule.id} deleted from the rule library.`)}
  catch(error:any){setMessage(error.message||'Could not delete the rule.')}
  finally{setBusy('')}
 };
 return <section className="card knowledgeTableCard"><h3>Rule library</h3><p>Manage rules, feature links and saved pipeline checks here. Saving and enabling a configured rule automatically links it to its feature.</p>
  <div className="actions"><input className="textInput" aria-label="Search rules" placeholder="Search rule or category" value={query} onChange={e=>setQuery(e.target.value)}/><button className="btn" onClick={()=>{void reload();void refreshFeatures()}}>Refresh rules</button><span>{visible.length} rules</span></div>
  <div className="actions"><label>Feature<select value={featureId} disabled={!!busy} onChange={e=>{setFeatureId(e.target.value);setLinkId('')}}><option value="">All features</option>{features.map(item=><option key={item.id} value={item.id}>{item.name} ({item.ruleIds?.length||0})</option>)}</select></label>{feature&&<><select aria-label="Rule to link to feature" value={linkId} disabled={!!busy} onChange={e=>setLinkId(e.target.value)}><option value="">Link an existing rule to {feature.name}</option>{rules.filter(rule=>!(feature.ruleIds||[]).includes(rule.id)).map(rule=><option key={rule.id} value={rule.id}>{rule.name||rule.id}</option>)}</select><button className="btn" disabled={!!busy||!linkId} onClick={()=>void linkRule()}>Link rule</button></>}</div>
  <details><summary>Saved pipeline rule selection</summary><p>Save a pipeline in Rules first, then choose its feature step here. Each occurrence of a feature has its own selection.</p><div className="actions"><label>Pipeline<select value={pipeline?.id||''} disabled={!!busy||selectionDirty} onChange={e=>{setPipeline(structuredClone(pipelines.find(item=>item.id===e.target.value)||null));setStageId('')}}><option value="">Choose saved pipeline</option>{pipelines.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Feature step<select value={stageId} disabled={!pipeline||!!busy} onChange={e=>{setStageId(e.target.value);setFeatureId(pipeline.stages.find((item:any)=>item.id===e.target.value)?.featureId||'')}}><option value="">Choose feature step</option>{pipeline?.stages?.map((item:any,index:number)=><option key={item.id} value={item.id}>{index+1}. {item.label||item.featureId}</option>)}</select></label><button className="btn" disabled={!stage||!!busy} onClick={()=>selectRules(rules.filter(selectable).map(rule=>rule.id))}>Select all ready checks</button><button className="btn" disabled={!stage||!!busy} onClick={()=>selectRules([])}>Clear selection</button><button className="btn primary" disabled={!selectionDirty||!!busy} onClick={()=>void saveSelection()}>Save selection</button>{selectionDirty&&<button className="btn" disabled={!!busy} onClick={()=>{setPipeline(structuredClone(pipelines.find(item=>item.id===pipeline.id)||null));setSelectionDirty(false)}}>Discard changes</button>}</div>{stage&&<p>Select rules in the table below for {pipeline.name} / {stage.label||stage.featureId}.</p>}</details>
  {message&&<p className="ruleMessage" role="status">{message}</p>}
  {error&&<p role="alert">{error}</p>}
  {duplicate&&<section className="card"><h4>Duplicate {duplicate.name||duplicate.id}</h4><p>The copy receives a new unique rule ID and is saved as a draft with the same requirements and accepted alternatives.</p><label>New rule name<input className="textInput" value={duplicateName} disabled={!!busy} onChange={e=>setDuplicateName(e.target.value)}/></label><div className="actions"><button className="btn primary" disabled={!!busy||!duplicateName.trim()} onClick={()=>void saveDuplicate()}>{busy?'Creating copy?':'Create duplicate draft'}</button><button className="btn" disabled={!!busy} onClick={()=>setDuplicate(null)}>Cancel</button></div></section>}
  <div className="knowledgeTableScroll"><table className="table"><thead><tr>{stage&&<th>Run in pipeline</th>}<th>Rule</th><th>Feature</th><th>Category</th><th>File / checks</th><th>Saved status</th><th>Actions</th></tr></thead><tbody>{visible.map(rule=><tr key={rule.id}>{stage&&<td><input type="checkbox" aria-label={'Select '+rule.id} disabled={!!busy||(!selectable(rule)&&!stage.ruleIds.includes(rule.id))} checked={stage.ruleIds.includes(rule.id)} onChange={e=>selectRules(e.target.checked?[...new Set([...stage.ruleIds,rule.id])]:stage.ruleIds.filter((id:string)=>id!==rule.id))}/>{rule.enabled===false?<small>Draft - enable first</small>:!scope(rule)?<small>Outside pipeline machine scope</small>:null}</td>}<td><b>{rule.name||rule.id}</b><div>{rule.id}</div></td><td>{linked(rule).map(item=>item.name).join(', ')||'Not linked'}</td><td>{categoryFor(rule)}</td><td>{rule.checks?.map((check:any)=>check.file).filter(Boolean).join(', ')||rule.subroutine||rule.sourceFile||'File not configured'}<small>{rule.checks?.length||0} requirements</small></td><td>{rule.enabled===false?'Saved · Draft':'Saved · Enabled'}</td><td><div className="actions"><button className="btn" onClick={()=>setViewed(rule)}>View rule</button><button className="btn" onClick={()=>onEdit(rule)}>Configure / test</button><button className="btn" disabled={!!busy} onClick={()=>beginDuplicate(rule)}><Copy size={14}/>Duplicate</button><button className="btn danger" disabled={!!busy} title={`Delete ${rule.id}`} onClick={()=>void deleteRule(rule)}>{busy===rule.id?'Deleting…':<><Trash2 size={14}/>Delete</>}</button></div></td></tr>)}</tbody></table></div>
  {viewed&&<RuleDetails rule={viewed} onClose={()=>setViewed(null)}/>}
 </section>;
}
