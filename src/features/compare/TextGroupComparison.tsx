import {useState,type ReactNode} from 'react';
import {ChevronDown,ChevronRight} from 'lucide-react';
import {HmiPropertyComparison} from './HmiPropertyComparison';
import './text-group-comparison.css';

type RecordValue={name:string;index?:string;class?:string;class_id?:string;properties:Record<string,unknown>};
type Item={name:string;status:string;base?:RecordValue;new?:RecordValue;changes?:unknown[]};
type Column={id:string;label:string;value:(record:RecordValue)=>unknown};
const STATUS:Record<string,string>={added:'+ Added',removed:'− Removed',modified:'~ Modified',unchanged:'= Same'};
const raw=(value:unknown)=>value===undefined||value===null?'':String(value);
function languageName(code:string){
 try{return `${new Intl.DisplayNames(['en'],{type:'language'}).of(code.replace('_','-'))||code} (${code})`}catch{return code}
}
function sourceReference(value:unknown,kind:string){
 return raw(value).match(new RegExp(`\\.${kind}\\[(.*)\\]$`))?.[1]??raw(value);
}
function snippetDetails(record:RecordValue){
 const p=record.properties||{},parts:string[]=[];
 if(p.Datapoint)parts.push(`Datapoint(${sourceReference(p.Datapoint,'Variable')})`);
 if(p.TextGroup)parts.push(`Text group(${sourceReference(p.TextGroup,'TextGroup')})`);
 if(p.TextIndexOffset!==undefined)parts.push(`Index offset: ${raw(p.TextIndexOffset)}`);
 if(p.Content)parts.push(raw(p.Content));
 for(const [key,value] of Object.entries(p))if(!['Datapoint','TextGroup','TextIndexOffset','Content','StyleClass','Description'].includes(key))parts.push(`${key}: ${raw(value)}`);
 return parts.join(' · ');
}
function itemIndex(item:Item){return raw(item.new?.index??item.base?.index??item.name.replace(/^Value /,''))}

/** Paired grid rows keep language and snippet definitions aligned between projects. */
export function TextGroupComparison({data,baseLabel,newLabel}:{data:any;baseLabel:string;newLabel:string}){
 const [showAll,setShowAll]=useState(true),[query,setQuery]=useState(''),[language,setLanguage]=useState('all');
 const [showIds,setShowIds]=useState(false),[valuesOpen,setValuesOpen]=useState(true),[snippetsOpen,setSnippetsOpen]=useState(true);
 const [selected,setSelected]=useState<{kind:string;item:Item}|null>(null);
 const allValues:Item[]=data.controls||[],allSnippets:Item[]=data.text_group?.snippets||[];
 const languages:string[]=Array.from(new Set<string>(data.text_group?.languages||allValues.flatMap(item=>[item.base,item.new].flatMap(record=>Object.keys(record?.properties||{}).filter(key=>key.startsWith('Language: ')).map(key=>key.slice(10))))));
 languages.sort((a,b)=>(a==='en'?-1:b==='en'?1:0)||a.localeCompare(b));
 const visible=(items:Item[])=>items.filter(item=>(showAll||item.status!=='unchanged')&&(!query||JSON.stringify([item.name,item.base,item.new]).toLowerCase().includes(query.toLowerCase())));
 const values=visible(allValues).sort((a,b)=>itemIndex(a).localeCompare(itemIndex(b),undefined,{numeric:true}));
 const snippets=visible(allSnippets).sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));
 const textColumns:Column[]=[{id:'index',label:'Index',value:record=>record.index??record.name.replace(/^Value /,'')},
  ...(showIds?[{id:'text-id',label:'Text ID',value:(record:RecordValue)=>record.properties['Text ID']}]:[]),
  ...languages.filter(code=>language==='all'||code===language).map(code=>({id:code,label:languageName(code),value:(record:RecordValue)=>record.properties['Language: '+code]}))];
 const snippetColumns:Column[]=[{id:'name',label:'Name',value:record=>record.name},{id:'type',label:'Type',value:record=>record.class},
  {id:'style',label:'StyleClass',value:record=>sourceReference(record.properties.StyleClass,'StyleClass')},
  {id:'details',label:'Details',value:snippetDetails},{id:'description',label:'Description',value:record=>record.properties.Description}];
 const properties=(record?:RecordValue)=>record?{Name:record.name,...(record.class_id?{ClassId:record.class_id}:{}),...record.properties}:{};
 const grid=(items:Item[],columns:Column[],kind:string):ReactNode=><div className="textGroupTableScroll" tabIndex={0} aria-label={`${kind} comparison scroll area`}>
  <table className={'textGroupTable '+(kind==='Text snippets'?'snippets':'values')} aria-label={`${kind} comparison`}>
   <colgroup>{[0,1].flatMap(side=>[<col key={side+'state'} style={{width:'2%'}}/>,...columns.map(col=>{
    const snippetWidths:Record<string,number>={name:12,type:6,style:6,details:17,description:7};
    const languageCount=columns.filter(column=>!['index','text-id'].includes(column.id)).length;
    const width=(kind==='Text snippets'?snippetWidths[col.id]:col.id==='index'?(languageCount?4:48-(showIds?6:0)):
     col.id==='text-id'?6:(44-(showIds?6:0))/Math.max(1,languageCount))+'%';
    return <col key={side+col.id} style={{width}}/>;
   })])}</colgroup>
   <thead><tr>{[baseLabel,newLabel].map((label,side)=><th colSpan={columns.length+1} key={side} className={side?'developed':'base'}><span>{side?'DEVELOPED / COMPARE':'BASE / REFERENCE'}</span><b>{label}</b></th>)}</tr>
    <tr>{[0,1].flatMap(side=>[<th key={side+'status'} scope="col" title="Comparison status" className={side?'sideStart':''}>Δ</th>,...columns.map(col=><th key={side+col.id} scope="col">{col.label}</th>)])}</tr></thead>
   <tbody>{items.map(item=><tr key={item.name} data-record={item.name} data-status={item.status} className={selected?.kind===kind&&selected.item.name===item.name?'selected':''}>
    {[item.base,item.new].flatMap((record,side)=>[
     <td key={side+'status'} className={'textGroupRowStatus '+item.status+(side?' sideStart':'')} title={STATUS[item.status]}>{item.status==='added'?'+':item.status==='removed'?'−':item.status==='modified'?'~':'='}</td>,
     ...columns.map((col,index)=>{
      const value=record?col.value(record):undefined,other=side?item.base:item.new;
      const different=value!==(other?col.value(other):undefined)||!record!==!other;
      const state=different?(!record?'absent':!other?(side?'added':'removed'):'modified'):'';
      const text=!record?'Not present':value===undefined?'Not defined':raw(value)===''?'(empty)':raw(value);
      return <td key={side+col.id} data-column={col.id} className={state} title={text}>
       {index===0?<button type="button" className="textGroupRowSelect" aria-label={`Inspect ${kind==='Text snippets'?'snippet':'index'} ${kind==='Text snippets'?item.name:itemIndex(item)} (${side?newLabel:baseLabel})`} onClick={()=>setSelected({kind,item})}>{text}</button>:<span className={!record||value===undefined||raw(value)===''?'textGroupEmpty':''}>{text}</span>}
      </td>;
     })])}
   </tr>)}{!items.length&&<tr><td colSpan={(columns.length+1)*2} className="textGroupNoRows">{showAll?'No matching rows.':'No changed rows. Select Show all to see every entry.'}</td></tr>}</tbody>
  </table>
 </div>;
 const sectionHeading=(title:string,open:boolean,toggle:()=>void,items:Item[],visibleCount:number)=><button type="button" className="textGroupSectionHeading" onClick={toggle} aria-expanded={open}>
  {open?<ChevronDown size={17}/>:<ChevronRight size={17}/>}<b>{title}</b><span>{visibleCount} / {items.length} rows</span><small>{items.filter(item=>item.status!=='unchanged').length} changed</small>
 </button>;
 return <div className="textGroupComparison">
  <div className="hmiInspectorTabs"><strong>{data.object_name||'Text group'}</strong><span>Text group and snippet comparison</span><button className={!showAll?'active':''} onClick={()=>setShowAll(false)}>Changed only</button><button className={showAll?'active':''} onClick={()=>setShowAll(true)}>Show all</button></div>
  <div className="textGroupTools"><label>Search <input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Index, text or snippet…"/></label><label>Language <select aria-label="Text group language" value={language} onChange={event=>setLanguage(event.target.value)}><option value="all">All languages</option>{languages.map(code=><option value={code} key={code}>{languageName(code)}</option>)}</select></label><label><input type="checkbox" checked={showIds} onChange={event=>setShowIds(event.target.checked)}/> Show text IDs</label><span>+ Added · − Removed · ~ Modified · = Same</span></div>
  {sectionHeading('Text group values',valuesOpen,()=>setValuesOpen(!valuesOpen),allValues,values.length)}
  {valuesOpen&&grid(values,textColumns,'Text group values')}
  {sectionHeading('Text snippets',snippetsOpen,()=>setSnippetsOpen(!snippetsOpen),allSnippets,snippets.length)}
  {snippetsOpen&&(data.text_group?grid(snippets,snippetColumns,'Text snippets'):<p className="textGroupNoRows">Rerun this comparison to include Text Snippets from the source files.</p>)}
  <details className="textGroupExtra"><summary>Text group properties</summary><HmiPropertyComparison base={data.base_page_properties||{}} developed={data.new_page_properties||{}} baseLabel={baseLabel} newLabel={newLabel} contextKey={data.object_name+':group'}/></details>
  {selected&&<section className="textGroupExtra" aria-label="Selected text group record"><div className="textGroupSelectionHead"><b>{selected.kind}: {selected.item.name}</b><button type="button" onClick={()=>setSelected(null)}>Close details</button></div><HmiPropertyComparison base={properties(selected.item.base)} developed={properties(selected.item.new)} baseLabel={baseLabel} newLabel={newLabel} contextKey={data.object_name+':'+selected.kind+':'+selected.item.name} baseMissing={!selected.item.base} newMissing={!selected.item.new}/></section>}
 </div>;
}
