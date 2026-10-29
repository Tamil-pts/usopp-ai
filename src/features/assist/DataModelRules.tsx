import {ChangeEvent,useEffect,useMemo,useState} from 'react';
import {Bot,Download,FileUp,Plus,RefreshCw,Save,Table2,Trash2,Upload, WandSparkles} from 'lucide-react';
import {requestChopper} from './chopperRequest';
import {userStorage} from '../../shared/userStorage';

type JsonRecord=Record<string,unknown>;
type ModelSummary={id:string;service:string;department:string;originalSource:string;modelFile:string;parameterCount:number;collectionCount:number;revision:string};
type ModelDocument=ModelSummary&{collections:Record<string,JsonRecord[]>;canEdit:boolean};
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
function parseCsvRecords(input:string[],existing:JsonRecord[]):JsonRecord[]{
 const rows=parseCsv(input.join(''));if(rows.length<2)throw new Error('CSV needs a header row and at least one data row.');
 const headers=rows[0].map(value=>value.trim());if(!headers.includes('tagName'))throw new Error('CSV must include the exact tagName column.');
 if(headers.some(value=>!value)||new Set(headers).size!==headers.length)throw new Error('CSV column names must be present and unique.');
 if(rows.length>30001)throw new Error('CSV can contain at most 30,000 mappings.');
 const sample=existing[0]||EMPTY_RECORD;
 return rows.slice(1).map((cells,index)=>{
  const record:JsonRecord={};headers.forEach((header,column)=>{
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

export function DataModelRules({active}:{active:boolean}){
 const [models,setModels]=useState<ModelSummary[]>([]),[canEdit,setCanEdit]=useState(false),[selectedId,setSelectedId]=useState(''),[document,setDocument]=useState<ModelDocument|null>(null);
 const [collection,setCollection]=useState(''),[draftCollections,setDraftCollections]=useState<Record<string,JsonRecord[]>>({}),[savedCollections,setSavedCollections]=useState('');
 const [editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[search,setSearch]=useState('');
 const [csvOpen,setCsvOpen]=useState(false),[csvText,setCsvText]=useState(''),[chopperOpen,setChopperOpen]=useState(false),[chopperQuestion,setChopperQuestion]=useState(''),[chopperAnswer,setChopperAnswer]=useState(''),[chopperBusy,setChopperBusy]=useState(false);
 const dirty=Boolean(document)&&JSON.stringify(draftCollections)!==savedCollections;
 const rows=draftCollections[collection]||[];
 const columns=useMemo(()=>columnsFor(rows),[rows]);
 const visible=useMemo(()=>rows.map((row,index)=>({row,index})).filter(({row})=>JSON.stringify(row).toLocaleLowerCase().includes(search.toLocaleLowerCase())),[rows,search]);

 const loadModel=async(id=selectedId)=>{
  if(!id)return;setBusy(true);setError('');setNotice('');setDocument(null);setEditing(false);
  try{const response=await fetch(`/api/knowledge/data-model-json-keys/${encodeURIComponent(id)}`,{cache:'no-store'});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not load that JSON Key file.');const next=result as ModelDocument;setDocument(next);setCanEdit(next.canEdit===true);setDraftCollections(next.collections);setSavedCollections(JSON.stringify(next.collections));setCollection(id===document?.id&&next.collections[collection]?collection:Object.entries(next.collections).find(([,records])=>records.length)?.[0]||Object.keys(next.collections)[0]||'')}
  catch(reason){setError(reason instanceof Error?reason.message:'Could not load that JSON Key file.')}
  finally{setBusy(false)}
 };
 const loadList=async()=>{
  setBusy(true);setError('');
  try{
   const response=await fetch('/api/knowledge/data-model-json-keys',{cache:'no-store'});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not load the original JSON Key files.');
   const items:ModelSummary[]=result.models||[];setModels(items);setCanEdit(result.canEdit===true);
   const normalize=(value:string)=>value.toLowerCase().replace(/[^a-z]/g,'');
   const department=normalize(userStorage.getItem('usopp_machine_department_v1')||'');
   const saved=selectedId||userStorage.getItem('usopp_json_key_model_v1');
   const selected=items.find(item=>item.id===saved)||items.find(item=>item.service==='PMS'&&normalize(item.department)===department&&item.parameterCount>0)||items.find(item=>item.service==='PMS'&&item.parameterCount>0)||items.find(item=>item.parameterCount>0)||items[0];
   if(selected){setSelectedId(selected.id);userStorage.setItem('usopp_json_key_model_v1',selected.id);await loadModel(selected.id)}
   else{setSelectedId('');setDocument(null);setDraftCollections({});setCollection('');setError('No PMS, QMS or CMS JSON Key files are installed.')}
  }
  catch(reason){setError(reason instanceof Error?reason.message:'Could not load JSON Key files.')}
  finally{setBusy(false)}
 };
 const selectModel=(id:string)=>{
  setSelectedId(id);setSearch('');
  if(id){userStorage.setItem('usopp_json_key_model_v1',id);void loadModel(id)}
  else{setDocument(null);setDraftCollections({});setCollection('')}
 };
 const selectedModel=models.find(model=>model.id===selectedId);
 useEffect(()=>{if(active&&models.length===0)void loadList()},[active]);

 const updateRow=(index:number,key:string,value:unknown)=>setDraftCollections(current=>({...current,[collection]:current[collection].map((row,rowIndex)=>rowIndex===index?{...row,[key]:value}:row)}));
 const addRow=()=>{setDraftCollections(current=>({...current,[collection]:[...(current[collection]||[]),{...EMPTY_RECORD}]}));setNotice('Added a new JSON Key row. Complete its fields before saving.')};
 const removeRow=(index:number)=>{if(!window.confirm('Delete this mapping from the selected JSON Key collection?'))return;setDraftCollections(current=>({...current,[collection]:current[collection].filter((_,rowIndex)=>rowIndex!==index)}))};
 const addColumn=()=>{const key=window.prompt('New JSON field name (for example: displayUnit):');const clean=key?.trim();if(!clean)return;if(columns.includes(clean)){setError('That field already exists in this collection.');return}setDraftCollections(current=>({...current,[collection]:current[collection].map(row=>({...row,[clean]:''}))}));setError('')};
 const save=async()=>{
  if(!document)return;setBusy(true);setError('');setNotice('');
  try{const response=await fetch(`/api/knowledge/data-model-json-keys/${encodeURIComponent(document.id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:document.revision,collections:draftCollections})});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not save JSON Key changes.');const next=result as ModelDocument;setDocument(next);setDraftCollections(next.collections);setSavedCollections(JSON.stringify(next.collections));setModels(items=>items.map(item=>item.id===next.id?{...item,revision:next.revision,parameterCount:Object.values(next.collections).reduce((total,value)=>total+value.length,0),collectionCount:Object.keys(next.collections).length}:item));setEditing(false);setNotice(`Saved ${next.originalSource}. KnowHub and DataInspect will now use this source.`)}
  catch(reason){setError(reason instanceof Error?reason.message:'Could not save JSON Key changes.')}
  finally{setBusy(false)}
 };
 const importCsv=(text:string)=>{
  if(!document||!collection)return;
  try{const imported=parseCsvRecords([text],rows);if(!window.confirm(`Replace the ${rows.length} rows in ${collection} with ${imported.length} CSV rows?`))return;setDraftCollections(current=>({...current,[collection]:imported}));setCsvOpen(false);setCsvText('');setEditing(true);setNotice(`Loaded ${imported.length} rows from CSV. Save Changes to publish them.`);setError('')}
  catch(reason){setError(reason instanceof Error?reason.message:'Could not read this CSV.')}
 };
 const browseCsv=(event:ChangeEvent<HTMLInputElement>)=>{const file=event.target.files?.[0];event.target.value='';if(!file)return;if(!file.name.toLocaleLowerCase().endsWith('.csv')){setError('Choose a CSV file.');return}void file.text().then(importCsv).catch(()=>setError('Could not read the selected CSV file.'))};
 const askChopper=async()=>{
  if(!document||!collection||!chopperQuestion.trim())return;
  setChopperBusy(true);setChopperAnswer('');setError('');const controller=new AbortController();
  try{const result=await requestChopper({task:'KnowHub JSON Key configuration guidance',question:chopperQuestion,context:{projectName:`${document.service} ${document.department} database JSON Key`,jsonKeySource:document.originalSource,collection,jsonKeyRecords:rows.slice(0,20),configurationGuidance:'Explain the fields and suggest review steps. Do not invent server schema values or change the source file.'}},controller.signal,()=>{});const reply=(result as any)?.result?.answer||(result as any)?.answer||'Chopper returned no text response.';setChopperAnswer(String(reply))}
  catch(reason){setError(reason instanceof Error?reason.message:'Chopper could not prepare guidance.')}
  finally{setChopperBusy(false)}
 };

 return <section className="card knowledgeTableCard dataModelRulesCard">
  <div className="widgetHead"><div><h3><Table2 size={17}/> Database JSON Keys</h3><p>Edit the original server key definitions from the PMS, QMS and CMS data-model folders. Changes are shared with KnowHub and DataInspect.</p></div><span className="muted">{canEdit?'Administrator editing':'Read only'}</span></div>
  <p className="muted">Source: <code>{document?.originalSource||'knowledge/data_models/reference_sources'}</code>{document&&<> · Project department: <b>{document.department}</b> · {document.parameterCount} entries in this department</>}</p>
  <div className="dataModelSourceToolbar">
   <button className="btn primary" disabled={!document||!collection||busy} onClick={()=>{setChopperOpen(value=>!value);setChopperAnswer('')}}><WandSparkles size={14}/>Configure with Chopper</button>
   <button className="btn" disabled={!canEdit||!document||busy} aria-pressed={editing} onClick={()=>setEditing(value=>!value)}><Table2 size={14}/>{editing?'Finish editing':'Edit table'}</button>
   <button className="btn" disabled={busy} onClick={()=>void loadList()}><RefreshCw size={14}/>Reload</button>
   <button className="btn" disabled={!document||!collection} onClick={()=>downloadCsv(`${document?.service}_${document?.department}_empty_template.csv`,toCsv([],columnsFor([])))}><Download size={14}/>Export empty template</button>
   <button className="btn" disabled={!document||!collection} onClick={()=>downloadCsv(`${document?.service}_${document?.department}_${collection}.csv`,toCsv(rows,columns))}><Download size={14}/>Export data (CSV)</button>
   <button className="btn" disabled={!canEdit||!document||!collection||busy} onClick={()=>{setCsvOpen(true);setCsvText('')}}><Upload size={14}/>Import CSV</button>
   <label className="btn" aria-disabled={!canEdit||!document||!collection||busy}><FileUp size={14}/>Browse This PC (CSV)<input type="file" accept=".csv,text/csv" disabled={!canEdit||!document||!collection||busy} onChange={browseCsv}/></label>
  </div>
  <div className="dataModelSourceSelectors">
   <label>Service<select value={selectedModel?.service||''} onChange={event=>{const item=models.find(model=>model.service===event.target.value&&model.department===selectedModel?.department)||models.find(model=>model.service===event.target.value);selectModel(item?.id||'')}} disabled={busy||!models.length}><option value="">Select service</option>{['PMS','QMS','CMS'].map(service=><option key={service}>{service}</option>)}</select></label>
   <label>Department<select value={selectedId} onChange={event=>selectModel(event.target.value)} disabled={busy||!models.length}><option value="">Select department and JSON Key source</option>{models.filter(model=>!selectedModel||model.service===selectedModel.service).map(model=><option key={model.id} value={model.id}>{model.department} · {model.parameterCount} entries</option>)}</select></label>
   <label>JSON collection<select value={collection} onChange={event=>setCollection(event.target.value)} disabled={!document||busy}><option value="">Select a collection</option>{Object.entries(draftCollections).map(([name,value])=><option key={name} value={name}>{name} · {value.length}</option>)}</select></label>
   <button className="btn" disabled={busy} onClick={()=>void loadList()}><RefreshCw size={14}/>Reload sources</button>
  </div>
  {error&&<p className="failText" role="alert">{error}</p>}{notice&&<p className="dataModelSourceNotice" role="status">{notice}</p>}
  {chopperOpen&&<div className="dataModelChopperPanel"><div className="widgetHead"><div><h4><Bot size={16}/> Configure with Chopper</h4><p>Ask for guidance on the selected source and collection. Chopper will not edit or publish JSON values.</p></div><button className="btn" onClick={()=>setChopperOpen(false)}>Close</button></div><label>What should Chopper help configure?<textarea value={chopperQuestion} onChange={event=>setChopperQuestion(event.target.value)} placeholder="Explain a field, review a mapping, or describe the change you want to make." rows={2}/></label><button className="btn primary" disabled={chopperBusy||!chopperQuestion.trim()} onClick={()=>void askChopper()}><Bot size={14}/>{chopperBusy?'Asking Chopper…':'Ask Chopper'}</button>{chopperAnswer&&<div className="dataModelChopperAnswer">{chopperAnswer}</div>}</div>}
  {document&&collection&&<>
   <div className="dataModelSourceTableHeading"><div><b>{collection}</b><span>{rows.length} entries · edits are drafts until saved</span></div><label>Search<input value={search} onChange={event=>setSearch(event.target.value)} placeholder="Find tagName, group code, or database key"/></label></div>
   {editing&&canEdit&&<div className="dataModelEditActions"><button className="btn" disabled={busy} onClick={addRow}><Plus size={14}/>Add mapping</button><button className="btn" disabled={busy} onClick={addColumn}><Plus size={14}/>Add field</button></div>}
   <div className="knowledgeTableScroll dataModelJsonKeyTable" tabIndex={0} aria-label="Editable database JSON Key records"><table className="table"><thead><tr>{columns.map(key=><th key={key}>{key}</th>)}{editing&&canEdit&&<th>Actions</th>}</tr></thead><tbody>
    {visible.map(({row,index})=><tr key={`${collection}:${index}`}>
     {columns.map(key=><td key={key}>{editing&&canEdit?typeof row[key]==='boolean'||key==='isRequired'?<input type="checkbox" aria-label={`${key} row ${index+1}`} checked={row[key]===true} onChange={event=>updateRow(index,key,event.target.checked)}/>:typeof row[key]==='number'?<input className="dataModelCellInput" type="number" value={row[key] as number} onChange={event=>updateRow(index,key,event.target.value===''?null:Number(event.target.value))}/>:<input className="dataModelCellInput" aria-label={`${key} row ${index+1}`} value={row[key]==null?'':typeof row[key]==='object'?JSON.stringify(row[key]):String(row[key])} placeholder={row[key]===null?'null':''} onChange={event=>updateRow(index,key,event.target.value)}/>:row[key]==null?<span className="muted">—</span>:typeof row[key]==='object'?JSON.stringify(row[key]):String(row[key])}</td>)}
     {editing&&canEdit&&<td><button type="button" className="btn dataModelDeleteRow" disabled={busy} aria-label={`Delete ${String(row.tagName||'mapping')}`} onClick={()=>removeRow(index)}><Trash2 size={14}/>Delete</button></td>}
    </tr>)}
   </tbody></table>{!visible.length&&<p>No JSON Key records match this search.</p>}</div>
   <div className="dataModelSourceFooter">{dirty&&<button className="btn" disabled={busy} onClick={()=>{setDraftCollections(document.collections);setSavedCollections(JSON.stringify(document.collections));setEditing(false);setError('');setNotice('Draft changes discarded.')}}>Discard changes</button>}<button className="btn primary" disabled={!canEdit||!dirty||busy} onClick={()=>void save()}><Save size={14}/>{busy?'Saving…':'Save Changes'}</button></div>
  </>}
  {!document&&<div className="dataModelSourceEmpty"><Table2 size={24}/><b>{busy?'Loading JSON Key table…':error?'JSON Key table could not be loaded':'Select a service and department'}</b><span>{busy?'Reading the PMS, QMS and CMS JSON files.':'The table uses the original JSON Key file for the selected service and department.'}</span></div>}
  {!canEdit&&document&&<p className="muted">Only an administrator can import, edit or save the shared JSON Key files.</p>}
  {csvOpen&&<div className="dataModelCsvDialog" role="dialog" aria-modal="true" aria-label="Import JSON Key CSV"><div className="dataModelCsvDialogCard"><div className="widgetHead"><div><h4>Import CSV into {collection}</h4><p>CSV must have a header row containing <code>tagName</code>. This replaces the selected collection after confirmation.</p></div><button className="btn" onClick={()=>setCsvOpen(false)}>Close</button></div><textarea value={csvText} onChange={event=>setCsvText(event.target.value)} rows={10} placeholder={'tagName,dataType,groupCode,tdEngineKey,mongoKey,formula,type,isRequired\nShift Number,FLOAT,40,shift_number,shift_id,,instant,true'}/><div className="actions"><button className="btn" onClick={()=>setCsvOpen(false)}>Cancel</button><button className="btn primary" disabled={!csvText.trim()} onClick={()=>importCsv(csvText)}>Import CSV</button></div></div></div>}
 </section>;
}
