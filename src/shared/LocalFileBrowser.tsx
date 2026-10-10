import {useEffect,useState,type ReactNode} from 'react';
import {FolderOpen,FileSpreadsheet,X,ArrowUp} from 'lucide-react';

type Props={open:boolean;onClose:()=>void;onSelect:(path:string,name:string)=>void;selectedPath?:string;allowedExts?:string[];projectControls?:ReactNode};
function LocalBrowser({open,onClose,onSelect,selectedPath='',allowedExts,projectControls,kind}:{open:boolean;onClose:()=>void;onSelect:(path:string,name:string)=>void;selectedPath?:string;allowedExts?:string[];projectControls?:ReactNode;kind:'file'|'folder'}) {
  const [address,setAddress]=useState(selectedPath);
  const [current,setCurrent]=useState('');
  const [parent,setParent]=useState('');
  const [entries,setEntries]=useState<any[]>([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const browse=async(path='',keepAddress=false)=>{
    setBusy(true);setError('');
    try{const r=await fetch('/api/local/browse?'+new URLSearchParams({path,files:String(kind==='file'),ext:(allowedExts||[]).join(',')}));const j=await r.json();if(!r.ok)throw new Error(j.detail||'Cannot browse folder');setEntries(j.entries||[]);setCurrent(j.path);setParent(j.parent||'');if(!keepAddress)setAddress(j.path)}catch(e:any){setError(e.message)}finally{setBusy(false)}
  };
  useEffect(()=>{if(open){void browse('',true);setAddress(selectedPath)}},[open]);
  const select=async()=>{
    setBusy(true);setError('');
    try{const r=await fetch('/api/local/path/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:address,kind,extensions:allowedExts})});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Cannot open path');onSelect(j.path,j.name);onClose()}catch(e:any){setError(e.message)}finally{setBusy(false)}
  };
  if(!open)return null;
  return <div className="modalBackdrop"><section className="folderBrowser card" role="dialog" aria-modal="true" aria-label={kind==='folder'?'Select project folder':'Select local file'}><div className="panelHead"><div><h2>{kind==='folder'?'Select project folder':'Select local file'}</h2><p>Paste a full path or browse this PC. Files are read by the local application without browser upload.</p></div><button className="iconBtn" aria-label="Close browser" onClick={onClose}><X size={18}/></button></div>
    {projectControls}
    <label className="pathLabel">{kind==='folder'?'Project folder or .apj path':'File path'}<input autoFocus className="textInput" value={address} onChange={e=>setAddress(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void select()}} placeholder={kind==='folder'?'C:\\Projects\\My project':'C:\\Metadata\\reference.xlsx'}/></label>
    <div className="actions"><button className="btn" disabled={busy} onClick={()=>browse()}>This PC</button><button className="btn" disabled={busy||!current} onClick={()=>browse(parent)}><ArrowUp size={14}/> Up</button><button className="btn" disabled={busy||!address} onClick={()=>browse(address)}>Open folder</button></div>
    <div className="folderPath mono">{current||'This PC'}</div><div className="folderTree">{entries.map(entry=><button className={'treeRow '+(entry.path===address?'selected':'')} key={entry.path} onClick={()=>setAddress(entry.path)} onDoubleClick={()=>entry.is_file?setAddress(entry.path):browse(entry.path)}>{entry.is_file?<FileSpreadsheet size={15}/>:<FolderOpen size={15}/>}<span>{entry.name}</span>{!entry.is_file&&<span className="subtle">Double-click to open</span>}</button>)}{!entries.length&&!busy&&<p>No matching files or folders.</p>}</div>
    {error&&<p className="pathError" role="alert">{error}</p>}<div className="actions"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy||!address.trim()} onClick={select}>{busy?'Reading…':kind==='folder'?'Use this folder':'Use this file'}</button></div>
  </section></div>;
}
export function LocalFolderTree(props:Props){return <LocalBrowser {...props} kind="folder"/>}
export function LocalFileTree({allowedExts=['.xlsx','.xls'],...props}:Props){return <LocalBrowser {...props} kind="file" allowedExts={allowedExts}/>}
