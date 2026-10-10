import {useEffect,useRef,useState} from 'react';

export type SourceSelection={path:string;line?:number;tag?:string;edit?:boolean;mode?:'source'|'types'};
export function ValidationSourceEditor({sessionId,selection,datatypes,onClose,onSaved}:{sessionId:string;selection:SourceSelection;datatypes:any[];onClose:()=>void;onSaved:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),editor=useRef<HTMLTextAreaElement>(null),gutter=useRef<HTMLPreElement>(null);
 const [path,setPath]=useState(selection.path),[line,setLine]=useState(selection.line||1),[mode,setMode]=useState(selection.mode||'source');
 const [source,setSource]=useState<any>(null),[text,setText]=useState(''),[editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [reload,setReload]=useState(0);
 const [search,setSearch]=useState(''),[tagQuery,setTagQuery]=useState((selection.tag||'').replace(/\[.*?\]/g,'')),[typeFilter,setTypeFilter]=useState('');
 const dirty=!!source&&text!==source.content;
 useEffect(()=>{if(dialog.current&&!dialog.current.open)dialog.current.showModal()},[]);
 useEffect(()=>{
  const controller=new AbortController();setBusy(true);setSource(null);setText('');setError('');setMessage('');setEditing(!!selection.edit);
  fetch('/api/validation/source/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,path}),signal:controller.signal})
   .then(async r=>{const data=await r.json();if(!r.ok)throw new Error(data.detail||'Cannot open source');return data})
   .then(data=>{const normalized={...data,content:data.content.replace(/\r\n?/g,'\n')};setSource(normalized);setText(normalized.content);if(normalized.readOnly)setEditing(false)})
   .catch(e=>{if(e.name!=='AbortError')setError(e.message)}).finally(()=>{if(!controller.signal.aborted)setBusy(false)});
  return()=>controller.abort();
 },[sessionId,path,reload]);
 useEffect(()=>{if(!source||mode!=='source')return;const area=editor.current;if(!area)return;const rows=source.content.split('\n');const start=rows.slice(0,Math.max(0,line-1)).join('\n').length+(line>1?1:0);area.focus();area.setSelectionRange(start,start+(rows[line-1]?.length||0));area.scrollTop=Math.max(0,(line-4)*20);if(gutter.current)gutter.current.scrollTop=area.scrollTop},[source,line,mode]);
 const save=async()=>{
  setBusy(true);setError('');setMessage('');
  try{const r=await fetch('/api/validation/source/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,path,etag:source.etag,content:text})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Save failed');setSource({...source,content:text,etag:data.etag});setEditing(false);setMessage(data.message);onSaved()}catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 const findNext=()=>{const area=editor.current;if(!area||!search)return;let start=text.toLowerCase().indexOf(search.toLowerCase(),area.selectionEnd);if(start<0)start=text.toLowerCase().indexOf(search.toLowerCase());if(start<0){setMessage('Search text not found.');return}setMessage('');area.focus();area.setSelectionRange(start,start+search.length);area.scrollTop=Math.max(0,(text.slice(0,start).split('\n').length-4)*20);if(gutter.current)gutter.current.scrollTop=area.scrollTop};
 const filtered=datatypes.filter(item=>(!typeFilter||item.dataType===typeFilter)&&`${item.name} ${item.dataType} ${item.sourceFile}`.toLowerCase().includes(tagQuery.toLowerCase()));
 const types=Array.from(new Set(datatypes.map(item=>String(item.dataType)))).sort();
 return <dialog ref={dialog} className="validationSourceDialog" aria-labelledby="validationSourceTitle" onClose={onClose} onCancel={event=>{if(dirty||busy){event.preventDefault();setMessage('Save or discard your edits before closing.')}}}>
  <header><div><h2 id="validationSourceTitle">Validated PLC source</h2><small>{path} · line {line}</small></div><button className="btn" disabled={dirty||busy} onClick={()=>dialog.current?.close()}>Close</button></header>
  <div className="sourceEditorToolbar"><button className={'chip '+(mode==='source'?'active':'')} onClick={()=>setMode('source')}>Source file</button><button className={'chip '+(mode==='types'?'active':'')} onClick={()=>setMode('types')}>PLC tag / datatype</button><span>{dirty?'Unsaved edits':editing?'Editing':'Read-only view'}</span></div>
  {error&&<p role="alert" className="failText sourceEditorMessage">{error}</p>}{message&&<p role="status" className="sourceEditorMessage">{message}</p>}
  {source?.note&&<p className="sourceEditorMessage">{source.note}</p>}{mode==='source'?<>
   <div className="sourceEditorToolbar"><input aria-label="Search source" placeholder="Find PLC tag or text" value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();findNext()}}}/><button className="btn" onClick={findNext} disabled={!source||!search}>Find next</button><button className="btn" disabled={!source||busy||editing||source.readOnly} onClick={()=>setEditing(true)}>Edit file</button><button className="btn primary" disabled={!dirty||busy||source?.readOnly} onClick={()=>void save()}>{busy?'Working…':'Save file'}</button><button className="btn" disabled={!dirty||busy} onClick={()=>{setText(source.content);setEditing(false);setMessage('Edits discarded.')}}>Discard edits</button><button className="btn" disabled={dirty||busy} onClick={()=>setReload(n=>n+1)}>Reload file</button></div>
   <p className="sourceEditorMessage">Save writes to {source?.projectPath||'the validated project'}. A backup is kept in this validation session. Uploaded projects are edited in their temporary workspace. Rerun validation after saving.</p>
   {busy&&!source?<p className="sourceEditorMessage">Loading source…</p>:<div className="sourceEditorCode"><pre aria-hidden="true" ref={gutter}>{text.split('\n').map((_,i)=>i+1).join('\n')}</pre><textarea ref={editor} aria-label="PLC source file contents" spellCheck={false} readOnly={!editing||busy||!source||source.readOnly} value={text} onChange={e=>setText(e.target.value)} onScroll={e=>{if(gutter.current)gutter.current.scrollTop=e.currentTarget.scrollTop}}/></div>}
  </>:<div className="sourceDatatypeView"><div className="sourceEditorToolbar"><input aria-label="Filter PLC tags" placeholder="Search tag, datatype or declaration file" value={tagQuery} onChange={e=>setTagQuery(e.target.value)}/><select aria-label="Datatype filter" value={typeFilter} onChange={e=>setTypeFilter(e.target.value)}><option value="">All datatypes</option>{types.map(t=><option key={t}>{t}</option>)}</select><span>{filtered.length} resolved declarations</span></div>
   <p className="sourceEditorMessage">Declarations used in the last validation. Open the declaration file to edit it, then rerun validation to refresh this index.</p>
   <div className="tableWrap"><table className="table"><thead><tr><th>PLC tag</th><th>Declared datatype</th><th>Bytes</th><th>Declaration file</th><th>View</th></tr></thead><tbody>{filtered.slice(0,200).map((item,i)=><tr key={`${item.sourceFile}-${item.name}-${i}`}><td>{item.name}</td><td>{item.dataType}</td><td>{item.size??'Unresolved'}</td><td>{item.sourceFile}</td><td><button className="btn" disabled={dirty||busy||!item.sourceFile} onClick={()=>{setPath(item.sourceFile);setLine(1);setSearch(item.name);setMode('source')}}>Open declaration</button></td></tr>)}</tbody></table></div>
   {!datatypes.length&&<p>Run validation again to populate the datatype index.</p>}{filtered.length>200&&<p>Showing the first 200 matches. Refine the search to find your tag.</p>}{dirty&&<p>Save or discard the current edits before opening another file.</p>}
  </div>}
 </dialog>;
}
