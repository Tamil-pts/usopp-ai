import {useCallback,useEffect,useState,type CSSProperties} from 'react';
import {ArrowDown,ArrowRight,ArrowUp,Download,FileDiff,Filter,LayoutList,LoaderCircle,Plus,Table2,Trash2,Upload} from 'lucide-react';
import {userStorage} from '../../shared/userStorage';
import './document-compare.css';
import {DocumentColumnMenu,type ColumnFilter,type ColumnSort,type FilterColumn} from './DocumentColumnFilters';

const API='/api/assist/document-comparisons';
const SAVED='usopp_document_comparison_last';
const VIEW='usopp_document_comparison_spreadsheet_view';
const ACCEPT='.csv,.xls,.xlsx,.pdf,.docx,.txt';
type Source={id:string;name:string;kind:'table'|'text';extension:string;sha256:string;size:number;sheets:{name:string;rows:number;columns:number}[]};
type Column={index:number;letter:string;name:string;has_data?:boolean};
type Schema={columns:Column[];preview:{row:number;values:string[]}[];notice:string};
type Pair={base:number;compared:number;enabled:boolean;key:boolean};
type Status='added'|'removed'|'modified'|'unchanged'|'unresolved';
type Cell={value:string;type:string;ref:string};
type Change={column:number;status:Status;base:Cell|null;compared:Cell|null};
type Row={id:number;status:Status;base_ref:string;compared_ref:string;key?:string;cells?:Change[];base?:string;compared?:string};
type Result={id:string;kind:'table'|'text';base:Source;compared:Source;summary:Record<Status,number>;columns:{base:Column;compared:Column}[];notices:string[];rows:Row[];total:number;offset:number;limit:number};
const labels:Record<string,string>={differences:'Differences',all:'All',added:'Added',removed:'Removed',modified:'Modified',unchanged:'Unchanged',unresolved:'Needs review'};

async function json<T>(url:string,init?:RequestInit):Promise<T>{
 const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...init});
 const value=await response.json().catch(()=>({detail:'The server did not return a readable comparison response.'}));
 if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Could not compare these files.');
 if(response.headers.get('content-type')?.includes('text/html'))throw Error('Restart the updated uSOPp server to enable document comparison.');
 return value;
}

function useInput(){
 const [info,setInfo]=useState<Source|null>(null),[sheet,setSheet]=useState(''),[header,setHeader]=useState(1),[schema,setSchema]=useState<Schema|null>(null),[uploading,setUploading]=useState(false),[reading,setReading]=useState(false),[error,setError]=useState('');
 async function upload(file:File){
  setInfo(null);setSchema(null);setError('');
  if(file.size>25*1024**2){setError('Choose a file up to 25 MB.');return;}
  setUploading(true);const data=new FormData();data.append('file',file);
  try{const result=await json<Source>(API+'/uploads',{method:'POST',body:data});setHeader(1);setSheet(result.sheets[0]?.name||'');setInfo(result);}
  catch(e){setError((e as Error).message);}finally{setUploading(false);}
 }
 useEffect(()=>{
  setSchema(null);setReading(false);if(!info||info.kind!=='table'||!sheet)return;
  const controller=new AbortController();setReading(true);setError('');
  void json<Schema>(`${API}/uploads/${info.id}/columns?${new URLSearchParams({sheet,header_row:String(header)})}`,{signal:controller.signal}).then(setSchema).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setReading(false);});
  return()=>controller.abort();
 },[info?.id,sheet,header]);
 return {info,sheet,header,schema,error,busy:uploading||reading,upload,setSheet,setHeader};
}
type Input=ReturnType<typeof useInput>;

function FileInput({side,input,disabled}:{side:'Base'|'Compared';input:Input;disabled:boolean}){
 return <fieldset className="dc-input" disabled={disabled||input.busy}><legend>{side} file</legend><label className="dc-upload"><Upload size={17}/><span>{input.info?.name||'Choose a file'}</span><input type="file" aria-label={`${side} document`} accept={ACCEPT} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void input.upload(file);}}/></label>
  {input.info&&<small className="dc-source-meta">{(input.info.size/1024).toFixed(1)} KB · SHA256 {input.info.sha256.slice(0,12)}…</small>}
  {input.info?.kind==='table'&&<div className="dc-sheet-controls"><label>{side} sheet<select aria-label={`${side} sheet`} value={input.sheet} onChange={e=>input.setSheet(e.target.value)}>{input.info.sheets.map(s=><option key={s.name} value={s.name}>{s.name} ({s.rows} rows)</option>)}</select></label><label>{side} header row<input type="number" aria-label={`${side} header row`} min={0} max={100} value={input.header} onChange={e=>input.setHeader(Math.min(100,Math.max(0,Number(e.target.value))))}/></label></div>}
  {input.busy&&<p role="status"><LoaderCircle size={14} className="spin"/>Reading {side.toLowerCase()} file…</p>}{input.error&&<p className="wh-error" role="alert">{input.error}</p>}
  {input.schema&&<details><summary>Preview columns and first rows</summary><div className="dc-preview"><table><thead><tr><th>Row</th>{input.schema.columns.slice(0,32).map(c=><th key={c.index}>{c.letter} · {c.name}</th>)}</tr></thead><tbody>{input.schema.preview.map(r=><tr key={r.row}><th>{r.row}</th>{r.values.map((v,i)=><td key={i}>{v}</td>)}</tr>)}</tbody></table></div><small>{input.schema.notice}</small></details>}
 </fieldset>;
}

function RowResult({row,result,showSame}:{row:Row;result:Result;showSame:boolean}){
 const [open,setOpen]=useState(row.status!=='unchanged');
 const cells=(row.cells||[]).filter(c=>showSame||row.status==='unchanged'||c.status!=='unchanged');
 return <details className={'dc-result-row '+row.status} open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary><span className={'dc-status '+row.status}>{labels[row.status]}</span>{row.key&&<b>{row.key}</b>}<span>{row.base_ref||'—'} <ArrowRight size={13}/> {row.compared_ref||'—'}</span><small>{row.cells?.filter(c=>c.status!=='unchanged').length} changed cells</small></summary>
  {open&&<div>{cells.map(c=>{const columns=result.columns[c.column];return <div className={'dc-cell-pair '+c.status} key={c.column}>{(['base','compared'] as const).map(side=><div key={side}><strong>{columns[side].letter} · {columns[side].name}</strong><small>{c[side]?.ref||'No row on this side'}{c[side]?' · '+c[side]!.type:''}</small><pre>{c[side]?.value||(c[side]?'(blank)':'—')}</pre></div>)}</div>;})}</div>}
 </details>;
}

function SpreadsheetTable({result,headerFilters,status,filters,sort,onFilter,onSort}:{result:Result;headerFilters:boolean;status:string;filters:ColumnFilter[];sort:ColumnSort|null;onFilter:(filter:ColumnFilter|null,side:'base'|'compared',column:number)=>void;onSort:(sort:ColumnSort|null)=>void}){
 const [menu,setMenu]=useState<FilterColumn|null>(null);const closeMenu=useCallback(()=>setMenu(null),[]);
 useEffect(()=>{if(!headerFilters)setMenu(null);},[headerFilters]);
 const rowNumber=(reference:string)=>reference.match(/\/ row (\d+)$/)?.[1]||'—';
 return <><div className="dc-result-scroll dc-spreadsheet-scroll" role="region" aria-label="Spreadsheet table comparison" tabIndex={0}>
  <table className="dc-spreadsheet-table" style={{'--dc-grid-width':`${result.columns.length*360}px`} as CSSProperties}>
   <caption className="dc-visually-hidden">Selected columns from File 1 and File 2, aligned by the comparison's row matching. Cell colours identify differences.</caption>
   <colgroup><col style={{width:'var(--dc-meta-width)'}}/>{(['base','compared'] as const).flatMap(side=>result.columns.map((_,i)=><col key={side+i} style={{width:180}}/>))}</colgroup>
   <thead><tr><th className="dc-table-meta" rowSpan={2} scope="col">Status / source rows</th><th className="dc-table-file base" colSpan={result.columns.length} scope="colgroup"><b>File 1 · Base</b><span>{result.base.name}</span></th><th className="dc-table-file compared dc-table-divider" colSpan={result.columns.length} scope="colgroup"><b>File 2 · Compared</b><span>{result.compared.name}</span></th></tr>
    <tr>{(['base','compared'] as const).flatMap(side=>result.columns.map((c,i)=><th key={side+i} scope="col" className={`dc-table-column ${side}${side==='compared'&&i===0?' dc-table-divider':''}`}><div className="dc-table-column-heading"><span>{c[side].name}</span>{headerFilters&&<button type="button" className={'dc-header-filter'+(filters.some(f=>f.side===side&&f.column===i)?' active':'')} aria-label={`Filter File ${side==='base'?'1':'2'} column ${c[side].name}`} aria-haspopup="dialog" aria-expanded={menu?.side===side&&menu.column===i} aria-controls={menu?.side===side&&menu.column===i?'document-column-filter':undefined} onClick={e=>{const anchor=e.currentTarget;setMenu(old=>old?.side===side&&old.column===i?null:{side,column:i,name:c[side].name,anchor});}}><Filter size={12}/>{sort?.side===side&&sort.column===i&&(sort.direction==='asc'?<ArrowUp size={11}/>:<ArrowDown size={11}/>)}</button>}</div><small>Column {c[side].letter}</small></th>))}</tr></thead>
   <tbody>{result.rows.map(row=>{
    const cells=new Map((row.cells||[]).map(c=>[c.column,c]));
    return <tr key={row.id} data-status={row.status}><th scope="row" className="dc-table-meta" title={`${row.key?'Key: '+row.key+' · ':''}File 1: ${row.base_ref||'No row'} · File 2: ${row.compared_ref||'No row'}`}><span className={'dc-status '+row.status}>{labels[row.status]}</span><small>Rows {rowNumber(row.base_ref)} → {rowNumber(row.compared_ref)}</small></th>
     {(['base','compared'] as const).flatMap(side=>result.columns.map((_,i)=>{
      const change=cells.get(i),value=change?.[side];
      const status=value?change?.status||'unchanged':'missing';
      return <td key={side+i} data-side={side} data-column={i} data-status={status} className={`dc-table-cell ${side} ${status}${side==='compared'&&i===0?' dc-table-divider':''}`} title={value?`${value.ref} · ${value.type} · ${labels[status]}${value.value===''?' · Blank cell':''}`:`No row in File ${side==='base'?'1':'2'}`}><span>{value?value.value:<span className="dc-table-missing" aria-label={`No row in File ${side==='base'?'1':'2'}`}>—</span>}</span></td>;
     }))}
    </tr>;
   })}</tbody>
  </table>
 </div>{menu&&<DocumentColumnMenu key={`${menu.side}:${menu.column}`} resultId={result.id} column={menu} status={status} filters={filters} sort={sort} onClose={closeMenu} onFilter={filter=>onFilter(filter,menu.side,menu.column)} onSort={onSort}/>}</>;
}

export default function DocumentCompare(){
 const base=useInput(),compared=useInput();
 const [pairs,setPairs]=useState<Pair[]>([]),[matchBy,setMatchBy]=useState('row'),[valueMode,setValueMode]=useState('values'),[ignoreCase,setIgnoreCase]=useState(false),[ignoreWhitespace,setIgnoreWhitespace]=useState(false),[compareTypes,setCompareTypes]=useState(false);
 const [comparison,setComparison]=useState(()=>userStorage.getItem(SAVED)||''),[result,setResult]=useState<Result|null>(null),[status,setStatus]=useState('differences'),[offset,setOffset]=useState(0),[showSame,setShowSame]=useState(false),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const [headerFilters,setHeaderFilters]=useState(false),[columnFilters,setColumnFilters]=useState<ColumnFilter[]>([]),[columnSort,setColumnSort]=useState<ColumnSort|null>(null),[exporting,setExporting]=useState(false);
 const activeFilters=headerFilters?columnFilters:[],activeSort=headerFilters?columnSort:null;const criteriaKey=JSON.stringify({column_filters:activeFilters,sort:activeSort});const hasCriteria=activeFilters.length>0||!!activeSort;
 const [spreadsheetView,setSpreadsheetView]=useState<'detailed'|'table'>(()=>userStorage.getItem(VIEW)==='table'?'table':'detailed');
 const chooseView=(view:'detailed'|'table')=>{setSpreadsheetView(view);userStorage.setItem(VIEW,view);};
 const tables=base.info?.kind==='table'&&compared.info?.kind==='table';
 const selected=pairs.filter(p=>p.enabled);
 function autoPair(){
  const used=new Set<number>(),rows:Pair[]=[];
  for(const a of (base.schema?.columns||[]).filter(c=>c.has_data!==false)){const b=compared.schema?.columns.find(b=>b.has_data!==false&&!used.has(b.index)&&b.name.trim().toLowerCase()===a.name.trim().toLowerCase());if(b){used.add(b.index);rows.push({base:a.index,compared:b.index,enabled:true,key:false});}}
  setPairs(rows);
 }
 useEffect(()=>{autoPair();},[base.schema,compared.schema]);
 useEffect(()=>{if(base.info||compared.info){setComparison('');setResult(null);setError('');setColumnFilters([]);setColumnSort(null);}},[base.info?.id,compared.info?.id,base.sheet,compared.sheet,base.header,compared.header,pairs,matchBy,valueMode,ignoreCase,ignoreWhitespace,compareTypes]);
 useEffect(()=>{if(base.info?.extension!=='.xlsx'||compared.info?.extension!=='.xlsx')setValueMode('values');},[base.info?.extension,compared.info?.extension]);
 useEffect(()=>{
  if(!comparison)return;const controller=new AbortController();setLoading(true);setError('');
  void json<Result>(hasCriteria?`${API}/results/${comparison}/query`:`${API}/results/${comparison}?${new URLSearchParams({status,offset:String(offset),limit:'100'})}`,{signal:controller.signal,...(hasCriteria?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,offset,limit:100,column_filters:activeFilters,sort:activeSort})}:{})}).then(setResult).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();
 },[comparison,status,offset,criteriaKey]);
 function changePair(i:number,value:Partial<Pair>){setPairs(current=>current.map((p,n)=>n===i?{...p,...value}:p));}
 async function run(){
  if(!base.info||!compared.info)return;setError('');setBusy(true);setComparison('');setResult(null);setColumnFilters([]);setColumnSort(null);
  const config=(input:Input)=>({id:input.info!.id,sheet:input.sheet,header_row:input.header});
  try{
   const value=await json<Result>(API+'/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base:config(base),compared:config(compared),columns:selected.map(p=>({base:p.base,compared:p.compared})),keys:selected.flatMap((p,i)=>p.key?[i]:[]),match_by:matchBy,value_mode:valueMode,ignore_case:ignoreCase,ignore_whitespace:ignoreWhitespace,compare_types:compareTypes})});
   setOffset(0);setStatus('differences');setResult(value);setComparison(value.id);userStorage.setItem(SAVED,value.id);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 const ready=!!base.info&&!!compared.info&&!base.busy&&!compared.busy&&base.info.kind===compared.info.kind&&(!tables||!!base.schema&&!!compared.schema&&!!selected.length&&(matchBy!=='key'||selected.some(p=>p.key)));
 const filter=(next:string)=>{setOffset(0);setStatus(next);};
 const applyColumn=(filter:ColumnFilter|null,side:'base'|'compared',column:number)=>{setOffset(0);setColumnFilters(old=>[...old.filter(f=>f.side!==side||f.column!==column),...(filter?[filter]:[])]);};
 const applySort=(sort:ColumnSort|null)=>{setOffset(0);setColumnSort(sort);};
 const enableHeaders=(enabled:boolean)=>{setHeaderFilters(enabled);if(enabled)chooseView('table');else{setColumnFilters([]);setColumnSort(null);setOffset(0);}};
 async function exportView(){
  if(!result)return;setExporting(true);setError('');
  try{const response=await fetch(`${API}/results/${result.id}/export.csv`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,column_filters:activeFilters,sort:activeSort})});if(!response.ok){const data=await response.json();throw Error(data.detail||'Could not export this view.');}const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=`document-comparison-${result.id.slice(0,8)}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){setError((e as Error).message);}finally{setExporting(false);}
 }

 return <section className="documentCompare" aria-label="Document comparison workspace">
  <header className="dc-heading"><div><h3><FileDiff size={20}/>Compare documents</h3><p>Choose two files. Compare selected spreadsheet columns or review PDF and Word text changes side by side.</p><small>CSV · XLS · XLSX · PDF · Word DOCX · TXT · Up to 25 MB per file</small></div></header>
  <div className="dc-inputs"><FileInput side="Base" input={base} disabled={busy}/><FileInput side="Compared" input={compared} disabled={busy}/></div>
  {base.info&&compared.info&&base.info.kind!==compared.info.kind&&<p role="alert" className="wh-error">Choose two spreadsheet files, or two text documents (PDF, DOCX or TXT).</p>}
  {tables&&base.schema&&compared.schema&&<fieldset className="dc-mapping" disabled={busy}><legend>Columns to compare</legend><div className="dc-actions"><button type="button" className="btn" onClick={autoPair}>Match column names</button><button type="button" className="btn" onClick={()=>setPairs(p=>p.map(v=>({...v,enabled:true})))}>Select all</button><button type="button" className="btn" onClick={()=>setPairs(p=>p.map(v=>({...v,enabled:false,key:false})))}>Clear selections</button><button type="button" className="btn" disabled={pairs.length>=256} onClick={()=>setPairs(p=>[...p,{base:base.schema!.columns[0]?.index||0,compared:compared.schema!.columns[0]?.index||0,enabled:true,key:false}])}><Plus size={14}/>Add column pair</button><small>{selected.length} selected</small></div>
   <p>Each row maps one base column to one compared column. Columns may have different names. Header row 0 means there is no header.</p>
   <div className="dc-mapping-scroll"><table><thead><tr><th>Compare</th><th>Base column</th><th>Compared column</th><th>Row key</th><th/></tr></thead><tbody>{pairs.map((p,i)=><tr key={i}><td><input type="checkbox" aria-label={`Compare column pair ${i+1}`} checked={p.enabled} onChange={e=>changePair(i,{enabled:e.target.checked,key:e.target.checked&&p.key})}/></td>{(['base','compared'] as const).map(side=><td key={side}><select aria-label={`${side==='base'?'Base':'Compared'} column ${i+1}`} value={p[side]} onChange={e=>changePair(i,{[side]:Number(e.target.value)})}>{(side==='base'?base.schema:compared.schema)!.columns.map(c=><option key={c.index} value={c.index}>{c.letter} · {c.name}</option>)}</select></td>)}<td><input type="checkbox" aria-label={`Row key column pair ${i+1}`} disabled={!p.enabled||matchBy!=='key'} checked={p.key} onChange={e=>changePair(i,{key:e.target.checked})}/></td><td><button type="button" className="btn" aria-label={`Remove column pair ${i+1}`} onClick={()=>setPairs(rows=>rows.filter((_,n)=>i!==n))}><Trash2 size={14}/></button></td></tr>)}</tbody></table></div>
   <div className="dc-options"><label>Match rows by<select aria-label="Match rows by" value={matchBy} onChange={e=>setMatchBy(e.target.value)}><option value="row">Row order</option><option value="key">Selected key columns</option></select></label><label>Compare Excel cells<select aria-label="Compare Excel cells" value={valueMode} onChange={e=>setValueMode(e.target.value)}><option value="values">Stored values</option><option value="formulas" disabled={base.info?.extension!=='.xlsx'||compared.info?.extension!=='.xlsx'}>Formula text (XLSX)</option></select></label><label><input type="checkbox" checked={compareTypes} onChange={e=>setCompareTypes(e.target.checked)}/>Compare cell types</label></div>
   {matchBy==='key'&&<p>Mark one or more mapped columns as the row key, for example TAG_CODE + GROUP_CODE. Keys must be complete and unique in each selected sheet. Row order changes are ignored in this mode.</p>}
  </fieldset>}
  <div className="dc-options"><label><input type="checkbox" checked={ignoreCase} disabled={busy} onChange={e=>setIgnoreCase(e.target.checked)}/>Ignore letter case</label><label><input type="checkbox" checked={ignoreWhitespace} disabled={busy} onChange={e=>setIgnoreWhitespace(e.target.checked)}/>Ignore repeated whitespace</label><button type="button" className="btn primary" disabled={!ready||busy} onClick={()=>void run()}>{busy?<LoaderCircle size={16} className="spin"/>:<FileDiff size={16}/>}Compare files</button></div>
  {error&&<p className="wh-error" role="alert">{error}</p>}{busy&&<p role="status">Comparing the selected content…</p>}
  {result&&<section className="dc-results" aria-label="Document comparison results" aria-busy={loading}><div className="dc-result-heading"><div><h3>Comparison results</h3><p>{result.base.name} <ArrowRight size={14}/> {result.compared.name}</p></div>{hasCriteria?<button type="button" className="btn" disabled={exporting||loading} onClick={()=>void exportView()}><Download size={15}/>{exporting?'Exporting?':'Export this view (CSV)'}</button>:<a className="btn" href={`${API}/results/${result.id}/export.csv?status=${status}`}><Download size={15}/>Export this view (CSV)</a>}</div>
   <div className="dc-totals">{(['modified','added','removed','unchanged','unresolved'] as Status[]).map(s=><button type="button" className={'dc-count '+s} key={s} onClick={()=>filter(s)}><b>{result.summary[s]}</b>{labels[s]} {result.kind==='table'?'rows':'lines'}</button>)}</div>
   <details className="dc-scope"><summary>Compared content and source snapshots</summary>{result.notices.map((note,i)=><p key={i}>{note}</p>)}<p>Base SHA256: <code>{result.base.sha256}</code></p><p>Compared SHA256: <code>{result.compared.sha256}</code></p></details>
   {result.summary.unresolved>0&&<p className="dc-review" role="status">Some content needs review. Missing stored formula results or unreadable PDF pages are not treated as matches.</p>}
   {result.kind==='table'&&<div className="dc-result-view" role="group" aria-label="Spreadsheet result view"><span>Result view</span><button type="button" className={'btn '+(spreadsheetView==='detailed'?'primary':'')} aria-pressed={spreadsheetView==='detailed'} onClick={()=>chooseView('detailed')}><LayoutList size={15}/>Detailed view</button><button type="button" className={'btn '+(spreadsheetView==='table'?'primary':'')} aria-pressed={spreadsheetView==='table'} onClick={()=>chooseView('table')}><Table2 size={15}/>Table view</button><label className="dc-header-filter-toggle"><input type="checkbox" checked={headerFilters} onChange={e=>enableHeaders(e.target.checked)}/>Enable header filters</label>{hasCriteria&&<><small>{activeFilters.length} column filters{activeSort?' ? Sorted':''}</small><button type="button" className="btn" onClick={()=>{setColumnFilters([]);setColumnSort(null);setOffset(0);}}>Clear column filters &amp; sort</button></>}</div>}
   <div className="dc-actions" role="group" aria-label="Comparison filters">{['differences','all','modified','added','removed','unchanged','unresolved'].map(s=><button type="button" className={'btn '+(status===s?'primary':'')} key={s} aria-pressed={status===s} onClick={()=>filter(s)}>{labels[s]}</button>)}{result.kind==='table'&&spreadsheetView==='detailed'&&<label><input type="checkbox" checked={showSame} onChange={e=>setShowSame(e.target.checked)}/>Show unchanged cells</label>}</div>
   {result.kind==='text'&&<p className="dc-note">PDF and Word comparison covers extracted text. Differences includes five surrounding text lines; visual drawing changes can be reviewed in e-design MatchView.</p>}
   {result.kind==='table'&&spreadsheetView==='table'?<><p className="dc-note">Table view shows all selected columns. Choose All to include unchanged rows. Changed cells are highlighted; both files share the same scroll area.</p><SpreadsheetTable result={result} headerFilters={headerFilters} status={status} filters={activeFilters} sort={activeSort} onFilter={applyColumn} onSort={applySort}/></>:<div className="dc-result-scroll"><div className="dc-result-content"><div className="dc-side-heading"><strong>Base · {result.base.name}</strong><strong>Compared · {result.compared.name}</strong></div>{result.rows.map(row=>result.kind==='table'?<RowResult key={row.id} row={row} result={result} showSame={showSame}/>:<div className={'dc-text-pair '+row.status} key={row.id}><div><small>{row.base_ref||'—'}</small><pre>{row.base||'—'}</pre></div><div><small>{row.compared_ref||'—'} · {labels[row.status]}</small><pre>{row.compared||'—'}</pre></div></div>)}</div></div>}
   {!result.total&&<p className="dc-empty">{hasCriteria?'No rows match the selected column filters.':status==='differences'?'No differences in the selected content.':'No rows match this filter.'}</p>}
   <footer className="dc-pagination"><span>{result.total?`${offset+1}–${Math.min(offset+100,result.total)} of ${result.total}`:'0 results'}{loading?' · Loading…':''}</span><button type="button" className="btn" disabled={loading||offset===0} onClick={()=>setOffset(n=>Math.max(0,n-100))}>Previous</button><button type="button" className="btn" disabled={loading||offset+100>=result.total} onClick={()=>setOffset(n=>n+100)}>Next</button></footer>
  </section>}
 </section>;
}
