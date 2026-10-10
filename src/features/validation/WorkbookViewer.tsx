import {useEffect,useMemo,useState} from 'react';

type Sheet={name:string;headers:string[];rows:Record<string,any>[]};
const normalizedHeader=(value:string)=>String(value||'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const groupHeaders=new Set(['groupcode','group','groupid']);
const parameterHeaders=new Set(['parameters','parameter','parametername']);
export function WorkbookViewer({path,sessionId,source,projectName,onUse}:{path?:string;sessionId?:string;source:'generated'|'uploaded';projectName:string;onUse?:(path:string,name:string)=>void}) {
  const [sheets,setSheets]=useState<Sheet[]>([]);
  const [active,setActive]=useState(0);
  const [workbook,setWorkbook]=useState('');
  const [edit,setEdit]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [download,setDownload]=useState('');
  useEffect(()=>{
    let cancelled=false;
    setSheets([]);setActive(0);setDirty(false);setEdit(false);setDownload('');setWorkbook('');
    if(!path&&!sessionId){setMessage('Select a metadata workbook or generate one from the project.');return}
    setBusy(true);setMessage('Loading workbook…');
    fetch('/api/metadata/view/sheets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path,sessionId,source})})
      .then(async r=>{const j=await r.json();if(!r.ok)throw new Error(j.detail||'Cannot open workbook');return j})
      .then(j=>{if(!cancelled){setSheets(j.sheets);setWorkbook(j.workbookPath);setMessage('Edits are saved to a new workbook copy.')}})
      .catch(e=>{if(!cancelled)setMessage(e.message)})
      .finally(()=>{if(!cancelled)setBusy(false)});
    return()=>{cancelled=true};
  },[path,sessionId,source]);
  useEffect(()=>{if(!dirty)return;const guard=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard)},[dirty]);
  const update=(row:number,key:string,value:string)=>{
    setSheets(ss=>ss.map((s,i)=>i===active?{...s,rows:s.rows.map((r,n)=>n===row?{...r,[key]:value}:r)}:s));setDirty(true);
  };
  const save=async(exportFile=false)=>{
    setBusy(true);
    try{
      const r=await fetch('/api/metadata/view/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workbookPath:workbook,projectName,sheets})});
      const j=await r.json();if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:j.detail?.message+' '+(j.detail?.cells||[]).map((c:any)=>`${c.sheet}!${c.cell}: ${c.value}`).join('; ')||'Save failed');
      setWorkbook(j.workbookPath);setDownload(j.downloadUrl);setDirty(false);setEdit(false);setMessage('Saved all worksheets to '+j.fileName);
      if(exportFile){const link=document.createElement('a');link.href=j.downloadUrl;link.download=j.fileName;link.click()}
    }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  };
  const sheet=sheets[active];
  const duplicateInfo=useMemo(()=>{
    const rows=new Set<number>();
    if(!sheet)return {rows,groupHeader:'',parameterHeader:''};
    if(normalizedHeader(sheet.name)==='sheet2')return {rows,groupHeader:'',parameterHeader:''};
    const groupHeader=sheet.headers.find(h=>groupHeaders.has(normalizedHeader(h)))||'';
    const parameterHeader=sheet.headers.find(h=>parameterHeaders.has(normalizedHeader(h)))||'';
    if(!groupHeader||!parameterHeader)return {rows,groupHeader,parameterHeader};
    const buckets=new Map<string,number[]>();
    sheet.rows.forEach((row,index)=>{
      const group=String(row[groupHeader]??'').trim().toLowerCase();
      const parameter=String(row[parameterHeader]??'').trim().replace(/\s+/g,' ').toLowerCase();
      if(!group||!parameter)return;
      const key=`${group}\u0000${parameter}`;
      buckets.set(key,[...(buckets.get(key)||[]),index]);
    });
    buckets.forEach(indexes=>{if(indexes.length>1)indexes.forEach(index=>rows.add(index))});
    return {rows,groupHeader,parameterHeader};
  },[sheet]);
  return <section className="card workbookViewer">
    <div className="panelHead"><div><h2>{source==='generated'?'MetaWorks · Generated':'MetaWorks · Uploaded / selected'}</h2><p>{sheet?.rows.length||0} rows · {sheets.length} worksheets{dirty?' · Unsaved edits':''}</p></div>
      <div className="actions"><button className="btn" disabled={busy||!sheet} onClick={()=>setEdit(!edit)}>{edit?'Finish editing':'Edit'}</button><button className="btn" disabled={busy||!dirty} onClick={()=>save()}>Save copy</button><button className="btn primary" disabled={busy||!sheet} onClick={()=>save(true)}>Export XLSX</button>{download&&<a className="btn" href={download}>Download saved copy</a>}{onUse&&workbook&&<button className="btn" disabled={dirty||busy} onClick={()=>onUse(workbook,workbook.split(/[\\/]/).pop()||'Metadata')}>Use for validation</button>}</div></div>
    <p role="status">{message}</p>
    <div className="featureTabs">{sheets.map((s,i)=><button className={'chip '+(active===i?'active':'')} key={s.name} onClick={()=>setActive(i)}>{s.name}</button>)}</div>
    {duplicateInfo.rows.size>0&&<div className="metadataDuplicateNotice">Purple rows are duplicate Parameters inside the same Group Code. {duplicateInfo.rows.size} rows are affected on this worksheet.</div>}
    <div className="tableWrap workbookScroll"><table className="table"><thead><tr>{sheet?.headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{sheet?.rows.map((row,i)=>{const duplicate=duplicateInfo.rows.has(i);return <tr key={i} className={duplicate?'metadataDuplicateRow':''} title={duplicate?`Duplicate Parameter inside Group Code ${row[duplicateInfo.groupHeader]}`:undefined}>{sheet.headers.map((h,column)=><td key={h}>{duplicate&&column===0&&<span className="metadataDuplicateBadge">Duplicate in GC {String(row[duplicateInfo.groupHeader]??'')}</span>}{edit?<input aria-label={`${h}, row ${i+2}`} className="metadataEditInput" value={row[h]??''} onChange={e=>update(i,h,e.target.value)}/>:String(row[h]??'')}</td>)}</tr>})}</tbody></table></div>
  </section>;
}
