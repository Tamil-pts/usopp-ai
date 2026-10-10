import {ValidationFindings,ChopperRecommendation} from './ValidationFindings';
import React,{useEffect,useState} from 'react';
import {LayoutDashboard,FolderOpen,ArrowRightLeft,Table2,SlidersHorizontal,MessageSquare,Settings,Download,FileText,ChevronRight,Clock3,Search,Sparkles,FolderTree,FileSpreadsheet,Play,Plus,Trash2,Save,RefreshCw,ShieldCheck,Upload,CheckCircle2,AlertTriangle,AlertCircle,XCircle,Eye,GitCompare,GitCompareArrows,BookOpen,ChevronDown,Minus,X} from 'lucide-react';
import type {MetaCol,Status} from '../../shared/types';
import {DEFAULT_META_COLS} from './metadataColumns';
import {Badge,Detail} from '../../shared/ui';
import {downloadCSV} from '../../shared/download';
import {logEvent} from '../../shared/logging';

export function TablePage({title,desc,rows,type,metaCols,projectName,onSource}:{title:string,desc:string,rows:any[],type:string,metaCols?:MetaCol[],projectName?:string,onSource?:(row:any,mode:'source'|'types')=>void}){
 const [filter,setFilter]=useState<'all'|Status>('all');const [q,setQ]=useState('');const [open,setOpen]=useState<number|null>(null);
 const filtered=rows.filter(r=>(filter==='all'||r.status===filter)&&JSON.stringify(r).toLowerCase().includes(q.toLowerCase()));

 return <><div className="pageHead"><div><h1>{title}</h1><p>{desc}</p></div><button className="btn" onClick={()=>downloadCSV(filtered,`uSOPp_${type}.csv`)}><Download size={13}/> Export CSV</button></div><div className="toolbar"><div className="filters">{(['all','fail','warn','pass'] as const).map(f=><button className={'chip '+(filter===f?'active':'')} key={f} onClick={()=>setFilter(f)}>{f==='all'?'All':f==='warn'?'Warning':f[0].toUpperCase()+f.slice(1)}</button>)}</div><div><Search size={13}/><input className="search" value={q} onChange={e=>setQ(e.target.value)} placeholder="Search parameter / Group Code"/></div></div><div className={'card tableWrap '+(type==='metadata'?'metadataTableWrap':'')}><table className={'table '+(type==='metadata'?'metadataCompareTable':'')}>{type==='metadata'?<MetaTable rows={filtered} open={open} setOpen={setOpen} columns={metaCols||DEFAULT_META_COLS} projectName={projectName||''} allRows={rows}/>:type==='offset'?<OffsetTable rows={filtered} open={open} setOpen={setOpen} onSource={onSource}/>:<DropTable rows={filtered} open={open} setOpen={setOpen}/>}</table></div></>
}

function OffsetTable({rows,open,setOpen,onSource}:any){return <><thead><tr><th>Sl. No.</th><th>Group Code</th><th>PLC Tag / Variable</th><th>Parameter</th><th>Packet path / condition</th><th>Data Type</th><th>Field size (bytes)</th><th>Buffer offset (Actual → Expected)</th><th>TCP offset (starts at 0)</th><th>Status</th></tr></thead><tbody>{rows.map((r:any)=><React.Fragment key={r.id}><tr className="data" onClick={()=>setOpen(open===r.id?null:r.id)}><td>{r.id}</td><td className="mono">{r.gc}</td><td className="mono">{r.parameter}</td><td>{r.description||'—'}</td><td>{r.condition||'All paths'}</td><td className="mono">{r.type}</td><td className="mono">{r.size}</td><td className={'mono '+(r.actual!==r.expected?'failText':'')}>{r.actual} → {r.expected}</td><td className="mono">{r.tcpOffset}</td><td><Badge status={r.status}/>{r.status!=='pass'&&<button className="btn" onClick={e=>{e.stopPropagation();setOpen(open===r.id?null:r.id)}}>Why / recommendation</button>}</td></tr>{open===r.id&&<tr className="detail"><td colSpan={10}>{r.status!=='pass'&&<ValidationFindings issues={r.issues} fallback={r.root||'Review this packet field'} sourceFile={r.sourceFile} lineNumber={r.lineNumber} onSource={onSource?(file,line)=>onSource({...r,sourceFile:file,lineNumber:line},'source'):undefined}/>}<div className="detailGrid"><Detail k="Tag Code" v={r.tag} mono/><Detail k="PLC Tag / declared variable" v={r.parameter} mono/><Detail k="Parameter (PLC logic comment)" v={r.description||'No PLC comment found.'}/><Detail k="Packet path / condition" v={r.condition||'All paths'}/><Detail k="Declared data type" v={r.declaredType} mono/><Detail k="Declared size" v={r.declaredSize||'—'} mono/><Detail k="Resolved packet data type" v={r.type} mono/><Detail k="Packet write method" v={r.method}/><Detail k="Field size (bytes)" v={r.size} mono/><Detail k="TCP offset (payload-relative; starts at 0)" v={r.tcpOffset} mono/><Detail k="Metadata offset (payload-relative)" v={r.payloadOffset} mono/><Detail k="nw_i increment used" v={r.increment===''||r.increment==null?'Not detected':r.increment} mono/><Detail k="Offset after copy" v={r.after||'—'} mono/><Detail k="Buffer offset (actual → expected)" v={`${r.actual} → ${r.expected}`} mono/><div className="detailBlock full"><div className="k">PLC source / logic</div>{onSource&&r.sourceFile&&<div className="actions"><button className="btn" onClick={()=>onSource(r,'source')}>View / edit source</button><button className="btn" onClick={()=>onSource(r,'types')}>PLC tag / datatype</button></div>}<div className="code">{r.code||'Resolved from PLC source; no exception evidence.'}</div></div>{r.evidence?.length>0&&<div className="detailBlock full"><div className="k">Branch assignments</div><div className="code">{r.evidence.map((e:any,i:number)=><div key={i}>{e.sourceFile}:{e.lineNumber} | {e.condition||'Unconditional'} | {e.sourceText||`Source: ${e.sourceExpression}; destination: ${e.destinationExpression}; method: ${e.transferMethod||r.method}`}</div>)}</div></div>}<Detail k="Source expression" v={r.src||'—'} mono/><Detail k="Destination expression" v={r.dest||'—'} mono/></div></td></tr>}</React.Fragment>)}</tbody></>}
function MappingToggle({row,projectName,onSaved,metaOptions=[],acceptedMapping='',globalMapping=''}:{row:any,projectName:string,onSaved:(mapping:any)=>void,metaOptions:string[],acceptedMapping:string,globalMapping?:string}){
 const [stage,setStage]=useState<'configure'|'normal'>('normal');
 const [busy,setBusy]=useState(false); const [msg,setMsg]=useState('');
 const [globalConfigured,setGlobalConfigured]=useState(!!globalMapping||row.mappingStatus==='configured');
 const [saved,setSaved]=useState(!!acceptedMapping);
 const suggested=row.suggestedMeta||{};
 const [selectedMeta,setSelectedMeta]=useState(acceptedMapping||globalMapping||row.meta||suggested.meta||'');
 const plcParam=row.logicComment||'';
 const metaParam=selectedMeta||row.meta||suggested.meta||'';
 const metadataOnly=!plcParam&&!!row.metaSeq;
 // Normalise for name comparison — same logic the engine uses
 const norm=(s:string)=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
 const namesMatch=!!(plcParam&&metaParam&&norm(plcParam)===norm(metaParam));
 const engineMatched=row.mappingStatus==='matched';
 // Per-field validation chips: compare PLC side vs Metadata side
 const v={
   offset:  !!row.lo && !!row.mo   && String(row.lo).trim()!==String(row.mo).trim(),
   slno:    !!row.sl && !!row.metaSeq && String(row.sl).trim()!==String(row.metaSeq).trim(),
   dtype:   !!row.lt && !!row.mt   && norm(row.lt)!==norm(row.mt),
   gc:      !!row.gc && !!row.mg   && String(row.gc).trim()!==String(row.mg).trim(),
   sheet2:  String(row.metadataShown||'').toUpperCase()==='YES',
 };
 useEffect(()=>{
   if(acceptedMapping){setSelectedMeta(acceptedMapping);setSaved(true);}
   if(globalMapping){setSelectedMeta((vv:any)=>vv||globalMapping);setGlobalConfigured(true);}
 },[acceptedMapping,globalMapping]);
 const saveGlobal=async()=>{
   if(!plcParam||!metaParam){setStage('configure');setMsg('Select a metadata parameter to add a global mapping.');return;}
   setBusy(true);setMsg('');
   try{
     const res=await fetch('/api/knowledge/master',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plc_parameter:plcParam,plc_tag:row.plcTag||'',metadata_parameter:metaParam,status:'configured'})});
     const data=await res.json(); if(!res.ok)throw new Error(data.detail||'Could not save global mapping.');
     setGlobalConfigured(true);setStage('normal');setMsg('');
     onSaved({metadataParameter:metaParam,plcParameter:plcParam,scope:'global'});
   }catch(e:any){setMsg(e.message||'Global mapping failed.')}finally{setBusy(false)}
 };
 const saveProject=async()=>{
   if(!projectName||!plcParam||!metaParam){setMsg('No metadata mapping is available for this PLC row.');return;}
   setBusy(true);setMsg('');
   try{
     const res=await fetch('/api/knowledge/project',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_name:projectName,plc_parameter:plcParam,plc_tag:row.plcTag||'',metadata_parameter:metaParam})});
     const data=await res.json(); if(!res.ok)throw new Error(data.detail||'Could not save project mapping.');
     setSaved(true);setStage('normal');setMsg('');
     onSaved({metadataParameter:metaParam,plcParameter:plcParam,scope:'project'});
   }catch(e:any){setMsg(e.message||'Project mapping failed.')}finally{setBusy(false)}
 };
 // ── Render states ────────────────────────────────────────────────────────────
 // Metadata-only row: no PLC parameter to map from
 if(metadataOnly)return <span className="mappingState noMatch">—</span>;
 // Already accepted for this project
 if(saved)return <span className="mappingState accepted" title={`Project mapping: ${metaParam}`} onClick={e=>{e.stopPropagation();setSaved(false);}}><CheckCircle2 size={12}/>Accepted ✓</span>;
 // Global alias confirmed: show pill, still allow re-configuring
 if(globalConfigured&&!stage)return null;// handled below inside controls
 // Parameter names match exactly (or engine confirmed match) and no manual action pending
 // → hide mapping controls; other field differences appear in the Result column
 if((engineMatched||namesMatch)&&!globalConfigured)return null;
 // ── Mapping controls: only shown when parameter names differ ─────────────────
 const hasChips=Object.values(v).some(Boolean);
 return <div className="mappingControl compact" onClick={e=>e.stopPropagation()}>
   <div className="mappingTopline">
     {plcParam&&metaParam&&!namesMatch&&(
       <div className="paramMismatch"><AlertCircle size={11}/>Parameter not match</div>
     )}
     <div className="mappingSwitch" role="group" aria-label="Parameter mapping">
     <button type="button" className={'mappingSeg configure '+(globalConfigured?'configured':'')+(stage==='configure'?' active':'')} disabled={busy} onClick={()=>{if(metaParam)saveGlobal();else{setStage('configure');setMsg('');}}}>{busy?'…':globalConfigured?'Configured ✓':'Configure'}</button>
     <button type="button" className={'mappingSeg normal '+(stage==='normal'?'active':'')} disabled={busy} onClick={()=>{setStage('normal');setMsg('');}}>Normal</button>
     <button type="button" className="mappingSeg accept" disabled={busy||!projectName||!plcParam||!metaParam} onClick={saveProject}>{busy?'…':'Accept'}</button>
     </div>
   </div>
   {/* Metadata selector in configure mode */}
   {stage==='configure'&&metaOptions.length>0&&(
     <select className="metaSelect" value={selectedMeta} onChange={e=>setSelectedMeta(e.target.value)}>
       <option value="">— select metadata parameter —</option>
       {metaOptions.map((o:string)=><option key={o} value={o}>{o}</option>)}
     </select>
   )}
   {/* Per-field validation chips */}
   {hasChips&&<div className="validationChips">
     {v.offset&&<span className="vChip fail">Offset</span>}
     {v.slno&&<span className="vChip fail">Sl.No.</span>}
     {v.dtype&&<span className="vChip fail">Data Type</span>}
     {v.gc&&<span className="vChip fail">Group Code</span>}
     {v.sheet2&&<span className="vChip warn">Sheet 2 ref</span>}
   </div>}
   {msg&&<div className="mappingInlineMsg">{msg}</div>}
 </div>;
}
function MetaTable({rows,open,setOpen,columns,projectName,allRows}:{rows:any[],open:number|null,setOpen:(n:number|null)=>void,columns:MetaCol[],projectName:string,allRows:any[]}){
 // ── Load previously accepted mappings from project knowledge base ──────────
 const [acceptedMappings,setAcceptedMappings]=useState<Record<string,string>>({});
 const [masterDropdowns,setMasterDropdowns]=useState<Record<string,string[]>>({});
 const [globalMappings,setGlobalMappings]=useState<Record<string,string>>({}); 
 useEffect(()=>{
   if(projectName){
     fetch(`/api/knowledge/project?project_name=${encodeURIComponent(projectName)}`).then(r=>r.json()).then((j:any)=>{
       const m:Record<string,string>={};
       (j.mappings||[]).forEach((x:any)=>{if(x.plc_parameter&&x.metadata_parameter)m[x.plc_parameter]=x.metadata_parameter;});
       setAcceptedMappings(m);
     }).catch(()=>{});
   }
   fetch('/api/knowledge/master').then(r=>r.json()).then((j:any)=>{
     const m:Record<string,string>={};(j.mappings||[]).forEach((x:any)=>{if(x.plc_parameter&&x.metadata_parameter)m[x.plc_parameter]=x.metadata_parameter;});setGlobalMappings(m);})
     .catch(()=>{});
   fetch('/api/knowledge/master/dropdown').then(r=>r.json()).then((j:any)=>{
     const mp:Record<string,string[]>={};
     (j.mappings||[]).forEach((x:any)=>{if(x.plc_parameter&&Array.isArray(x.mapping)){const pairs=(x.mapping||[]).filter((p:any)=>p.PLCVAL!=null&&p.SHOWNVAL!=null).map((p:any)=>`${p.PLCVAL} = ${p.SHOWNVAL}`);if(pairs.length)mp[x.plc_parameter]=pairs;}});
     setMasterDropdowns(mp);}).catch(()=>{});
 },[projectName]);
 // All unique metadata parameter names across every row — fed to the dropdown
 const metaOptions=[...new Set(allRows.filter((r:any)=>r.meta).map((r:any)=>String(r.meta)))].sort() as string[];
 // Inline metadata suggestion: this is display-only and NEVER changes validation.
 // Prefer exact Group Code + Offset because those fields identify the metadata
 // record without forcing the engineer to search the whole workbook.
 const findSuggested=(r:any)=>{
   if(r.meta) return r;
   const gc=String(r.gc??''); const off=String(r.lo??'');
   const candidate=allRows.find((m:any)=>m.meta && String(m.mg??m.gc??'')===gc && String(m.mo??m.lo??'')===off);
   return candidate||{};
 };
 const visible=columns.filter(c=>c.enabled&&c.key!=='result');
 const plcKeys=['sl','plcTagCode','logicComment','gc','lt','lo','size','dropdown','hmiMin','hmiMax','valueSource','inputType']; const metaKeys=['metaSeq','metadataScreenName','metadataMachineVariants','metadataTagCode','meta','mg','mt','mo','metadataUnits','metadataMin','metadataMax','metadataShown'];
 const plcVisible=visible.filter(c=>plcKeys.includes(c.key)); const metaVisible=visible.filter(c=>metaKeys.includes(c.key));
 const render=(r:any,key:string)=>{if(key==='valueSource')return r.valueSource??'';if(key==='inputType')return r.inputType??'';if(key==='sl')return r.sl??'';if(key==='plcTagCode')return r.plcTagCode??r.sl??'';if(key==='logicComment')return r.logicComment??'';if(key==='gc')return r.gc??'';if(key==='lt')return r.lt??'';if(key==='lo')return r.lo??'';if(key==='size')return r.size??'';if(key==='dropdown')return r.hmiPairs?.length?r.hmiPairs.join(' | '):(r.dropdown?'YES':'');if(key==='hmiMin')return r.hmiMin??'';if(key==='hmiMax')return r.hmiMax??'';if(key==='metaSeq')return r.metaSeq??'';if(key==='metadataScreenName')return r.metadataScreenName??'';if(key==='metadataMachineVariants')return r.metadataMachineVariants??'';if(key==='metadataTagCode')return r.metadataTagCode??'';if(key==='meta')return r.meta??'';if(key==='mg')return r.mg??'';if(key==='mt')return r.mt??'';if(key==='mo')return r.mo??'';if(key==='metadataUnits')return r.metadataUnits??'';if(key==='metadataMin')return r.metadataMin??'';if(key==='metadataMax')return r.metadataMax??'';if(key==='metadataShown')return r.metadataShown||'';return ''};
  // Suggestions belong only to the Mapping control. The uploaded-workbook
  // columns must contain the actual matched source row; otherwise a suggested
  // row can hide the real METADATA_ONLY record and make the workbook look incomplete.
  const displayEntries=rows.map((r:any)=>({r,sm:findSuggested(r),display:r}));
  const usedMetadataLocations=new Set(displayEntries
    .filter(x=>x.r.recordType!=='METADATA_ONLY'&&x.r.metaSeq!=='')
    .map(x=>x.r.metadataSheet&&x.r.metadataRow?`${x.r.metadataSheet}::${x.r.metadataRow}`:`seq::${x.r.metaSeq}::${x.r.mg}`));
  const visibleEntries=displayEntries.filter(x=>{
    if(x.r.recordType!=='METADATA_ONLY')return true;
    const key=x.r.metadataSheet&&x.r.metadataRow?`${x.r.metadataSheet}::${x.r.metadataRow}`:`seq::${x.r.metaSeq}::${x.r.mg}`;
    return !usedMetadataLocations.has(key);
  });
 return <><thead><tr>{plcVisible.length>0&&<th colSpan={plcVisible.length}>PLC / Logic</th>}<th rowSpan={2} className="mappingHead">Mapping</th>{metaVisible.length>0&&<th colSpan={metaVisible.length}>Uploaded Metadata Workbook</th>}<th rowSpan={2}>Result</th></tr><tr>{plcVisible.map(c=><th key={c.key}>{c.label}</th>)}{metaVisible.map(c=><th key={c.key}>{c.label}</th>)}</tr></thead><tbody>{visibleEntries.map(({r,sm,display}:any)=><React.Fragment key={r.id}><tr className="data" onClick={()=>setOpen(open===r.id?null:r.id)}>{plcVisible.map(c=><td key={'p'+c.key} className={['gc','lo','lt','sl'].includes(c.key)?'mono':''}>{c.key==='dropdown'&&((r.hmiPairs?.length)||(masterDropdowns[r.logicComment||'']?.length))  ?<div className="hmiPairList">{(r.hmiPairs?.length?r.hmiPairs:(masterDropdowns[r.logicComment||'']||[])).map((p:string,pi:number)=>{    const[plcv,shv]=p.split(' = ');    return <div className="hmiPairRow" key={pi}>      <span className="hmiPlcVal">{plcv}</span>      <span className="hmiEq">=</span>      <span className="hmiShVal">{shv??''}</span>    </div>;})}  {!r.hmiPairs?.length&&masterDropdowns[r.logicComment||'']?.length&&<div className="masterDdBadge">Global</div>}  </div>  :render(r,c.key)}{c.key==='logicComment'&&r.logicComment&&display.meta&&String(r.logicComment).trim().toLowerCase()!==String(display.meta).trim().toLowerCase()&&<div className="plcActualSmall">PLC actual: {r.logicComment}</div>}</td>)}<td className="mappingCell"><MappingToggle row={{...r,suggestedMeta:sm}} projectName={projectName} metaOptions={metaOptions} acceptedMapping={acceptedMappings[r.logicComment||'']||''} globalMapping={globalMappings[r.logicComment||'']||''} onSaved={(mapping:any)=>{if(mapping.scope==='global')setGlobalMappings(prev=>({...prev,[mapping.plcParameter]:mapping.metadataParameter}));else setAcceptedMappings(prev=>({...prev,[mapping.plcParameter]:mapping.metadataParameter}))}}/></td>{metaVisible.map(c=><td key={'m'+c.key} className={['mg','mo','mt','metaSeq'].includes(c.key)?'mono metadataInlineCell':''}>{c.key==='metadataShown'&&(display.hmiPairs?.length||(masterDropdowns[display.logicComment||'']?.length&&String(display.metadataShown||'').toUpperCase()==='YES'))  ?<div className="hmiPairList">    {(display.hmiPairs?.length?display.hmiPairs:(masterDropdowns[display.logicComment||'']||[])).map((p:string,pi:number)=>{      const[plcv,shv]=p.split(' = ');      return <div className="hmiPairRow" key={pi}>        <span className="hmiPlcVal">{plcv}</span>        <span className="hmiEq">=</span>        <span className="hmiShVal">{shv??''}</span>      </div>;})}  </div>  :render(display,c.key)}</td>)}<td><ResultIndicator status={r.status} onDetails={()=>setOpen(open===r.id?null:r.id)}/></td></tr>{open===r.id&&<tr className="detail"><td colSpan={plcVisible.length+1+metaVisible.length+1}><div className="detailSplit"><div className="detailPane"><div className="detailPaneTitle">PLC Logic</div><Detail k="PLC Parameter" v={r.logicComment||'Not available'}/><Detail k="PLC TAG_CODE" v={display.plcTagCode||display.sl||'Not available'} mono/><Detail k="PLC Tag / variable" v={r.plcTag||'Not available'} mono/><Detail k="Value Source" v={r.valueSource||'Logic data'}/><Detail k="Input Type" v={r.inputType||'Used only in logic, not in screen'}/>{r.hmiPairs?.length  ?<><div className="detailKey">HMI Dropdown values</div>    <div className="hmiPairListDetail">    {r.hmiPairs.map((p:string,pi:number)=>{      const[plcv,shv]=p.split(' = ');      return <div className="hmiPairRow" key={pi}>        <span className="hmiPlcVal">{plcv}</span>        <span className="hmiEq">=</span>        <span className="hmiShVal">{shv??''}</span>      </div>;    })}</div></>  :<Detail k="HMI Dropdown" v={r.dropdown?'YES':'—'}/>}<Detail k="HMI Min" v={r.hmiMin||'Not available'} mono/><Detail k="HMI Max" v={r.hmiMax||'Not available'} mono/><Detail k="PLC source" v={r.logicSourceFile?`${r.logicSourceFile}${r.logicLineNumber!==''?` : line ${r.logicLineNumber}`:''}`:'Not available'} mono/></div><div className="detailPane"><div className="detailPaneTitle">Metadata</div><Detail k="S.No. (A)" v={display.metaSeq||'Not available'} mono/><Detail k="TAG_CODE (H)" v={display.metadataTagCode||'Not available'} mono/><Detail k="Parameter (D)" v={display.meta||'Not available'}/><Detail k="Group Code (I)" v={display.mg||'Not available'} mono/><Detail k="Offset (J)" v={display.mo||'Not available'} mono/><Detail k="Data Type (M)" v={display.mt||'Not available'} mono/><Detail k="UNITS (E)" v={display.metadataUnits||'Not available'}/><Detail k="MIN (F)" v={display.metadataMin??'Not available'} mono/><Detail k="MAX (G)" v={display.metadataMax??'Not available'} mono/><Detail k="IS_SHOWN_VALUE_DIFFERENT (X)" v={display.metadataShown||'Not available'}/><Detail k="Metadata location" v={display.metadataSheet?`${display.metadataSheet}${display.metadataRow?` : row ${display.metadataRow}`:''}`:'Not available'} mono/><div className="suggestionNote">Inline metadata is a display suggestion only; it does not create or change a mapping.</div></div></div>{r.status&&r.status!=='pass'&&<div className="validationIssuesPanel"><div className="viTitle">Validation Issues &amp; Recommendations</div><div className="viGrid">{display.logicComment&&display.meta&&String(display.logicComment||"").trim().toLowerCase()!==String(display.meta||"").trim().toLowerCase()&&<div className="viRow"><span className="viLabel">Parameter name</span><span className="viPlc">{display.logicComment||"—"}</span><span className="viArrow">≠</span><span className="viMeta">{display.meta||"—"}</span><ChopperRecommendation text={"Use Configure to create a global alias, or Accept for this project."}/></div>}{display.lo&&display.mo&&String(display.lo)!==String(display.mo)&&<div className="viRow"><span className="viLabel">Offset (J)</span><span className="viPlc">PLC: {display.lo}</span><span className="viArrow">≠</span><span className="viMeta">Meta: {display.mo}</span><ChopperRecommendation text={"PLC offset and metadata offset do not match. Check the PLC offset and metadata column J."}/></div>}{display.lt&&display.mt&&String(display.lt||"").toUpperCase()!==String(display.mt||"").toUpperCase()&&<div className="viRow"><span className="viLabel">Data Type (M)</span><span className="viPlc">PLC: {display.lt}</span><span className="viArrow">≠</span><span className="viMeta">Meta: {display.mt}</span><ChopperRecommendation text={"PLC data type and metadata data type do not match. Check the PLC type and metadata column M."}/></div>}{display.gc&&display.mg&&String(display.gc)!==String(display.mg)&&<div className="viRow"><span className="viLabel">Group Code (I)</span><span className="viPlc">PLC: {display.gc}</span><span className="viArrow">≠</span><span className="viMeta">Meta: {display.mg}</span><ChopperRecommendation text={"PLC group code and metadata group code do not match. Check the PLC group assignment and metadata Group Code."}/></div>}{display.sl&&display.metaSeq&&String(display.sl)!==String(display.metaSeq)&&<div className="viRow"><span className="viLabel">S.No. (A)</span><span className="viPlc">PLC seq: {display.sl}</span><span className="viArrow">≠</span><span className="viMeta">Meta: {display.metaSeq}</span><ChopperRecommendation text={"PLC S.L.No. (TAG_CODE) and metadata S.No. do not match. Check PLC TAG_CODE and metadata column A."}/></div>}{String(display.metadataShown||"").toUpperCase()==="YES"&&<div className="viRow sheet2"><span className="viLabel">IS_SHOWN_VALUE_DIFFERENT (X)</span><span className="viMeta">YES — HMI shows a different display value (Sheet 2 reference)</span><ChopperRecommendation text={"Verify the HMI TextGroup Sheet 2 mapping matches the intended display value. Check the Dropdown tab for PLCVAL \u2194 SHOWNVAL pairs."}/></div>}{r.root&&<div className="viRow engine"><span className="viLabel">Engine finding</span><span className="viMeta">{r.root}</span></div>}{r.fix&&<div className="viRow engine fix"><span className="viLabel">Recommended fix</span><span className="viMeta">{r.fix}</span></div>}</div></div>}</td></tr>}</React.Fragment>)}</tbody></>}

function DropTable({rows,open,setOpen}:any){return <><thead><tr><th colSpan={5}>PLC / HMI</th><th colSpan={5}>Uploaded Metadata Workbook</th></tr><tr><th>Group Code</th><th>Parameter (PLC Comment)</th><th>TAG_CODE</th><th>HMI PLCVAL</th><th>HMI SHOWNVAL</th><th>Metadata S No.</th><th>Metadata Parameter</th><th>Metadata PLCVAL</th><th>Metadata SHOWNVAL</th><th>Result</th></tr></thead><tbody>{rows.map((r:any)=><React.Fragment key={r.id}><tr className="data" onClick={()=>setOpen(open===r.id?null:r.id)}><td>{r.gc}</td><td>{r.comment||'—'}</td><td className="mono">{r.tag}</td><td>{r.hmi.map((x:string,i:number)=><span className="valuePill" key={i}>{x.split(' = ')[0]}</span>)}</td><td>{r.hmi.slice(0,4).map((x:string,i:number)=><div key={i}>{x.split(' = ')[1]??x}</div>)}</td><td>{r.metaSeq||'—'}</td><td className="mono">{r.metaParam||'—'}</td><td>{r.meta.map((x:string,i:number)=><span className="valuePill" key={i}>{x.split(' = ')[0]}</span>)}</td><td>{r.meta.slice(0,4).map((x:string,i:number)=><div key={i}>{x.split(' = ')[1]??x}</div>)}</td><td><Badge status={r.status}/><div className="subtle">{r.reason}</div></td></tr>{open===r.id&&<tr className="detail"><td colSpan={10}><div className="detailGrid"><Detail k="PLC / HMI Group Code" v={r.gc} mono/><Detail k="Parameter (PLC comment)" v={r.comment||'No PLC comment found.'}/><Detail k="TAG_CODE" v={r.tag} mono/><Detail k="HMI TextGroup values" v={r.hmi.join('\n')} mono/><Detail k="Metadata serial number" v={r.metaSeq||'Not available'} mono/><Detail k="Metadata parameter" v={r.metaParam||'Not available'} mono/><Detail k="Metadata values" v={r.meta.join('\n')} mono/><Detail k="Metadata match method" v={r.matchMethod||'Not found'}/><Detail k="PLC source" v={r.source?`${r.source}${r.line!==''?` : line ${r.line}`:''}`:'Not available'} mono/><Detail k="Root cause" v={r.root||'Review HMI TextGroup and uploaded metadata mapping.'}/><div className="detailBlock full"><ChopperRecommendation text={r.fix||'Compare the HMI text-group entries with the uploaded metadata for this parameter. Review the expected values before changing either source.'}/></div></div></td></tr>}</React.Fragment>)}</tbody></>}
function ResultIndicator({status,onDetails}:{status:Status,onDetails:()=>void}){
 if(status==='pass')return <span className="resultIcon pass" title="Pass"><CheckCircle2 size={15}/></span>;
 if(status==='warn')return <button type="button" className="resultCompact warn" onClick={e=>{e.stopPropagation();onDetails()}} title="Warning — view details"><AlertTriangle size={14}/><span>View details</span></button>;
 return <button type="button" className="resultCompact fail" onClick={e=>{e.stopPropagation();onDetails()}} title="Fail — view details"><XCircle size={14}/><span>View details</span></button>;
}
