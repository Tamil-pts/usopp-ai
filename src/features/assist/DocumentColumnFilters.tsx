import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowDownAZ,ArrowUpAZ,Search,X} from 'lucide-react';

export type ColumnFilter={side:'base'|'compared';column:number;mode:'include'|'exclude';values:(string|null)[]};
export type ColumnSort={side:'base'|'compared';column:number;direction:'asc'|'desc'};
export type FilterColumn={side:'base'|'compared';column:number;name:string;anchor:HTMLButtonElement};
type Values={items:{value:string|null;label:string;count:number}[];total:number;offset:number;limit:number};
type Props={resultId:string;column:FilterColumn;status:string;filters:ColumnFilter[];sort:ColumnSort|null;onFilter:(filter:ColumnFilter|null)=>void;onSort:(sort:ColumnSort|null)=>void;onClose:()=>void};

export function DocumentColumnMenu({resultId,column,status,filters,sort,onFilter,onSort,onClose}:Props){
 const current=filters.find(f=>f.side===column.side&&f.column===column.column);
 const [draft,setDraft]=useState<ColumnFilter>(()=>current?{...current,values:[...current.values]}:{side:column.side,column:column.column,mode:'exclude',values:[]});
 const [search,setSearch]=useState(''),[term,setTerm]=useState(''),[offset,setOffset]=useState(0),[data,setData]=useState<Values|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState('');
 const [position,setPosition]=useState({left:12,top:12,maxHeight:450});const menu=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null);
 const all=draft.mode==='exclude'&&!draft.values.length,none=draft.mode==='include'&&!draft.values.length;
 const file=column.side==='base'?'1':'2';
 const filterKey=JSON.stringify(filters);
 useEffect(()=>{if(search===term)return;const timer=setTimeout(()=>{setTerm(search);setOffset(0);},200);return()=>clearTimeout(timer);},[search,term]);
 useEffect(()=>{
  const controller=new AbortController();setBusy(true);setError('');
  void fetch(`/api/assist/document-comparisons/results/${resultId}/values`,{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({side:column.side,column:column.column,status,column_filters:filters,search:term,offset,limit:100})})
   .then(async r=>{const value=await r.json();if(!r.ok)throw Error(value.detail||'Could not read filter values.');return value as Values;}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>controller.abort();
 },[resultId,column.side,column.column,status,filterKey,term,offset]);
 useLayoutEffect(()=>{
  const place=()=>{const rect=column.anchor.getBoundingClientRect(),below=window.innerHeight-rect.bottom-12,above=rect.top-12;const height=Math.min(500,Math.max(below,above),window.innerHeight-24);setPosition({left:Math.max(12,Math.min(rect.left,window.innerWidth-324)),top:below>=Math.min(420,above)?rect.bottom+5:Math.max(12,rect.top-height-5),maxHeight:Math.max(130,height)});};
  place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
 },[column.anchor]);
 useEffect(()=>{
  input.current?.focus();const outside=(e:PointerEvent)=>{if(!menu.current?.contains(e.target as Node)&&!column.anchor.contains(e.target as Node))onClose();};const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();onClose();column.anchor.focus();}};
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',key);};
 },[column.anchor,onClose]);
 const chosen=(value:string|null)=>draft.mode==='include'?draft.values.includes(value):!draft.values.includes(value);
 const toggle=(value:string|null)=>setDraft(old=>({...old,values:old.values.includes(value)?old.values.filter(v=>v!==value):[...old.values,value]}));
 const clear=()=>{onFilter(null);onClose();};
 const sortBy=(direction:'asc'|'desc')=>{onSort({side:column.side,column:column.column,direction});onClose();};
 return createPortal(<div ref={menu} id="document-column-filter" className="dc-column-menu" style={position} role="dialog" aria-modal="false" aria-label={`Filter File ${file}: ${column.name}`}>
  <header><strong>File {file} · {column.name}</strong><button type="button" className="btn" aria-label="Close column filter" onClick={()=>{onClose();column.anchor.focus();}}><X size={16}/></button></header>
  <div className="dc-column-sorts"><button type="button" onClick={()=>sortBy('asc')}><ArrowDownAZ size={16}/>Sort A to Z / smallest first</button><button type="button" onClick={()=>sortBy('desc')}><ArrowUpAZ size={16}/>Sort Z to A / largest first</button><button type="button" disabled={!current} onClick={clear}>Clear filter from this column</button>{sort?.side===column.side&&sort.column===column.column&&<button type="button" onClick={()=>{onSort(null);onClose();}}>Clear sorting</button>}</div>
  <label className="dc-column-search"><Search size={14}/><input ref={input} type="search" aria-label="Search filter values" placeholder="Search values" maxLength={200} value={search} onChange={e=>setSearch(e.target.value)}/></label>
  <label className="dc-column-all"><input type="checkbox" checked={all} ref={node=>{if(node)node.indeterminate=!all&&!none;}} onChange={()=>setDraft({...draft,mode:all?'include':'exclude',values:[]})}/>Select all values</label>
  <div className="dc-column-values" aria-busy={busy}>{data?.items.map(item=><label key={JSON.stringify(item.value)} title={item.label}><input type="checkbox" aria-label={`Include ${item.value===null?'absent row':item.value===''?'blank cell':item.label}`} checked={chosen(item.value)} onChange={()=>toggle(item.value)}/><span>{item.label}</span><small>{item.count}</small></label>)}{busy&&<p role="status">Loading values…</p>}{!busy&&!data?.items.length&&<p>No matching values.</p>}</div>
  {error&&<p className="dc-column-error" role="alert">{error}</p>}
  <div className="dc-column-pages"><small>{data?.total?`${offset+1}–${Math.min(offset+100,data.total)} of ${data.total}`:'0 values'}</small><button type="button" disabled={busy||!offset} onClick={()=>setOffset(n=>Math.max(0,n-100))}>Previous</button><button type="button" disabled={busy||!data||offset+100>=data.total} onClick={()=>setOffset(n=>n+100)}>Next</button></div>
  <small>Search narrows the list. Selections apply across all result pages.</small>
  <footer><button type="button" className="btn" onClick={()=>{onClose();column.anchor.focus();}}>Cancel</button><button type="button" className="btn primary" disabled={busy||!!error} onClick={()=>{onFilter(draft.mode==='exclude'&&!draft.values.length?null:draft);onClose();column.anchor.focus();}}>Apply filter</button></footer>
 </div>,document.body);
}
