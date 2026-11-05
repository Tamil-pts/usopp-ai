import {useEffect,useMemo,useRef,useState,type PointerEvent,type KeyboardEvent} from 'react';
import {Expand,Minimize2,MoveDiagonal2} from 'lucide-react';
import {MissingSheet2Dialog,qualityDescription,useMetadataQuality,type QualityState,type QualityFocus} from './MetadataQuality';
import {MetadataRenameDialog,type MetadataRename} from './MetadataRenameDialog';

type Sheet={name:string;headers:string[];rows:Record<string,any>[]};
type DataModelParameter={name?:string;tagName?:string;canonicalName?:string;aliases?:string[];tdEngineKey?:string;mongoKey?:string;dataType?:string;groupCodes?:unknown[];groupCode?:unknown;groupCodeSource?:string;kind?:string;sheet?:string;source?:string;ignoreNameSeparators?:boolean;required?:boolean};
type DataModel={id:string;service:string;serviceName?:string;machine:string;parameters:DataModelParameter[]};
type CoverageRow={key:string;name:string;dataType:string;group:string;module:string;status:'Available'|'Missing';generated:string;required:boolean};

const normalizedHeader=(value:string)=>String(value||'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const groupHeaders=new Set(['groupcode','group','groupid']);
const parameterHeaders=new Set(['parameters','parameter','parametername']);
const offsetHeaders=new Set(['offsetfromthestartofthegroupinbytes','offset','byteoffset','offsetinbytes']);
const normalizeGroup=(value:unknown)=>{
  const raw=String(value??'').trim();
  if(!raw)return '';
  const numeric=Number(raw);
  return Number.isFinite(numeric)?String(numeric):raw.toLowerCase();
};
const normalizeParameter=(value:unknown,ignoreSeparators:boolean)=>{
  const raw=String(value??'').trim().toLowerCase().replace(/\s+/g,' ');
  return ignoreSeparators?raw.replace(/[\s_]+/g,''):raw;
};
const namesFor=(parameter:DataModelParameter)=>[parameter.name,parameter.tagName,parameter.canonicalName,...(parameter.aliases||[]),parameter.tdEngineKey,parameter.mongoKey].map(v=>String(v||'').trim()).filter(Boolean);

export function WorkbookViewer({path,sessionId,source,projectName,machineDepartment,onUse,referenceSessionId,onQualityChange,qualityFocus}:{path?:string;sessionId?:string;source:'generated'|'uploaded';projectName:string;machineDepartment?:string;onUse?:(path:string,name:string)=>void;referenceSessionId?:string;onQualityChange?:(state:QualityState)=>void;qualityFocus?:QualityFocus}) {
  const [sheets,setSheets]=useState<Sheet[]>([]);
  const [active,setActive]=useState(0);
  const [workbook,setWorkbook]=useState('');
  const [edit,setEdit]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [download,setDownload]=useState('');
  const [offerMasterMapping,setOfferMasterMapping]=useState(true);
  const [rename,setRename]=useState<MetadataRename|null>(null);
  const renameOpen=useRef(false);
  const sourceWorkbook=useRef('');
  const cellBeforeEdit=useRef<{sheet:number;row:number;column:string;value:string}|null>(null);
  const [groupFilter,setGroupFilter]=useState('');
  const [duplicateFilter,setDuplicateFilter]=useState<'all'|'duplicate'|'unique'>('all');
  const [offsetFilter,setOffsetFilter]=useState('all');
  const [qualityNotice,setQualityNotice]=useState('bytes');
  const [referenceError,setReferenceError]=useState('');const seenReferenceError=useRef('');
  const [coverageOpen,setCoverageOpen]=useState(false);
  const [models,setModels]=useState<DataModel[]>([]);
  const [modelId,setModelId]=useState('');
  const [modelsBusy,setModelsBusy]=useState(false);
  const [modelsError,setModelsError]=useState('');
  const [coverageGroup,setCoverageGroup]=useState('');
  const [coverageModule,setCoverageModule]=useState('');
  const [coverageStatus,setCoverageStatus]=useState('all');
  const [coverageSearch,setCoverageSearch]=useState('');
  const [coverageExpanded,setCoverageExpanded]=useState(false);
  const [coverageSize,setCoverageSize]=useState<{width?:number;height?:number}>({});
  const coveragePanel=useRef<HTMLElement>(null);
  const resizeOrigin=useRef<{x:number;y:number;width:number;height:number}|null>(null);
  const qualityReference=referenceSessionId||(source==='generated'?sessionId:undefined);
  const quality=useMetadataQuality({workbookPath:workbook,sheets,source,referenceSessionId:qualityReference,modelId,machineDepartment});
  useEffect(()=>{onQualityChange?.({...quality,dirty})},[quality,onQualityChange,dirty]);

  useEffect(()=>{
    let cancelled=false;
    setSheets([]);setActive(0);setDirty(false);setEdit(false);setDownload('');setWorkbook('');setGroupFilter('');setDuplicateFilter('all');
    sourceWorkbook.current='';cellBeforeEdit.current=null;renameOpen.current=false;setRename(null);
    if(!path&&!sessionId){setMessage('Select a metadata workbook or generate one from the project.');return}
    setBusy(true);setMessage('Loading workbook…');
    fetch('/api/metadata/view/sheets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path,sessionId,source})})
      .then(async r=>{const j=await r.json();if(!r.ok)throw new Error(j.detail||'Cannot open workbook');return j})
      .then(j=>{if(!cancelled){setSheets(j.sheets);setWorkbook(j.workbookPath);sourceWorkbook.current=j.workbookPath;setMessage('Edits are saved to a new workbook copy.')}})
      .catch(e=>{if(!cancelled)setMessage(e.message)})
      .finally(()=>{if(!cancelled)setBusy(false)});
    return()=>{cancelled=true};
  },[path,sessionId,source]);

  useEffect(()=>{
    if(!sheets.length)return;
    if(!machineDepartment||machineDepartment.trim().toLowerCase()==='all'){
      setModels([]);setModelId('');setModelsBusy(false);setModelsError('Choose a machine / department before comparing its Data Model.');return;
    }
    let cancelled=false;
    setModelsBusy(true);setModelsError('');setModels([]);setModelId('');
    fetch(`/api/nami/data-models?machine=${encodeURIComponent(machineDepartment)}&include_parameters=true&fixed_only=true`)
      .then(async r=>{const j=await r.json();if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:'Cannot load Data Models');return j})
      .then((items:DataModel[])=>{if(!cancelled){const fixed=Array.isArray(items)?items:[];setModels(fixed);setModelId(fixed.find(item=>item.service==='PMS')?.id||fixed[0]?.id||'');if(!fixed.length)setModelsError('No fixed Data Models were found for this machine / department.')}})
      .catch(e=>{if(!cancelled)setModelsError(e.message)})
      .finally(()=>{if(!cancelled)setModelsBusy(false)});
    return()=>{cancelled=true};
  },[sheets.length,source,machineDepartment]);
  useEffect(()=>{
    if(quality.loading||!quality.report)return;
    const missing=quality.report.stages.find(stage=>stage.id==='sheet2')?.issues.filter(issue=>issue.check==='Missing Sheet2 mapping')||[];
    const key=JSON.stringify([workbook,missing]);
    if(!missing.length){seenReferenceError.current='';setReferenceError('');return;}
    if(seenReferenceError.current===key)return;seenReferenceError.current=key;
    setReferenceError(missing.slice(0,20).map(issue=>`TAG_CODE ${issue.tagCode} ? GC ${issue.groupCode} ? ${issue.sheet} row ${issue.row}: ${issue.parameter}`).join('\n')+'\nIS_SHOWN_VALUE_DIFFERENT=YES requires valid PLCVAL/SHOWNVAL rows for the same tag and machine variant.');
  },[quality.report,quality.loading,workbook]);
  useEffect(()=>{
    if(!qualityFocus)return;
    setQualityNotice(qualityFocus.stage);
    if(qualityFocus.stage==='bytes'){setDuplicateFilter('all');setOffsetFilter(quality.report?.stages.find(stage=>stage.id==='bytes')?.issues.length?'issues':'all');const main=sheets.findIndex(sheet=>normalizedHeader(sheet.name)!=='sheet2');if(main>=0)setActive(main)}
    if(qualityFocus.stage==='duplicates'){setOffsetFilter('all');setDuplicateFilter('duplicate');const main=sheets.findIndex(sheet=>normalizedHeader(sheet.name)!=='sheet2');if(main>=0)setActive(main)}
    if(qualityFocus.stage==='sheet2'){const index=sheets.findIndex(sheet=>normalizedHeader(sheet.name)==='sheet2');if(index>=0)setActive(index)}
    if(qualityFocus.stage==='dataModel')setCoverageOpen(true);
    document.getElementById(`metadata-workbook-${source}`)?.scrollIntoView({block:'start',behavior:'smooth'});
  },[qualityFocus]);

  useEffect(()=>{if(!dirty)return;const guard=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard)},[dirty]);
  useEffect(()=>{setGroupFilter('');if(normalizedHeader(sheets[active]?.name||'')==='sheet2')setDuplicateFilter('all')},[active]);

  const update=(row:number,key:string,value:string)=>{
    setSheets(ss=>ss.map((s,i)=>i===active?{...s,rows:s.rows.map((r,n)=>n===row?{...r,[key]:value}:r)}:s));setDirty(true);
  };
  const beginCellEdit=(row:number,column:string,value:string)=>{
    cellBeforeEdit.current={sheet:active,row,column,value};
  };
  const finishCellEdit=(row:number,column:string,value:string)=>{
    const before=cellBeforeEdit.current;cellBeforeEdit.current=null;
    if(!offerMasterMapping||renameOpen.current||!before||before.sheet!==active||before.row!==row||before.column!==column||before.value===value||!value.trim()||!parameterHeaders.has(normalizedHeader(column))||normalizedHeader(sheets[active].name)==='sheet2')return;
    renameOpen.current=true;
    setRename({sheet:active,row,column,oldName:before.value,newName:value,payload:{workbookPath:sourceWorkbook.current,source,referenceSessionId:qualityReference,sheetName:sheets[active].name,rowNumber:row+2,row:{...sheets[active].rows[row],[column]:value}}});
  };
  const closeRename=()=>{renameOpen.current=false;setRename(null)};
  const acceptRename=(name:string)=>{
    if(!rename)return;
    setSheets(previous=>previous.map((sheet,index)=>index===rename.sheet?{...sheet,rows:sheet.rows.map((row,index)=>index===rename.row?{...row,[rename.column]:name}:row)}:sheet));
    setDirty(true);setMessage('Master parameter mapping saved. Save a workbook copy to keep this edit; future metadata generation will use the approved name.');closeRename();
  };
  const save=async(exportFile=false)=>{
    if(renameOpen.current)return;
    setBusy(true);
    try{
      const r=await fetch('/api/metadata/view/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workbookPath:workbook,projectName,sheets,source,referenceSessionId:qualityReference})});
      const j=await r.json();if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:j.detail?.message+' '+(j.detail?.cells||[]).map((c:any)=>`${c.sheet}!${c.cell}: ${c.value}`).join('; ')||'Save failed');
      setWorkbook(j.workbookPath);setDownload(j.downloadUrl);setDirty(false);setEdit(false);setMessage('Saved all worksheets to '+j.fileName);
      if(exportFile){const link=document.createElement('a');link.href=j.downloadUrl;link.download=j.fileName;link.click()}
    }catch(e:any){setMessage(e.message);if(e.message.includes('Missing Sheet2 reference:'))setReferenceError(e.message)}finally{setBusy(false)}
  };

  const sheet=sheets[active];
  const offsetByRow=useMemo(()=>new Map((quality.report?.offsetRows||[]).map(row=>[`${row.sheet}:${row.row}`,row])),[quality.report]);
  const duplicateInfo=useMemo(()=>{
    const rows=new Set<number>();
    if(!sheet)return {rows,groupHeader:'',parameterHeader:''};
    if(normalizedHeader(sheet.name)==='sheet2')return {rows,groupHeader:'',parameterHeader:''};
    const groupHeader=sheet.headers.find(h=>groupHeaders.has(normalizedHeader(h)))||'';
    const parameterHeader=sheet.headers.find(h=>parameterHeaders.has(normalizedHeader(h)))||'';
    if(!groupHeader||!parameterHeader)return {rows,groupHeader,parameterHeader};
    const buckets=new Map<string,number[]>();
    sheet.rows.forEach((row,index)=>{
      const group=normalizeGroup(row[groupHeader]);
      const parameter=normalizeParameter(row[parameterHeader],false);
      if(!group||!parameter)return;
      const key=`${group}\u0000${parameter}`;
      buckets.set(key,[...(buckets.get(key)||[]),index]);
    });
    buckets.forEach(indexes=>{if(indexes.length>1)indexes.forEach(index=>rows.add(index))});
    return {rows,groupHeader,parameterHeader};
  },[sheet]);

  const groupOptions=useMemo(()=>{
    if(!sheet||!duplicateInfo.groupHeader)return [];
    return [...new Set(sheet.rows.map(row=>normalizeGroup(row[duplicateInfo.groupHeader])).filter(Boolean))].sort((a,b)=>Number(a)-Number(b));
  },[sheet,duplicateInfo.groupHeader]);
  const visibleRows=useMemo(()=>sheet?.rows.map((row,index)=>({row,index})).filter(({row,index})=>{
    if(groupFilter&&normalizeGroup(row[duplicateInfo.groupHeader])!==groupFilter)return false;
    if(duplicateFilter==='duplicate'&&!duplicateInfo.rows.has(index))return false;
    if(duplicateFilter==='unique'&&duplicateInfo.rows.has(index))return false;
    if(offsetFilter!=='all'&&normalizedHeader(sheet.name)!=='sheet2'){
      const status=offsetByRow.get(`${sheet.name}:${index+2}`)?.status;
      if(offsetFilter==='issues'&&status!=='FAIL'&&status!=='REVIEW')return false;
      if(offsetFilter!=='issues'&&status!==offsetFilter)return false;
    }
    return true;
  })||[],[sheet,groupFilter,duplicateFilter,duplicateInfo,offsetFilter,offsetByRow]);

  const model=models.find(model=>model.id===modelId);
  const coverage=useMemo(()=>{
    if(!model)return {rows:[] as CoverageRow[],excluded:0};
    const generated=sheets.flatMap(candidate=>{
      if(normalizedHeader(candidate.name)==='sheet2')return [];
      const groupHeader=candidate.headers.find(h=>groupHeaders.has(normalizedHeader(h)))||'';
      const parameterHeader=candidate.headers.find(h=>parameterHeaders.has(normalizedHeader(h)))||'';
      if(!groupHeader||!parameterHeader)return [];
      return candidate.rows.map(row=>({group:normalizeGroup(row[groupHeader]),name:String(row[parameterHeader]??'').trim(),sheet:candidate.name})).filter(row=>row.group&&row.name);
    });
    const output:CoverageRow[]=[];let excluded=0;
    for(const parameter of model.parameters||[]){
      const groups=(Array.isArray(parameter.groupCodes)?parameter.groupCodes:[]).map(normalizeGroup).filter(Boolean);
      if(parameter.kind==='server'||parameter.kind==='formula'||!groups.length){excluded++;continue}
      const aliases=namesFor(parameter);
      const compact=parameter.ignoreNameSeparators===true;
      const normalizedNames=new Set(aliases.map(name=>normalizeParameter(name,compact)));
      for(const group of groups){
        const found=generated.filter(item=>item.group===group&&normalizedNames.has(normalizeParameter(item.name,compact)));
        output.push({key:`${parameter.sheet||parameter.source||'module'}:${group}:${parameter.name||parameter.tagName}:${output.length}`,name:parameter.name||parameter.tagName||parameter.canonicalName||'',dataType:parameter.dataType||'',group,module:parameter.sheet||parameter.source||'Unspecified module',status:found.length?'Available':'Missing',generated:found.map(item=>`${item.name} (${item.sheet})`).join(', ')||'—',required:parameter.required!==false});
      }
    }
    return {rows:output,excluded};
  },[model,sheets]);
  const coverageModules=useMemo(()=>[...new Set(coverage.rows.map(row=>row.module))].sort(),[coverage.rows]);
  const coverageGroups=useMemo(()=>[...new Set(coverage.rows.map(row=>row.group))].sort((a,b)=>Number(a)-Number(b)),[coverage.rows]);
  const visibleCoverage=useMemo(()=>{
    const search=coverageSearch.trim().toLowerCase();
    return coverage.rows.filter(row=>(!coverageGroup||row.group===coverageGroup)&&(!coverageModule||row.module===coverageModule)&&(coverageStatus==='all'||row.status===coverageStatus)&&(!search||`${row.name} ${row.generated} ${row.dataType} ${row.module} ${row.group}`.toLowerCase().includes(search)));
  },[coverage.rows,coverageGroup,coverageModule,coverageStatus,coverageSearch]);
  const availableCount=coverage.rows.filter(row=>row.status==='Available').length;
  const missingCount=coverage.rows.filter(row=>row.status==='Missing').length;
  const resizeCoverage=(width:number,height:number)=>{
    const panel=coveragePanel.current;if(!panel)return;
    const parent=panel.parentElement;
    const style=parent?getComputedStyle(parent):null;
    const available=parent?parent.clientWidth-parseFloat(style?.paddingLeft||'0')-parseFloat(style?.paddingRight||'0'):width;
    setCoverageSize({width:Math.max(Math.min(360,available),Math.min(available,width)),height:Math.max(380,height)});
    setCoverageExpanded(false);
  };
  const startResize=(event:PointerEvent<HTMLButtonElement>)=>{
    const panel=coveragePanel.current;if(!panel)return;
    event.preventDefault();const bounds=panel.getBoundingClientRect();
    resizeOrigin.current={x:event.clientX,y:event.clientY,width:bounds.width,height:bounds.height};
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveResize=(event:PointerEvent<HTMLButtonElement>)=>{
    const origin=resizeOrigin.current;if(!origin)return;
    resizeCoverage(origin.width+event.clientX-origin.x,origin.height+event.clientY-origin.y);
  };
  const keyboardResize=(event:KeyboardEvent<HTMLButtonElement>)=>{
    const panel=coveragePanel.current;if(!panel||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    event.preventDefault();const bounds=panel.getBoundingClientRect();
    resizeCoverage(bounds.width+(event.key==='ArrowRight'?20:event.key==='ArrowLeft'?-20:0),bounds.height+(event.key==='ArrowDown'?20:event.key==='ArrowUp'?-20:0));
  };

  return <section id={`metadata-workbook-${source}`} className="card workbookViewer">
    <MissingSheet2Dialog message={referenceError} onClose={()=>setReferenceError('')} onReview={()=>{setReferenceError('');const index=sheets.findIndex(sheet=>normalizedHeader(sheet.name)==='sheet2');if(index>=0)setActive(index);setEdit(true);}}/>
    <div className="panelHead"><div><h2>{source==='generated'?'MetaWorks · Generated':'MetaWorks · Uploaded / selected'}</h2><p>{sheet?.rows.length||0} rows · {sheets.length} worksheets{dirty?' · Unsaved edits':''}</p></div>
      <div className="actions"><button className="btn" disabled={busy||!sheet} onClick={()=>{if(!renameOpen.current)setEdit(!edit)}}>{edit?'Finish editing':'Edit'}</button><button className="btn" disabled={busy||!dirty} onClick={()=>save()}>Save copy</button><button className="btn primary" disabled={busy||!sheet} onClick={()=>save(true)}>Export XLSX</button>{download&&<a className="btn" href={download}>Download saved copy</a>}{onUse&&workbook&&<button className="btn" disabled={dirty||busy} onClick={()=>onUse(workbook,workbook.split(/[\\/]/).pop()||'Metadata')}>Use for validation</button>}</div></div>
    <p role="status">{message}</p>
    {edit&&<label className="metadataMasterOffer"><input type="checkbox" checked={offerMasterMapping} onChange={event=>setOfferMasterMapping(event.target.checked)}/> Offer to save parameter renames to master</label>}
    <div className="featureTabs">{sheets.map((s,i)=><button className={'chip '+(active===i?'active':'')} key={s.name} onClick={()=>setActive(i)}>{s.name}</button>)}</div>
    <div className="metadataCoverageToggle"><label><input type="checkbox" checked={coverageOpen} onChange={e=>setCoverageOpen(e.target.checked)}/> Compare with Data Model</label><div className="metadataCoverageActions"><button className="btn" disabled={!sheet} onClick={()=>{setCoverageOpen(true);setCoverageExpanded(true);setCoverageSize({})}}><Expand size={14}/>Expand all</button><button className="btn" disabled={!coverageOpen} onClick={()=>{setCoverageOpen(false);setCoverageExpanded(false)}}><Minimize2 size={14}/>Collapse</button><span>{machineDepartment||'Machine / department not set'}</span></div></div>
    {coverageOpen&&<section ref={coveragePanel} className={`metadataCoverage${coverageExpanded?' isExpanded':''}`} style={{width:coverageSize.width||'100%',height:coverageExpanded?'auto':coverageSize.height||'min(720px,85vh)'}} aria-label="Data Model coverage">
      <div className="metadataCoverageHead"><div><h3>Data Model parameter coverage</h3><p>Compare parameters within each Group Code, grouped by Data Model module.</p></div>
        <label>Data Model<select className="textInput" value={modelId} disabled={modelsBusy||!models.length} onChange={e=>{setModelId(e.target.value);setCoverageGroup('');setCoverageModule('');setCoverageStatus('all');setCoverageSearch('')}}>{models.map(item=><option key={item.id} value={item.id}>{item.service}{item.serviceName?` · ${item.serviceName}`:''}</option>)}</select></label>
      </div>
      {modelsBusy&&<p role="status">Loading Data Models…</p>}{modelsError&&<p role="status">{modelsError}</p>}
      {model&&<>
        <div className="metadataCoverageStats"><div><b>{availableCount}</b><span>Available in {source} metadata</span></div><div><b>{missingCount}</b><span>Missing from {source} metadata</span></div><div><b>{coverage.excluded}</b><span>Host-generated / formula / ungrouped</span></div></div>
        <div className="metadataCoverageFilters">
          <label>Group Code<select className="textInput" value={coverageGroup} onChange={e=>setCoverageGroup(e.target.value)}><option value="">All Group Codes</option>{coverageGroups.map(group=><option key={group} value={group}>GC {group}</option>)}</select></label>
          <label>Module<select className="textInput" value={coverageModule} onChange={e=>setCoverageModule(e.target.value)}><option value="">All modules</option>{coverageModules.map(module=><option key={module} value={module}>{module}</option>)}</select></label>
          <label>Status<select className="textInput" value={coverageStatus} onChange={e=>setCoverageStatus(e.target.value)}><option value="all">Available and missing</option><option value="Available">Available</option><option value="Missing">Missing</option></select></label>
          <label>Find parameter<input className="textInput" value={coverageSearch} onChange={e=>setCoverageSearch(e.target.value)} placeholder="Name, type or module"/></label>
        </div>
        <div className="tableWrap workbookScroll"><table className="table"><thead><tr><th>Group Code</th><th>Module</th><th>Data Model parameter</th><th>Data type</th><th>Status</th><th>{source==='generated'?'Generated':'Uploaded'} parameter</th></tr></thead><tbody>{visibleCoverage.map(row=><tr key={row.key}><td>GC {row.group}</td><td>{row.module}</td><td>{row.name}{row.required?'':' (optional)'}</td><td>{row.dataType||'—'}</td><td><span className={`metadataCoverageStatus ${row.status.toLowerCase()}`}>{row.status}</span></td><td>{row.generated}</td></tr>)}{!visibleCoverage.length&&<tr><td colSpan={6}>No Data Model parameters match these filters.</td></tr>}</tbody></table></div>
        <p className="metadataCoverageNote">Name matching is case-insensitive and follows each Data Model parameter’s separator rule. Server-generated and formula fields are excluded from PLC coverage.</p>
      </>}
      <button type="button" className="metadataCoverageResizeHandle" title="Drag to resize, or use arrow keys" aria-label="Resize Data Model panel" onPointerDown={startResize} onPointerMove={moveResize} onPointerUp={()=>{resizeOrigin.current=null}} onPointerCancel={()=>{resizeOrigin.current=null}} onLostPointerCapture={()=>{resizeOrigin.current=null}} onKeyDown={keyboardResize}><MoveDiagonal2 size={18}/></button>
    </section>}
    {duplicateInfo.rows.size>0&&<div className="metadataDuplicateNotice">Purple rows are duplicate Parameters inside the same Group Code. {duplicateInfo.rows.size} rows are affected on this worksheet.</div>}
    <div className="metadataWorkbookFilters">
      <label>Group Code<select className="textInput" value={groupFilter} onChange={e=>setGroupFilter(e.target.value)}><option value="">All Group Codes</option>{groupOptions.map(group=><option key={group} value={group}>GC {group}</option>)}</select></label>
      <label>Duplicate status<select className="textInput" value={duplicateFilter} onChange={e=>setDuplicateFilter(e.target.value as 'all'|'duplicate'|'unique')}><option value="all">All parameters</option><option value="duplicate">Duplicates only</option><option value="unique">Non-duplicates only</option></select></label>
      <label>Offset verification<select className="textInput" value={offsetFilter} disabled={normalizedHeader(sheet?.name||'')==='sheet2'} onChange={e=>setOffsetFilter(e.target.value)}><option value="all">All offsets</option><option value="issues">Findings only</option><option value="FAIL">Failed</option><option value="REVIEW">Needs review</option><option value="PASS">Workbook OK</option></select></label>
      <span>{visibleRows.length} of {sheet?.rows.length||0} rows</span>
    </div>
    {quality.error&&<p className="failText" role="alert">{quality.error}</p>}
    {quality.report&&<p className="metadataQualityNote" role="status">{quality.loading?'Checking current workbook…':quality.report.stages.find(stage=>stage.id===qualityNotice)?.detail} Offset findings highlight existing cells in OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES; hover a highlighted cell for expected and actual values.</p>}
    <div className="tableWrap workbookScroll"><table className="table"><thead><tr>{sheet?.headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{visibleRows.map(({row,index})=>{const duplicate=duplicateInfo.rows.has(index);const offsetQuality=offsetByRow.get(`${sheet?.name}:${index+2}`);const finding=offsetQuality&&offsetQuality.status!=='PASS';return <tr key={index} className={`${duplicate?'metadataDuplicateRow ':''}${finding?'metadataOffsetIssueRow':''}`} title={[duplicate?`Duplicate Parameter inside Group Code ${row[duplicateInfo.groupHeader]}`:'',qualityDescription(offsetQuality)].filter(Boolean).join(' ')}>{(sheet?.headers||[]).map((h,column)=><td key={h} className={finding&&offsetHeaders.has(normalizedHeader(h))?`metadataOffset${offsetQuality.status==='FAIL'?'Fail':'Review'}Cell`:undefined} title={offsetHeaders.has(normalizedHeader(h))?qualityDescription(offsetQuality):undefined}>{duplicate&&column===0&&<span className="metadataDuplicateBadge">Duplicate in GC {String(row[duplicateInfo.groupHeader]??'')}</span>}{edit?<input aria-label={`${h}, row ${index+2}`} className="metadataEditInput" value={row[h]??''} onFocus={e=>beginCellEdit(index,h,e.target.value)} onBlur={e=>finishCellEdit(index,h,e.target.value)} onChange={e=>update(index,h,e.target.value)}/>:String(row[h]??'')}</td>)}</tr>})}{!visibleRows.length&&<tr><td colSpan={sheet?.headers.length||1}>No rows match these filters.</td></tr>}</tbody></table></div>
    {rename&&<MetadataRenameDialog rename={rename} onClose={closeRename} onSaved={acceptRename}/>}
  </section>;
}
