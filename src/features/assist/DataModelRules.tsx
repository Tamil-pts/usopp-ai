import {ChangeEvent,useEffect,useMemo,useState} from 'react';
import {Bot,Download,FileUp,Plus,RefreshCw,Save,Table2,Trash2,Upload, WandSparkles} from 'lucide-react';
import {requestChopper} from './chopperRequest';
import {userStorage} from '../../shared/userStorage';

type JsonRecord=Record<string,unknown>;
type ModelSummary={id:string;service:string;department:string;originalSource:string;modelFile:string;parameterCount:number;collectionCount:number;revision:string};
type ModelDocument=ModelSummary&{collections:Record<string,JsonRecord[]>;canEdit:boolean};
const SOURCE_FIELDS=['Service','Department','JSON collection'];
const BASE_FIELDS=['tagName','dataType','groupCode','tdEngineKey','mongoKey','formula','type','isRequired'];
const EMPTY_RECORD:JsonRecord={tagName:'New parameter',dataType:'FLOAT',groupCode:'',tdEngineKey:null,mongoKey:null,formula:null,type:'instant',isRequired:true};

function columnsFor(rows:JsonRecord[]){return [...BASE_FIELDS,...new Set(rows.flatMap(row=>Object.keys(row)).filter(key=>!BASE_FIELDS.includes(key)))];}
function csvCell(value:unknown){const text=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);return /[",\r\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text;}
function toCsv(rows:JsonRecord[],columns:string[]){return [columns.map(csvCell).join(','),...rows.map(row=>columns.map(key=>csvCell(row[key])).join(','))].join('\r\n');}
function parseCsv(input:string):string[][]{
 const rows:string[][]=[];let row:string[]=[],cell='',quoted=false;
 for(let i=0;i<input.length;i++){
  const char=input[i];
  if(quoted){if(char==='"'&&input[i+1]==='"'){cell+='"';i++}else if(char==='"')quoted=false;else cell+=char;continue}
  if(char==='"'&&!cell)quoted=true;
  else if(char===','){row.push(cell);cell=''}
  else if(char==='\n'||char==='\r'){if(char==='\r'&&input[i+1]==='\n')i++;row.push(cell);rows.push(row);row=[];cell=''}
  else cell+=char;
 }
 if(quoted)throw new Error('CSV has an unclosed quoted field.');
 if(cell.length||row.length){row.push(cell);rows.push(row)}
 return rows.filter(item=>item.some(value=>value.trim()));
}
function parseCsvRecords(input:string[],existing:JsonRecord[],scope?:string[]):JsonRecord[]{
 const rows=parseCsv(input.join(''));if(rows.length<2)throw new Error('CSV needs a header row and at least one data row.');
 const headers=rows[0].map(value=>value.trim());if(!headers.includes('tagName'))throw new Error('CSV must include the exact tagName column.');
 if(headers.some(value=>!value)||new Set(headers).size!==headers.length)throw new Error('CSV column names must be present and unique.');
 if(rows.length>30001)throw new Error('CSV can contain at most 30,000 mappings.');
 const contextColumns=SOURCE_FIELDS.map(key=>headers.indexOf(key));
 const hasContext=contextColumns.some(index=>index>=0);
 if(hasContext&&(!scope||contextColumns.some(index=>index<0)))throw new Error('CSV source columns must include Service, Department and JSON collection.');
 const sample=existing[0]||EMPTY_RECORD;
 return rows.slice(1).map((cells,index)=>{
  if(hasContext&&contextColumns.some((column,index)=>(cells[column]||'').trim()!==scope![index]))throw new Error(`Row ${index+2}: CSV source does not match the selected service, department and collection. Filter the export to one collection before importing it.`);
  const record:JsonRecord={};headers.forEach((csvHeader,column)=>{
   if(hasContext&&contextColumns.includes(column))return;
   const header=hasContext&&csvHeader.startsWith('JSON field: ')&&SOURCE_FIELDS.includes(csvHeader.slice(12))?csvHeader.slice(12):csvHeader;
   const raw=(cells[column]||'').trim();const previous=sample[header];
   if(raw===''&&(previous===null||previous===undefined)){record[header]=null;return}
   if(typeof previous==='boolean'||header==='isRequired'){
    if(!/^(true|false|1|0|yes|no)$/i.test(raw))throw new Error(`Row ${index+2}: ${header} must be true or false.`);
    record[header]=/^(true|1|yes)$/i.test(raw);return;
   }
   if(typeof previous==='number'){
    const value=Number(raw);if(raw!==''&&!Number.isFinite(value))throw new Error(`Row ${index+2}: ${header} must be numeric.`);
    record[header]=raw===''?null:value;return;
   }
   record[header]=raw===''&&['formula','tdEngineKey','mongoKey'].includes(header)?null:raw;
  });
  if(!String(record.tagName??'').trim())throw new Error(`Row ${index+2}: tagName is required.`);
  return record;
 });
}
function downloadCsv(name:string,contents:string){const blob=new Blob([contents],{type:'text/csv;charset=utf-8'});const href=URL.createObjectURL(blob);const link=document.createElement('a');link.href=href;link.download=name;link.click();URL.revokeObjectURL(href);}


type SourceRow={source:ModelDocument;collection:string;index:number;row:JsonRecord};
type SourceColumn={key:string;label:string;value:(entry:SourceRow)=>unknown};
const PAGE_SIZE=100;
const sourceColumns:SourceColumn[]=[
 {key:'@service',label:'Service',value:entry=>entry.source.service},
 {key:'@department',label:'Department',value:entry=>entry.source.department},
 {key:'@collection',label:'JSON collection',value:entry=>entry.collection},
];
function sourceRows(sources:ModelDocument[]):SourceRow[]{
 return sources.flatMap(source=>Object.entries(source.collections).flatMap(([collection,rows])=>rows.map((row,index)=>({source,collection,index,row}))));
}
function exportRows(rows:SourceRow[]){
 const fields=columnsFor(rows.map(entry=>entry.row));
 // Keep provenance separate from JSON fields, including identically named fields.
 const headers=[...SOURCE_FIELDS,...fields.map(field=>SOURCE_FIELDS.includes(field)?'JSON field: '+field:field)];
 return [headers.map(csvCell).join(','),...rows.map(entry=>[
  entry.source.service,entry.source.department,entry.collection,...fields.map(field=>entry.row[field]),
 ].map(csvCell).join(','))].join('\r\n');
}
function displayValue(value:unknown){return value==null?'':typeof value==='object'?JSON.stringify(value):String(value);}

export function DataModelRules({active}:{active:boolean}){
 const [sources,setSources]=useState<ModelDocument[]>([]),[canEdit,setCanEdit]=useState(false),[document,setDocument]=useState<ModelDocument|null>(null);
 const [service,setService]=useState(''),[department,setDepartment]=useState(''),[collection,setCollection]=useState(''),[initialized,setInitialized]=useState(false);
 const [draftCollections,setDraftCollections]=useState<Record<string,JsonRecord[]>>({}),[savedCollections,setSavedCollections]=useState('');
 const [editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[search,setSearch]=useState('');
 const [columnFilters,setColumnFilters]=useState<Record<string,string>>({}),[page,setPage]=useState(1);
 const [csvOpen,setCsvOpen]=useState(false),[csvText,setCsvText]=useState(''),[chopperOpen,setChopperOpen]=useState(false),[chopperQuestion,setChopperQuestion]=useState(''),[chopperAnswer,setChopperAnswer]=useState(''),[chopperBusy,setChopperBusy]=useState(false);
 const dirty=Boolean(document)&&JSON.stringify(draftCollections)!==savedCollections;
 const canEditCollection=canEdit&&Boolean(document&&collection);
 const rows=draftCollections[collection]||[];
 const currentSources=useMemo(()=>sources.map(source=>source.id===document?.id?{...source,collections:draftCollections}:source),[sources,document,draftCollections]);
 const allRows=useMemo(()=>sourceRows(currentSources),[currentSources]);
 const scopedRows=useMemo(()=>allRows.filter(entry=>(!service||entry.source.service===service)&&(!department||entry.source.department===department)&&(!collection||entry.collection===collection)),[allRows,service,department,collection]);
 const columns=useMemo(()=>columnsFor(scopedRows.map(entry=>entry.row)),[scopedRows]);
 const tableColumns=useMemo(()=>[...sourceColumns,...columns.map(key=>({key,label:key,value:(entry:SourceRow)=>entry.row[key]}))],[columns]);
 const visible=useMemo(()=>scopedRows.filter(entry=>{
  if(search&&!JSON.stringify([entry.source.service,entry.source.department,entry.collection,entry.row]).toLocaleLowerCase().includes(search.toLocaleLowerCase()))return false;
  return tableColumns.every(column=>!columnFilters[column.key]||displayValue(column.value(entry)).toLocaleLowerCase().includes(columnFilters[column.key].toLocaleLowerCase()));
 }),[scopedRows,search,tableColumns,columnFilters]);
 const pageCount=Math.max(1,Math.ceil(visible.length/PAGE_SIZE)),currentPage=Math.min(page,pageCount);
 const pageRows=visible.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE);
 const departments=[...new Set(sources.filter(source=>!service||source.service===service).map(source=>source.department))].sort();
 const collections=[...new Set(currentSources.filter(source=>(!service||source.service===service)&&(!department||source.department===department)).flatMap(source=>Object.keys(source.collections)))].sort();

 const setScope=(items:ModelDocument[],nextService:string,nextDepartment:string,nextCollection:string)=>{
  const matching=items.filter(source=>(!nextService||source.service===nextService)&&(!nextDepartment||source.department===nextDepartment));
  const selected=nextService&&nextDepartment?matching[0]:null;
  setService(nextService);setDepartment(nextDepartment);setCollection(nextCollection);
  setDocument(selected||null);setDraftCollections(selected?.collections||{});setSavedCollections(JSON.stringify(selected?.collections||{}));
  setEditing(false);setSearch('');setColumnFilters({});setPage(1);setChopperOpen(false);setCsvOpen(false);setNotice('');setError('');
  if(selected)userStorage.setItem('usopp_json_key_model_v1',selected.id);
  userStorage.setItem('usopp_json_key_scope_v1',JSON.stringify({service:nextService,department:nextDepartment,collection:nextCollection}));
 };
 const allowDiscard=()=>!dirty||window.confirm('Discard unsaved JSON Key changes before changing sources?');
 const changeScope=(nextService:string,nextDepartment:string,nextCollection:string)=>{
  if(!allowDiscard())return;
  if(nextService!==service||nextDepartment!==department)nextCollection='';
  const serviceSources=currentSources.filter(source=>!nextService||source.service===nextService);
  if(nextDepartment&&!serviceSources.some(source=>source.department===nextDepartment))nextDepartment='';
  const matches=serviceSources.filter(source=>!nextDepartment||source.department===nextDepartment);
  if(nextCollection&&!matches.some(source=>nextCollection in source.collections))nextCollection='';
  setScope(sources,nextService,nextDepartment,nextCollection);
 };
 const loadList=async()=>{
  if(!allowDiscard())return;setBusy(true);setError('');
  try{
   const response=await fetch('/api/knowledge/data-model-json-keys/all',{cache:'no-store'});
   const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not load the original JSON Key files.');
   const items:ModelDocument[]=result.sources||[];setSources(items);setCanEdit(result.canEdit===true);
   if(!items.length)throw new Error('No PMS, QMS or CMS JSON Key files are installed.');
   let nextService=service,nextDepartment=department,nextCollection=collection;
   if(!initialized){
    const normalize=(value:string)=>value.toLowerCase().replace(/[^a-z]/g,'');
    const preferredDepartment=normalize(userStorage.getItem('usopp_machine_department_v1')||'');
    const selected=items.find(item=>item.id===userStorage.getItem('usopp_json_key_model_v1'))||
     items.find(item=>item.service==='PMS'&&normalize(item.department)===preferredDepartment&&item.parameterCount>0)||
     items.find(item=>item.service==='PMS'&&item.parameterCount>0)||items.find(item=>item.parameterCount>0)||items[0];
    nextService=selected.service;nextDepartment=selected.department;
    nextCollection=Object.entries(selected.collections).find(([,records])=>records.length)?.[0]||Object.keys(selected.collections)[0]||'';
    try{
     const saved=JSON.parse(userStorage.getItem('usopp_json_key_scope_v1')||'null');
     if(saved&&['service','department','collection'].every(key=>typeof saved[key]==='string')){
      nextService=items.some(item=>item.service===saved.service)?saved.service:'';
      nextDepartment=items.some(item=>(!nextService||item.service===nextService)&&item.department===saved.department)?saved.department:'';
      nextCollection=items.some(item=>(!nextService||item.service===nextService)&&(!nextDepartment||item.department===nextDepartment)&&saved.collection in item.collections)?saved.collection:'';
     }
    }catch{/* An old preference cannot block the source table. */}
   }else{
    if(nextService&&!items.some(item=>item.service===nextService))nextService='';
    if(nextDepartment&&!items.some(item=>(!nextService||item.service===nextService)&&item.department===nextDepartment))nextDepartment='';
    if(nextCollection&&!items.some(item=>(!nextService||item.service===nextService)&&(!nextDepartment||item.department===nextDepartment)&&nextCollection in item.collections))nextCollection='';
   }
   setScope(items,nextService,nextDepartment,nextCollection);setInitialized(true);
  }catch(reason){setSources([]);setDocument(null);setDraftCollections({});setError(reason instanceof Error?reason.message:'Could not load JSON Key files.')}
  finally{setBusy(false)}
 };
 useEffect(()=>{if(active&&!initialized)void loadList()},[active]);
 useEffect(()=>{setPage(1)},[search,columnFilters,service,department,collection]);

 const updateRow=(index:number,key:string,value:unknown)=>setDraftCollections(current=>({...current,[collection]:current[collection].map((row,rowIndex)=>rowIndex===index?{...row,[key]:value}:row)}));
 const addRow=()=>{setDraftCollections(current=>({...current,[collection]:[...(current[collection]||[]),{...EMPTY_RECORD}]}));setNotice('Added a new JSON Key row. Complete its fields before saving.')};
 const removeRow=(index:number)=>{if(!window.confirm('Delete this mapping from the selected JSON Key collection?'))return;setDraftCollections(current=>({...current,[collection]:current[collection].filter((_,rowIndex)=>rowIndex!==index)}))};
 const addColumn=()=>{const key=window.prompt('New JSON field name (for example: displayUnit):');const clean=key?.trim();if(!clean)return;if(columns.includes(clean)||SOURCE_FIELDS.includes(clean)){setError('That field already exists or is used for source information.');return}setDraftCollections(current=>({...current,[collection]:current[collection].map(row=>({...row,[clean]:''}))}));setError('')};
 const save=async()=>{
  if(!document||!canEditCollection)return;setBusy(true);setError('');setNotice('');
  try{
   const response=await fetch('/api/knowledge/data-model-json-keys/'+encodeURIComponent(document.id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:document.revision,collections:draftCollections})});
   const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not save JSON Key changes.');
   const next=result as ModelDocument;setDocument(next);setDraftCollections(next.collections);setSavedCollections(JSON.stringify(next.collections));setSources(items=>items.map(item=>item.id===next.id?next:item.originalSource===next.originalSource?{...item,revision:next.revision}:item));setEditing(false);
   setNotice('Saved '+next.originalSource+'. KnowHub and DataInspect will now use this source.');
  }catch(reason){setError(reason instanceof Error?reason.message:'Could not save JSON Key changes.')}
  finally{setBusy(false)}
 };
 const importCsv=(text:string)=>{
  if(!document||!collection)return;
  try{
   const imported=parseCsvRecords([text],rows,[document.service,document.department,collection]);
   if(!window.confirm('Replace the '+rows.length+' rows in '+collection+' with '+imported.length+' CSV rows?'))return;
   setDraftCollections(current=>({...current,[collection]:imported}));setCsvOpen(false);setCsvText('');setEditing(true);setNotice('Loaded '+imported.length+' rows from CSV. Save Changes to publish them.');setError('');
  }catch(reason){setError(reason instanceof Error?reason.message:'Could not read this CSV.')}
 };
 const browseCsv=(event:ChangeEvent<HTMLInputElement>)=>{const file=event.target.files?.[0];event.target.value='';if(!file)return;if(!file.name.toLocaleLowerCase().endsWith('.csv')){setError('Choose a CSV file.');return}void file.text().then(importCsv).catch(()=>setError('Could not read the selected CSV file.'))};
 const askChopper=async()=>{
  if(!document||!collection||!chopperQuestion.trim())return;
  setChopperBusy(true);setChopperAnswer('');setError('');const controller=new AbortController();
  try{const result=await requestChopper({task:'KnowHub JSON Key configuration guidance',question:chopperQuestion,context:{projectName:document.service+' '+document.department+' database JSON Key',jsonKeySource:document.originalSource,collection,jsonKeyRecords:rows.slice(0,20),configurationGuidance:'Explain the fields and suggest review steps. Do not invent server schema values or change the source file.'}},controller.signal,()=>{});const reply=(result as any)?.result?.answer||(result as any)?.answer||'Chopper returned no text response.';setChopperAnswer(String(reply))}
  catch(reason){setError(reason instanceof Error?reason.message:'Chopper could not prepare guidance.')}
  finally{setChopperBusy(false)}
 };

 return <section className="card knowledgeTableCard dataModelRulesCard">
  <div className="widgetHead"><div><h3><Table2 size={17}/> Database JSON Keys</h3><p>Edit the original server key definitions from the PMS, QMS and CMS data-model folders. Changes are shared with KnowHub and DataInspect.</p></div><span className="muted">{canEdit?'Administrator access':'Read only'}</span></div>
  <p className="muted">Source: <code>{document?.originalSource||'PMS / QMS / CMS JSON Key files'}</code> · {scopedRows.length} entries in the selected scope</p>
  <div className="dataModelSourceToolbar">
   <button className="btn primary" disabled={!document||!collection||busy} onClick={()=>{setChopperOpen(value=>!value);setChopperAnswer('')}}><WandSparkles size={14}/>Configure with Chopper</button>
   <button className="btn" disabled={!canEditCollection||busy} aria-pressed={editing} onClick={()=>setEditing(value=>!value)}><Table2 size={14}/>{editing?'Finish editing':'Edit table'}</button>
   <button className="btn" disabled={busy} onClick={()=>void loadList()}><RefreshCw size={14}/>Reload</button>
   <button className="btn" disabled={!document||!collection||busy} onClick={()=>downloadCsv(document!.service+'_'+document!.department+'_empty_template.csv',toCsv([],columnsFor([])))}><Download size={14}/>Export empty template</button>
   <button className="btn" disabled={!visible.length||busy} onClick={()=>downloadCsv('JSON_Keys_'+(service||'All_services')+'_'+(department||'All_departments')+'.csv',exportRows(visible))}><Download size={14}/>Export data (CSV)</button>
   <button className="btn" disabled={!allRows.length||busy} onClick={()=>downloadCsv('JSON_Keys_All.csv',exportRows(allRows))}><Download size={14}/>Export all (CSV)</button>
   <button className="btn" disabled={!canEditCollection||busy} onClick={()=>{setCsvOpen(true);setCsvText('')}}><Upload size={14}/>Import CSV</button>
   <label className="btn" aria-disabled={!canEditCollection||busy}><FileUp size={14}/>Browse This PC (CSV)<input type="file" accept=".csv,text/csv" disabled={!canEditCollection||busy} onChange={browseCsv}/></label>
  </div>
  <div className="dataModelSourceSelectors">
   <label>Service<select value={service} onChange={event=>changeScope(event.target.value,department,collection)} disabled={busy||!sources.length}><option value="">All services</option>{[...new Set(sources.map(source=>source.service))].sort().map(value=><option key={value}>{value}</option>)}</select></label>
   <label>Department<select value={department} onChange={event=>changeScope(service,event.target.value,collection)} disabled={busy||!sources.length}><option value="">All departments</option>{departments.map(value=><option key={value}>{value}</option>)}</select></label>
   <label>JSON collection<select value={collection} onChange={event=>changeScope(service,department,event.target.value)} disabled={busy||!sources.length}><option value="">All JSON collections</option>{collections.map(value=><option key={value}>{value}</option>)}</select></label>
   <button className="btn" disabled={busy} onClick={()=>void loadList()}><RefreshCw size={14}/>Reload sources</button>
  </div>
  {error&&<p className="failText" role="alert">{error}</p>}{notice&&<p className="dataModelSourceNotice" role="status">{notice}</p>}
  {chopperOpen&&<div className="dataModelChopperPanel"><div className="widgetHead"><div><h4><Bot size={16}/> Configure with Chopper</h4><p>Ask for guidance on the selected source and collection. Chopper will not edit or publish JSON values.</p></div><button className="btn" onClick={()=>setChopperOpen(false)}>Close</button></div><label>What should Chopper help configure?<textarea value={chopperQuestion} onChange={event=>setChopperQuestion(event.target.value)} placeholder="Explain a field, review a mapping, or describe the change you want to make." rows={2}/></label><button className="btn primary" disabled={chopperBusy||!chopperQuestion.trim()} onClick={()=>void askChopper()}><Bot size={14}/>{chopperBusy?'Asking Chopper…':'Ask Chopper'}</button>{chopperAnswer&&<div className="dataModelChopperAnswer">{chopperAnswer}</div>}</div>}
  {sources.length>0&&<>
   <div className="dataModelSourceTableHeading"><div><b>{collection||'All JSON collections'}</b><span>{visible.length} of {scopedRows.length} entries · Export data follows filters; Export all includes every source.</span></div><label>Search<input value={search} onChange={event=>setSearch(event.target.value)} placeholder="Find tagName, group code, or database key"/></label>{(search||Object.values(columnFilters).some(Boolean))&&<button className="btn" onClick={()=>{setSearch('');setColumnFilters({})}}>Clear search and column filters</button>}</div>
   {editing&&canEditCollection&&<div className="dataModelEditActions"><button className="btn" disabled={busy} onClick={addRow}><Plus size={14}/>Add mapping</button><button className="btn" disabled={busy} onClick={addColumn}><Plus size={14}/>Add field</button></div>}
   <div className="knowledgeTableScroll dataModelJsonKeyTable" tabIndex={0} aria-label="Database JSON Key records"><table className="table"><thead><tr>{tableColumns.map(column=><th key={column.key}><span>{column.label}</span><input type="search" aria-label={'Filter '+column.label} placeholder="Filter…" value={columnFilters[column.key]||''} onChange={event=>setColumnFilters(current=>({...current,[column.key]:event.target.value}))}/></th>)}{editing&&canEditCollection&&<th>Actions</th>}</tr></thead><tbody>
    {pageRows.map(entry=><tr key={entry.source.id+':'+entry.collection+':'+entry.index}>
     {sourceColumns.map(column=><td key={column.key}>{displayValue(column.value(entry))}</td>)}
     {columns.map(key=><td key={key}>{editing&&canEditCollection?typeof entry.row[key]==='boolean'||key==='isRequired'?<input type="checkbox" aria-label={key+' row '+(entry.index+1)} checked={entry.row[key]===true} onChange={event=>updateRow(entry.index,key,event.target.checked)}/>:typeof entry.row[key]==='number'?<input className="dataModelCellInput" type="number" aria-label={key+' row '+(entry.index+1)} value={entry.row[key] as number} onChange={event=>updateRow(entry.index,key,event.target.value===''?null:Number(event.target.value))}/>:<input className="dataModelCellInput" aria-label={key+' row '+(entry.index+1)} value={displayValue(entry.row[key])} placeholder={entry.row[key]===null?'null':''} onChange={event=>updateRow(entry.index,key,event.target.value)}/>:entry.row[key]==null?<span className="muted">—</span>:displayValue(entry.row[key])}</td>)}
     {editing&&canEditCollection&&<td><button type="button" className="btn dataModelDeleteRow" disabled={busy} aria-label={'Delete '+String(entry.row.tagName||'mapping')} onClick={()=>removeRow(entry.index)}><Trash2 size={14}/>Delete</button></td>}
    </tr>)}
   </tbody></table>{!visible.length&&<p>No JSON Key records match these filters.</p>}</div>
   <div className="dataModelSourcePagination"><span>{visible.length?'Showing '+((currentPage-1)*PAGE_SIZE+1)+'–'+Math.min(currentPage*PAGE_SIZE,visible.length)+' of '+visible.length+' records':'0 records'}</span><div><button className="btn" disabled={currentPage===1} onClick={()=>setPage(currentPage-1)}>Previous page</button><span>Page {currentPage} of {pageCount}</span><button className="btn" disabled={currentPage===pageCount} onClick={()=>setPage(currentPage+1)}>Next page</button></div></div>
   {canEdit&&!canEditCollection&&<p className="muted">Select one service, department and JSON collection to edit or import records.</p>}
   {document&&<div className="dataModelSourceFooter">{dirty&&<button className="btn" disabled={busy} onClick={()=>{setDraftCollections(document.collections);setSavedCollections(JSON.stringify(document.collections));setEditing(false);setError('');setNotice('Draft changes discarded.')}}>Discard changes</button>}<button className="btn primary" disabled={!canEditCollection||!dirty||busy} onClick={()=>void save()}><Save size={14}/>{busy?'Saving…':'Save Changes'}</button></div>}
  </>}
  {!sources.length&&<div className="dataModelSourceEmpty"><Table2 size={24}/><b>{busy?'Loading JSON Key table…':error?'JSON Key table could not be loaded':'No JSON Key sources available'}</b><span>{busy?'Reading the PMS, QMS and CMS JSON files.':'The table uses the original JSON Key files for each service and department.'}</span></div>}
  {!canEdit&&sources.length>0&&<p className="muted">Only an administrator can import, edit or save the shared JSON Key files.</p>}
  {csvOpen&&<div className="dataModelCsvDialog" role="dialog" aria-modal="true" aria-label="Import JSON Key CSV"><div className="dataModelCsvDialogCard"><h4>Import CSV into {collection}</h4><p>Import one collection at a time. Source columns, when present, must match the selected filters.</p><textarea value={csvText} onChange={event=>setCsvText(event.target.value)} placeholder="Paste CSV with tagName and the original JSON field names" aria-label="CSV contents"/><div className="actions"><button className="btn" onClick={()=>setCsvOpen(false)}>Cancel</button><button className="btn primary" disabled={!csvText.trim()} onClick={()=>importCsv(csvText)}>Import CSV</button></div></div></div>}
 </section>;
}
